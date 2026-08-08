#include <Wire.h>
#include <Arduino.h>

// --- Pin Definitions ---
#define I2C_SDA_PIN 21
#define I2C_SCL_PIN 22
#define POT_PIN 34

// --- MPU6050 Register Map ---
#define MPU6050_ADDR         0x68
#define MPU6050_PWR_MGMT_1   0x6B
#define MPU6050_ACCEL_XOUT_H 0x3B
#define MPU6050_GYRO_XOUT_H  0x43

// --- Constants ---
const float RAD_TO_DEG_CONST = 180.0 / PI;
const float ACCEL_SCALE = 16384.0; // LSB/g for +/- 2g range
const float GYRO_SCALE = 131.0;     // LSB/(deg/s) for +/- 250 deg/s range
const float ALPHA = 0.98;           // Complementary filter coefficient
const float DT = 0.05;              // Sample period in seconds (20Hz)

// --- Global Variables ---
float pitch = 0.0;
float roll = 0.0;
unsigned long lastSampleTime = 0;

// Gyroscope calibration biases
float gyroBiasX = 0.0;
float gyroBiasY = 0.0;
float gyroBiasZ = 0.0;

// Last valid sensor readings (used as fallback if I2C read fails)
float ax = 0.0, ay = 0.0, az = 1.0;
float gx = 0.0, gy = 0.0, gz = 0.0;

// Function declarations
void initMPU6050();
void calibrateGyro();
bool readSensorData(float &ax, float &ay, float &az, float &gx, float &gy, float &gz);
void updateComplementaryFilter(float ax, float ay, float az, float gx, float gy);
float readHeading();

void setup() {
  Serial.begin(115200);
  
  // Initialize I2C on specified pins
  Wire.begin(I2C_SDA_PIN, I2C_SCL_PIN);
  
  // Initialize MPU6050
  initMPU6050();
  
  // Calibrate gyroscope while stationary
  Serial.println("Keep wrist still for calibration...");
  calibrateGyro();
  
  // Configure potentiometer pin
  pinMode(POT_PIN, INPUT);
  
  lastSampleTime = millis();
}

void loop() {
  unsigned long currentTime = millis();
  
  // Maintain approximately 20Hz output rate (50ms interval)
  if (currentTime - lastSampleTime >= 50) {
    lastSampleTime = currentTime;
    
    // 1. Read raw sensor values (updates variables only if read succeeds)
    readSensorData(ax, ay, az, gx, gy, gz);
    
    // 2. Calculate pitch and roll using complementary filter
    updateComplementaryFilter(ax, ay, az, gx, gy);
    
    // 3. Read potentiometer and map to simulated heading
    float heading = readHeading();
    
    // 4. Output newline-delimited JSON
    Serial.print("{");
    Serial.print("\"timestamp\":"); Serial.print(currentTime); Serial.print(",");
    Serial.print("\"pitch\":"); Serial.print(pitch, 2); Serial.print(",");
    Serial.print("\"roll\":"); Serial.print(roll, 2); Serial.print(",");
    Serial.print("\"heading\":"); Serial.print(heading, 2); Serial.print(",");
    Serial.print("\"ax\":"); Serial.print(ax, 4); Serial.print(",");
    Serial.print("\"ay\":"); Serial.print(ay, 4); Serial.print(",");
    Serial.print("\"az\":"); Serial.print(az, 4); Serial.print(",");
    Serial.print("\"gx\":"); Serial.print(gx, 4); Serial.print(",");
    Serial.print("\"gy\":"); Serial.print(gy, 4); Serial.print(",");
    Serial.print("\"gz\":"); Serial.print(gz, 4);
    Serial.println("}");
  }
}

/**
 * Configures the MPU6050 by waking it up from sleep mode.
 */
void initMPU6050() {
  Wire.beginTransmission(MPU6050_ADDR);
  Wire.write(MPU6050_PWR_MGMT_1);
  Wire.write(0); // Set to 0 to wake up the MPU-6050
  Wire.endTransmission(true);
  delay(100); // Wait for sensor to stabilize
}

/**
 * Collects gyroscope samples while stationary to calculate and set calibration biases.
 */
