import math
import time
import logging
from typing import List, Dict, Any, Tuple

import streamlit as st
import pandas as pd

from dashboard.serial_reader import SerialSensorReader
from dashboard.analytics import WristRiskAnalyzer
from dashboard.recommendations import ErgonomicRecommendationEngine

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

st.set_page_config(
    page_title="Wristly — AI Wrist Health Monitor",
    page_icon="🦾",
    layout="wide",
)

# ----------------------------------------------------------------------------
# Design tokens
# ----------------------------------------------------------------------------
COLOR_SAFE = "#37D6B4"
COLOR_CAUTION = "#F2A93B"
COLOR_DANGER = "#FF5D5D"
COLOR_TEXT = "#E8EEF0"
COLOR_MUTED = "#7C8B93"
COLOR_TRACK = "rgba(255,255,255,0.08)"

RISK_STYLE = {
    "LOW": {"label": "SAFE", "color": COLOR_SAFE, "sub": "Wrist posture is in a healthy range."},
    "MEDIUM": {"label": "CAUTION", "color": COLOR_CAUTION, "sub": "Posture is drifting from neutral."},
    "HIGH": {"label": "HIGH RISK", "color": COLOR_DANGER, "sub": "Strain risk is elevated — take a break."},
}

BASE_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;700&display=swap');

html, body, [class*="css"] { font-family: 'Space Grotesk', sans-serif; }
.mono { font-family: 'JetBrains Mono', monospace; }

#MainMenu {visibility: hidden;}
footer {visibility: hidden;}
div.block-container {padding-top: 1.6rem; padding-bottom: 2.5rem;}

.wr-header {display:flex; align-items:center; justify-content:space-between; margin-bottom: 0.4rem;}
.wr-brand {display:flex; align-items:baseline; gap:0.6rem;}
.wr-brand h1 {font-size: 1.7rem; font-weight:700; letter-spacing: 0.02em; margin:0; color:%(text)s;}
.wr-brand span {font-size: 0.85rem; color:%(muted)s; font-weight:500;}

.wr-pill {display:inline-flex; align-items:center; gap:0.45rem; padding: 0.35rem 0.85rem;
  border-radius: 999px; font-size:0.78rem; font-weight:600; letter-spacing:0.03em;
  border:1px solid rgba(255,255,255,0.08); font-family:'JetBrains Mono',monospace;}
.wr-dot {width:8px; height:8px; border-radius:50%%;}
.wr-dot.live {background:%(safe)s; box-shadow:0 0 8px %(safe)s; animation: wr-pulse 1.6s infinite;}
.wr-dot.idle {background:%(muted)s;}
.wr-dot.err {background:%(danger)s; box-shadow:0 0 8px %(danger)s;}
@keyframes wr-pulse {0%%{opacity:1;} 50%%{opacity:0.35;} 100%%{opacity:1;}}

.wr-card {background:%(surface)s; border:1px solid rgba(255,255,255,0.06); border-radius:16px;
  padding:1.1rem 1.3rem; height:100%%;}
.wr-card-title {font-size:0.72rem; font-weight:600; letter-spacing:0.09em; color:%(muted)s;
  text-transform:uppercase; margin-bottom:0.55rem;}

.wr-metric-value {font-family:'JetBrains Mono', monospace; font-size:1.9rem; font-weight:700; color:%(text)s; line-height:1.1;}
.wr-metric-sub {font-size:0.8rem; color:%(muted)s; margin-top:0.25rem;}
.wr-trend {font-size:0.78rem; font-family:'JetBrains Mono',monospace; margin-left:0.4rem;}

.wr-chip {display:inline-flex; align-items:center; gap:0.4rem; padding:0.32rem 0.75rem; border-radius:10px;
  font-size:0.8rem; font-weight:500; background:rgba(255,93,93,0.10); color:%(danger)s;
  border:1px solid rgba(255,93,93,0.25); margin:0.2rem 0.4rem 0.2rem 0;}
.wr-chip.ok {background:rgba(55,214,180,0.10); color:%(safe)s; border-color:rgba(55,214,180,0.25);}

