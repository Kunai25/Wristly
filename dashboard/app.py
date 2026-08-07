import time
import logging
from typing import List, Dict, Any

import streamlit as st
import pandas as pd

# Import custom modules
from dashboard.serial_reader import SerialSensorReader
from dashboard.analytics import WristRiskAnalyzer
from dashboard.recommendations import ErgonomicRecommendationEngine

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Set up Streamlit page configuration
st.set_page_config(
    page_title="Wristly - AI Ergonomic Wrist Monitor",
    page_icon="🦾",
    layout="wide",
)


def initialize_session_state() -> None:
    """Initializes Streamlit session state variables if they do not exist."""
    if "pitch_history" not in st.session_state:
        st.session_state.pitch_history = []
    if "roll_history" not in st.session_state:
        st.session_state.roll_history = []
    if "timestamps" not in st.session_state:
        st.session_state.timestamps = []
    if "monitoring" not in st.session_state:
        st.session_state.monitoring = False
    if "ai_recommendation" not in st.session_state:
        st.session_state.ai_recommendation = "No recommendation generated yet. Start monitoring to analyze your posture."


def main() -> None:
    initialize_session_state()

    st.title("🦾 Wristly - AI Ergonomic Wrist Monitor")
    st.markdown(
        "Real-time wrist posture tracking and AI-powered ergonomic recommendations to prevent strain."
    )

    # Sidebar for configuration
    st.sidebar.header("Connection Settings")
    port = st.sidebar.text_input("Serial Port", value="COM3")
    baudrate = st.sidebar.number_input("Baud Rate", value=115200, step=9600)
    
    # Max history points to display in graphs
    max_history = st.sidebar.slider("Graph History Length", min_value=10, max_value=200, value=50)

    # Control buttons
    col_start, col_stop, col_clear = st.sidebar.columns(3)
    with col_start:
        if st.button("Start", use_container_width=True):
            st.session_state.monitoring = True
    with col_stop:
        if st.button("Stop", use_container_width=True):
            st.session_state.monitoring = False
    with col_clear:
        if st.button("Clear", use_container_width=True):
            st.session_state.pitch_history = []
            st.session_state.roll_history = []
            st.session_state.timestamps = []
            st.session_state.ai_recommendation = "No recommendation generated yet. Start monitoring to analyze your posture."
            st.rerun()

    # Initialize components
    analyzer = WristRiskAnalyzer()
    recommendation_engine = ErgonomicRecommendationEngine()

    # Layout: Top metrics and status
    status_placeholder = st.empty()
    
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        risk_level_metric = st.empty()
    with col2:
        risk_score_metric = st.empty()
    with col3:
        pitch_metric = st.empty()
    with col4:
        roll_metric = st.empty()

    # Layout: Warnings and AI Recommendations
    st.markdown("---")
    col_left, col_right = st.columns([1, 1])
    
    with col_left:
        st.subheader("⚠️ Active Warnings")
        warnings_placeholder = st.empty()
        warnings_placeholder.info("No active warnings. Keep up the good posture!")

    with col_right:
        st.subheader("🤖 AI Ergonomic Recommendations")
        ai_rec_placeholder = st.empty()
        ai_rec_placeholder.write(st.session_state.ai_recommendation)
        
        # Button to manually trigger AI recommendation based on current state
        if st.button("Refresh AI Recommendation", use_container_width=True):
            if st.session_state.pitch_history and st.session_state.roll_history:
                latest_pitch = st.session_state.pitch_history[-1]
                latest_roll = st.session_state.roll_history[-1]
                
                # Re-analyze latest data to get structured risk data
                dummy_packet = {
                    "timestamp": int(time.time() * 1000),
                    "pitch": latest_pitch,
                    "roll": latest_roll,
                    "heading": 0.0,
                    "ax": 0.0, "ay": 0.0, "az": 1.0,
                    "gx": 0.0, "gy": 0.0, "gz": 0.0
                }
                risk_data = analyzer.analyze(dummy_packet)
                
                with st.spinner("Generating personalized recommendations..."):
                    rec = recommendation_engine.generate_recommendation(risk_data)
                    st.session_state.ai_recommendation = rec
                    ai_rec_placeholder.write(rec)
            else:
                st.warning("No sensor data available yet to generate recommendations.")

    # Layout: Live Graphs
    st.markdown("---")
    st.subheader("📈 Live Posture History")
    graph_col1, graph_col2 = st.columns(2)
    with graph_col1:
        st.markdown("**Pitch Angle History (Degrees)**")
        pitch_chart_placeholder = st.empty()
    with graph_col2:
        st.markdown("**Roll Angle History (Degrees)**")
        roll_chart_placeholder = st.empty()

    # Main monitoring loop
    if st.session_state.monitoring:
        if port.lower() in ("wokwi", "wokwisim"):
            status_placeholder.success("Connecting to Wokwi simulation...")
        else:
            status_placeholder.success(f"Connecting to {port}...")
        try:
            reader = SerialSensorReader(port=port, baudrate=int(baudrate))
            if port.lower() in ("wokwi", "wokwisim"):
                status_placeholder.success("Connected to Wokwi simulation. Streaming live data...")
            else:
                status_placeholder.success(f"Connected to {port}. Streaming live data...")
            
            # Read and update loop
            for packet in reader.stream():
                if not st.session_state.monitoring:
                    break
                
                # Analyze packet
                analysis = analyzer.analyze(packet)
                
                # Extract metrics
                risk_level = analysis["risk_level"]
                risk_score = analysis["risk_score"]
                pitch = analysis["pitch"]
                roll = analysis["roll"]
                warnings = analysis["warnings"]
                
                # Update history
                st.session_state.pitch_history.append(pitch)
                st.session_state.roll_history.append(roll)
                st.session_state.timestamps.append(pd.Timestamp.now())
                
                # Keep history within limits
                if len(st.session_state.pitch_history) > max_history:
                    st.session_state.pitch_history.pop(0)
                    st.session_state.roll_history.pop(0)
                    st.session_state.timestamps.pop(0)
                
                # Update metrics display
                risk_level_metric.metric("Risk Level", risk_level)
                risk_score_metric.metric("Risk Score", f"{risk_score}/10.0")
                pitch_metric.metric("Pitch Angle", f"{pitch:.1f}°")
                roll_metric.metric("Roll Angle", f"{roll:.1f}°")
                
                # Update warnings
                if warnings:
                    warnings_placeholder.warning("\n".join([f"- {w}" for w in warnings]))
                else:
                    warnings_placeholder.success("Posture is optimal. No warnings!")
                
                # Update charts
                df_history = pd.DataFrame({
                    "Timestamp": st.session_state.timestamps,
                    "Pitch": st.session_state.pitch_history,
                    "Roll": st.session_state.roll_history
                }).set_index("Timestamp")
                
                pitch_chart_placeholder.line_chart(df_history["Pitch"])
                roll_chart_placeholder.line_chart(df_history["Roll"])
                
                # Auto-trigger AI recommendation if risk becomes HIGH and we haven't updated recently
                if risk_level == "HIGH" and len(st.session_state.pitch_history) % 30 == 0:
                    rec = recommendation_engine.generate_recommendation(analysis)
                    st.session_state.ai_recommendation = rec
                    ai_rec_placeholder.write(rec)
                
                # Small sleep to yield control to Streamlit UI rendering
                time.sleep(0.05)
                
        except Exception as e:
            status_placeholder.error(f"Failed to connect or read from serial port: {e}")
            st.session_state.monitoring = False
            logger.error(f"Serial connection error: {e}")
    else:
        status_placeholder.info("Monitoring is stopped. Click 'Start' in the sidebar to begin.")


if __name__ == "__main__":
    main()