void calibrateGyro() {
  const int calibrationSamples = 200;
  float sumX = 0.0;
  float sumY = 0.0;
  float sumZ = 0.0;
  int validSamples = 0;

  for (int i = 0; i < calibrationSamples; i++) {
    float taX, taY, taZ, tgX, tgY, tgZ;
    if (readSensorData(taX, taY, taZ, tgX, tgY, tgZ)) {
      // Add back the uncalibrated gyro values to sum them up
      sumX += tgX;
      sumY += tgY;
      sumZ += tgZ;
      validSamples++;
    }
    delay(5);
  }

  if (validSamples > 0) {
    gyroBiasX = sumX / (float)validSamples;
    gyroBiasY = sumY / (float)validSamples;
    gyroBiasZ = sumZ / (float)validSamples;
  }
}

/**
 * Reads raw accelerometer and gyroscope data from MPU6050 and converts them to physical units.
 * Returns true if the read was successful, false otherwise.
 */
bool readSensorData(float &ax_out, float &ay_out, float &az_out, float &gx_out, float &gy_out, float &gz_out) {
  // Read 14 bytes starting from ACCEL_XOUT_H (accelerometer, temperature, gyroscope)
  Wire.beginTransmission(MPU6050_ADDR);
  Wire.write(MPU6050_ACCEL_XOUT_H);
  if (Wire.endTransmission(false) != 0) {
    return false; // I2C Transmission failed
  }
  
  if (Wire.requestFrom(MPU6050_ADDR, 14, true) != 14) {
    return false; // Failed to receive 14 bytes
  }
  
  int16_t rawAx = (Wire.read() << 8) | Wire.read();
  int16_t rawAy = (Wire.read() << 8) | Wire.read();
  int16_t rawAz = (Wire.read() << 8) | Wire.read();
  
  // Skip temperature bytes
  Wire.read(); 
  Wire.read();
  
  int16_t rawGx = (Wire.read() << 8) | Wire.read();
  int16_t rawGy = (Wire.read() << 8) | Wire.read();
  int16_t rawGz = (Wire.read() << 8) | Wire.read();
  
  // Convert raw values to physical units (g for accel, deg/s for gyro)
  ax_out = (float)rawAx / ACCEL_SCALE;
  ay_out = (float)rawAy / ACCEL_SCALE;
  az_out = (float)rawAz / ACCEL_SCALE;
  
  // Convert gyro and subtract calibration biases
  gx_out = ((float)rawGx / GYRO_SCALE) - gyroBiasX;
  gy_out = ((float)rawGy / GYRO_SCALE) - gyroBiasY;
  gz_out = ((float)rawGz / GYRO_SCALE) - gyroBiasZ;

  return true;
}

/**
 * Calculates pitch and roll using a complementary filter.
 * 
 * The complementary filter combines:
 * 1. Gyroscope integration: High-pass filtered. Accurate in the short term, but drifts over time.
 *    - Gyroscope Y (gy) is integrated for pitch.
 *    - Gyroscope X (gx) is integrated for roll.
 * 2. Accelerometer tilt: Low-pass filtered. Noisy in the short term due to movement, but stable in the long term.
 * 
 * Formula: Angle = ALPHA * (Angle + GyroRate * DT) + (1 - ALPHA) * AccelAngle
 */
void updateComplementaryFilter(float ax, float ay, float az, float gx, float gy) {
  // Calculate pitch and roll angles from accelerometer data
  // pitch = atan2(-ax, sqrt(ay^2 + az^2))
  // roll = atan2(ay, az)
  float accelPitch = atan2(-ax, sqrt(ay * ay + az * az)) * RAD_TO_DEG_CONST;
  float accelRoll = atan2(ay, az) * RAD_TO_DEG_CONST;
  
  // Apply complementary filter with corrected axis mapping:
  // Gyro Y integrates into pitch, Gyro X integrates into roll.
  pitch = ALPHA * (pitch + gy * DT) + (1.0 - ALPHA) * accelPitch;
  roll = ALPHA * (roll + gx * DT) + (1.0 - ALPHA) * accelRoll;

  // Safety clamp: bounds output to a generous realistic wrist range so an
  // overdriven simulator (or sensor glitch) can't produce nonsense values.
  pitch = constrain(pitch, -120.0, 120.0);
  roll = constrain(roll, -120.0, 120.0);
}

/**
 * Reads the potentiometer value and maps it to a simulated heading (0 to 360 degrees).
 */
float readHeading() {
  int rawPot = analogRead(POT_PIN);
  // ESP32 ADC is 12-bit (0 - 4095)
  float heading = (float)rawPot * 360.0 / 4095.0;
  return heading;
}