.wr-rec-card {background:linear-gradient(135deg, rgba(55,214,180,0.07), rgba(22,31,36,0.4));
  border:1px solid rgba(55,214,180,0.18); border-radius:16px; padding:1.2rem 1.4rem;}
.wr-rec-head {display:flex; align-items:center; gap:0.5rem; font-size:0.78rem; font-weight:700;
  letter-spacing:0.08em; color:%(safe)s; text-transform:uppercase; margin-bottom:0.55rem;}
.wr-rec-text {font-size:0.98rem; color:%(text)s; line-height:1.55; white-space:pre-wrap;}
.wr-rec-time {font-size:0.72rem; color:%(muted)s; margin-top:0.6rem; font-family:'JetBrains Mono',monospace;}

.wr-section-label {font-size:0.72rem; font-weight:600; letter-spacing:0.09em; color:%(muted)s;
  text-transform:uppercase; margin: 0.9rem 0 0.4rem 0;}

.wr-footer {text-align:center; color:%(muted)s; font-size:0.72rem; margin-top:1.6rem;
  font-family:'JetBrains Mono',monospace; letter-spacing:0.03em;}
</style>
""" % {
    "text": COLOR_TEXT, "muted": COLOR_MUTED, "safe": COLOR_SAFE,
    "danger": COLOR_DANGER, "surface": "#161F24",
}


# ----------------------------------------------------------------------------
# Gauge rendering
# ----------------------------------------------------------------------------
def _polar(cx: float, cy: float, r: float, angle_deg: float) -> Tuple[float, float]:
    rad = math.radians(angle_deg)
    return cx + r * math.cos(rad), cy + r * math.sin(rad)


def _arc_path(r: float, start_frac: float, end_frac: float, cx: float = 100, cy: float = 100,
              start_angle: float = 135, sweep: float = 270) -> str:
    a0 = start_angle + start_frac * sweep
    a1 = start_angle + end_frac * sweep
    x0, y0 = _polar(cx, cy, r, a0)
    x1, y1 = _polar(cx, cy, r, a1)
    large_arc = 1 if (a1 - a0) > 180 else 0
    return f"M {x0:.2f} {y0:.2f} A {r} {r} 0 {large_arc} 1 {x1:.2f} {y1:.2f}"


def render_gauge_svg(risk_score: float, risk_level: str) -> str:
    """Renders a 270-degree three-zone radial dial, styled like a wearable's activity ring."""
    fraction = max(0.0, min(risk_score / 10.0, 1.0))
    style = RISK_STYLE.get(risk_level, RISK_STYLE["LOW"])
    color = style["color"]
    percent = round(fraction * 100)

    r_track, r_zones = 80, 92
    zones = [(0.0, 0.30, COLOR_SAFE), (0.30, 0.70, COLOR_CAUTION), (0.70, 1.0, COLOR_DANGER)]
    zone_paths = "".join(
        f'<path d="{_arc_path(r_zones, s, e)}" fill="none" stroke="{c}" '
        f'stroke-opacity="0.35" stroke-width="4" stroke-linecap="round" />'
        for s, e, c in zones
    )

    track_path = _arc_path(r_track, 0.0, 1.0)
    progress_path = _arc_path(r_track, 0.0, fraction) if fraction > 0.002 else ""
    cap_x, cap_y = _polar(100, 100, r_track, 135 + fraction * 270)

    progress_el = (
        f'<path d="{progress_path}" fill="none" stroke="{color}" stroke-width="14" '
        f'stroke-linecap="round" filter="url(#wrGlow)" />'
        if progress_path else ""
    )
    cap_el = (
        f'<circle cx="{cap_x:.2f}" cy="{cap_y:.2f}" r="7" fill="{color}" filter="url(#wrGlow)" />'
        if fraction > 0.002 else ""
    )

    # FIX: Flattened the SVG into a single concatenated string 
    # to prevent Streamlit from turning indented lines into Markdown code blocks.
    return (
        f'<svg viewBox="0 0 200 200" width="100%" height="auto" style="max-width:230px; display:block; margin:0 auto;">'
        f'<defs><filter id="wrGlow" x="-50%" y="-50%" width="200%" height="200%">'
        f'<feGaussianBlur stdDeviation="4" result="blur" />'
        f'<feMerge><feMergeNode in="blur" /><feMergeNode in="SourceGraphic" /></feMerge>'
        f'</filter></defs>'
        f'{zone_paths}'
        f'<path d="{track_path}" fill="none" stroke="{COLOR_TRACK}" stroke-width="14" stroke-linecap="round" />'
        f'{progress_el}'
        f'{cap_el}'
        f'<text x="100" y="96" text-anchor="middle" font-family="JetBrains Mono, monospace" font-size="34" font-weight="700" fill="{COLOR_TEXT}">{percent}%</text>'
        f'<text x="100" y="118" text-anchor="middle" font-family="Space Grotesk, sans-serif" font-size="11" font-weight="600" letter-spacing="1.5" fill="{color}">{style["label"]}</text>'
        f'</svg>'
    )


# ----------------------------------------------------------------------------
# Presentation helpers (display-only — analytics.py stays untouched)
# ----------------------------------------------------------------------------
def classify_wrist_status(pitch: float, roll: float) -> Tuple[str, str]:
    """Maps pitch/roll into a human-readable posture label. Purely presentational."""
    ext, flex, rad, uln = pitch > 15, pitch < -15, roll > 15, roll < -15
    if (ext or flex) and (rad or uln):
        return "Combined Strain", "⚠️"
    if ext:
        return "Extension", "↗"
    if flex:
        return "Flexion", "↘"
    if rad:
        return "Radial Deviation", "↷"
    if uln:
        return "Ulnar Deviation", "↶"
    return "Neutral", "✓"


def trend_arrow(current: float, previous: float) -> str:
    if previous is None:
        return ""
    delta = current - previous
    if abs(delta) < 0.5:
        return f'<span class="wr-trend" style="color:{COLOR_MUTED}">·</span>'
    if delta > 0:
        return f'<span class="wr-trend" style="color:{COLOR_CAUTION}">▲ {abs(delta):.1f}°</span>'
    return f'<span class="wr-trend" style="color:{COLOR_SAFE}">▼ {abs(delta):.1f}°</span>'


def status_pill_html(monitoring: bool, source_label: str, error: str = "") -> str:
    if error:
        return (f'<span class="wr-pill"><span class="wr-dot err"></span>'
                f'ERROR — {error[:60]}</span>')
    if monitoring:
        return (f'<span class="wr-pill"><span class="wr-dot live"></span>'
                f'LIVE — {source_label}</span>')
    return '<span class="wr-pill"><span class="wr-dot idle"></span>IDLE</span>'


# ----------------------------------------------------------------------------
# Session state
# ----------------------------------------------------------------------------
def initialize_session_state() -> None:
    defaults = {
        "pitch_history": [], "roll_history": [], "timestamps": [],
        "monitoring": False, "prev_pitch": None, "prev_roll": None,
        "ai_recommendation": "Start monitoring to generate a personalized recommendation.",
        "ai_rec_time": None, "last_risk_level": "LOW", "last_risk_score": 0.0,
        "last_pitch": 0.0, "last_roll": 0.0, "last_warnings": [],
    }
    for key, val in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = val


def main() -> None:
    initialize_session_state()
    st.markdown(BASE_CSS, unsafe_allow_html=True)

    header_placeholder = st.empty()

    # ---- Sidebar: session controls ----
    st.sidebar.markdown(
        '<div style="font-weight:700; font-size:1.05rem; letter-spacing:0.02em;">🦾 WRISTLY</div>'
        '<div style="color:#7C8B93; font-size:0.78rem; margin-bottom:1rem;">Session controls</div>',
        unsafe_allow_html=True,
    )

    source_mode = st.sidebar.radio("Sensor Source", ("Simulation Mode", "Physical Serial Port"), index=0)
    if source_mode == "Physical Serial Port":
        port = st.sidebar.text_input("Serial Port", value="COM3")
    else:
        port = st.sidebar.selectbox("Simulation Source", ["simulation", "wokwi"], index=0)

    baudrate = st.sidebar.number_input("Baud Rate", value=115200, step=9600)
    max_history = st.sidebar.slider("Graph History Length", min_value=10, max_value=200, value=50)

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
            st.session_state.prev_pitch = None
            st.session_state.prev_roll = None
            st.session_state.ai_recommendation = "Start monitoring to generate a personalized recommendation."
            st.session_state.ai_rec_time = None
            st.rerun()

    st.sidebar.markdown(
        '<div style="color:#7C8B93; font-size:0.72rem; margin-top:1.2rem; line-height:1.5;">'
        'AI-powered ergonomic wrist monitor for early CTS risk detection.<br>NGN Hacks 2026.</div>',
        unsafe_allow_html=True,
    )

    analyzer = WristRiskAnalyzer()
    recommendation_engine = ErgonomicRecommendationEngine()

    # ---- Main layout placeholders ----
    gauge_col, readout_col = st.columns([1, 1.6], gap="medium")
    with gauge_col:
        gauge_placeholder = st.empty()
    with readout_col:
        readout_placeholder = st.empty()

    warnings_placeholder = st.empty()

    st.markdown('<div class="wr-section-label">AI Ergonomic Recommendation</div>', unsafe_allow_html=True)
    rec_placeholder = st.empty()
    if st.button("🔄 Refresh AI Recommendation"):
        risk_data = {
            "risk_level": st.session_state.last_risk_level,
            "risk_score": st.session_state.last_risk_score,
            "pitch": st.session_state.last_pitch,
            "roll": st.session_state.last_roll,
            "warnings": st.session_state.last_warnings,
        }
        with st.spinner("Generating personalized recommendation..."):
            rec = recommendation_engine.generate_recommendation(risk_data)
            st.session_state.ai_recommendation = rec
            st.session_state.ai_rec_time = time.time()

    st.markdown('<div class="wr-section-label">Live Wrist Tracking</div>', unsafe_allow_html=True)
    chart_placeholder = st.empty()

    def render_static_frame() -> None:
        """Renders the dashboard using the last-known values (used before Start / after Stop)."""
        header_placeholder.markdown(
            f'<div class="wr-header"><div class="wr-brand"><h1>🦾 WRISTLY</h1>'
            f'<span>AI Wrist Health Monitor</span></div>'
            f'{status_pill_html(st.session_state.monitoring, port)}</div>',
            unsafe_allow_html=True,
        )
        style = RISK_STYLE.get(st.session_state.last_risk_level, RISK_STYLE["LOW"])
        with gauge_placeholder.container():
            st.markdown(f'<div class="wr-card">{render_gauge_svg(st.session_state.last_risk_score, st.session_state.last_risk_level)}'
                        f'<div style="text-align:center; color:{COLOR_MUTED}; font-size:0.8rem; margin-top:0.4rem;">'
                        f'{style["sub"]}</div></div>', unsafe_allow_html=True)

        wrist_label, wrist_icon = classify_wrist_status(st.session_state.last_pitch, st.session_state.last_roll)
        with readout_placeholder.container():
            c1, c2, c3 = st.columns(3)
            for col, title, value, sub in (
                (c1, "Wrist Status", f"{wrist_icon} {wrist_label}", "Posture classification"),
                (c2, "Pitch", f'{st.session_state.last_pitch:.1f}°'
                              f'{trend_arrow(st.session_state.last_pitch, st.session_state.prev_pitch)}', "Up / down flex"),
                (c3, "Roll", f'{st.session_state.last_roll:.1f}°'
                             f'{trend_arrow(st.session_state.last_roll, st.session_state.prev_roll)}', "Side deviation"),
            ):
                with col:
                    st.markdown(
                        f'<div class="wr-card"><div class="wr-card-title">{title}</div>'
                        f'<div class="wr-metric-value">{value}</div>'
                        f'<div class="wr-metric-sub">{sub}</div></div>',
                        unsafe_allow_html=True,
                    )

        if st.session_state.last_warnings:
            chips = "".join(f'<span class="wr-chip">⚠ {w}</span>' for w in st.session_state.last_warnings)
        else:
            chips = '<span class="wr-chip ok">✓ No active warnings — posture optimal</span>'
        warnings_placeholder.markdown(chips, unsafe_allow_html=True)

        rec_time_str = ""
        if st.session_state.ai_rec_time:
            secs = int(time.time() - st.session_state.ai_rec_time)
            rec_time_str = f"Updated {secs}s ago" if secs < 60 else f"Updated {secs // 60}m ago"

        is_error = st.session_state.ai_recommendation.strip().startswith("Error:")
        rec_card_style = (
            "border-color:rgba(255,93,93,0.3); background:linear-gradient(135deg, rgba(255,93,93,0.08), rgba(22,31,36,0.4));"
            if is_error else ""
        )
        rec_head_color = COLOR_DANGER if is_error else COLOR_SAFE
        rec_icon = "⚠️" if is_error else "🤖"
        rec_placeholder.markdown(
            f'<div class="wr-rec-card" style="{rec_card_style}">'
            f'<div class="wr-rec-head" style="color:{rec_head_color};">{rec_icon} '
            f'{"Recommendation Unavailable" if is_error else "Recommendation"}</div>'
            f'<div class="wr-rec-text">{st.session_state.ai_recommendation}</div>'
            f'<div class="wr-rec-time">{rec_time_str}</div></div>',
            unsafe_allow_html=True,
        )

        if st.session_state.pitch_history:
            df_history = pd.DataFrame({
                "Timestamp": st.session_state.timestamps,
                "Pitch": st.session_state.pitch_history,
                "Roll": st.session_state.roll_history,
            }).set_index("Timestamp")
            with chart_placeholder.container():
                st.markdown('<div class="wr-card">', unsafe_allow_html=True)
                st.line_chart(df_history, color=[COLOR_SAFE, COLOR_CAUTION], height=260)
                st.markdown('</div>', unsafe_allow_html=True)
        else:
            chart_placeholder.markdown(
                f'<div class="wr-card" style="text-align:center; color:{COLOR_MUTED}; padding:2.5rem 0;">'
                f'No data yet — start monitoring to see live pitch &amp; roll history.</div>',
                unsafe_allow_html=True,
            )

    render_static_frame()
    st.markdown(
        f'<div class="wr-footer">WRISTLY · CTS PREVENTION WEARABLE · NGN HACKS 2026</div>',
        unsafe_allow_html=True,
    )

    if not st.session_state.monitoring:
        return

    try:
        reader = SerialSensorReader(port=port, baudrate=int(baudrate))
        for packet in reader.stream():
            if not st.session_state.monitoring:
                reader.close()
                break
            if not packet:
                continue

            analysis = analyzer.analyze(packet)

            st.session_state.prev_pitch = st.session_state.last_pitch
            st.session_state.prev_roll = st.session_state.last_roll
            st.session_state.last_risk_level = analysis["risk_level"]
            st.session_state.last_risk_score = analysis["risk_score"]
            st.session_state.last_pitch = analysis["pitch"]
            st.session_state.last_roll = analysis["roll"]
            st.session_state.last_warnings = analysis["warnings"]

            st.session_state.pitch_history.append(analysis["pitch"])
            st.session_state.roll_history.append(analysis["roll"])
            st.session_state.timestamps.append(pd.Timestamp.now())
            if len(st.session_state.pitch_history) > max_history:
                st.session_state.pitch_history.pop(0)
                st.session_state.roll_history.pop(0)
                st.session_state.timestamps.pop(0)

            if (analysis["risk_level"] == "HIGH"
                    and len(st.session_state.pitch_history) % 30 == 0):
                rec = recommendation_engine.generate_recommendation(analysis)
                st.session_state.ai_recommendation = rec
                st.session_state.ai_rec_time = time.time()

            render_static_frame()
            time.sleep(0.05)

    except Exception as e:
        header_placeholder.markdown(
            f'<div class="wr-header"><div class="wr-brand"><h1>🦾 WRISTLY</h1>'
            f'<span>AI Wrist Health Monitor</span></div>'
            f'{status_pill_html(False, port, error=str(e))}</div>',
            unsafe_allow_html=True,
        )
        st.session_state.monitoring = False
        logger.error(f"Connection error: {e}")


if __name__ == "__main__":
    main()
