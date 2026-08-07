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

// Function declarations
void initMPU6050();
void readSensorData(float &ax, float &ay, float &az, float &gx, float &gy, float &gz);
void updateComplementaryFilter(float ax, float ay, float az, float gx, float gy);
float readHeading();

void setup() {
  Serial.begin(115200);
  
  // Initialize I2C on specified pins
  Wire.begin(I2C_SDA_PIN, I2C_SCL_PIN);
  
  // Initialize MPU6050
  initMPU6050();
  
  // Configure potentiometer pin
  pinMode(POT_PIN, INPUT);
  
  lastSampleTime = millis();
}

void loop() {
  unsigned long currentTime = millis();
  
  // Maintain exactly 20Hz output rate (50ms interval)
  if (currentTime - lastSampleTime >= 50) {
    lastSampleTime = currentTime;
    
    float ax, ay, az;
    float gx, gy, gz;
    
    // 1. Read raw sensor values
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
}

/**
 * Reads raw accelerometer and gyroscope data from MPU6050 and converts them to physical units.
 */
void readSensorData(float &ax, float &ay, float &az, float &gx, float &gy, float &gz) {
  // Read 14 bytes starting from ACCEL_XOUT_H (accelerometer, temperature, gyroscope)
  Wire.beginTransmission(MPU6050_ADDR);
  Wire.write(MPU6050_ACCEL_XOUT_H);
  Wire.endTransmission(false);
  Wire.requestFrom(MPU6050_ADDR, 14, true);
  
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
  ax = (float)rawAx / ACCEL_SCALE;
  ay = (float)rawAy / ACCEL_SCALE;
  az = (float)rawAz / ACCEL_SCALE;
  
  gx = (float)rawGx / GYRO_SCALE;
  gy = (float)rawGy / GYRO_SCALE;
  gz = (float)rawGz / GYRO_SCALE;
}

/**
 * Calculates pitch and roll using a complementary filter.
 * 
 * The complementary filter combines:
 * 1. Gyroscope integration: High-pass filtered. Accurate in the short term, but drifts over time.
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
  
  // Apply complementary filter
  pitch = ALPHA * (pitch + gx * DT) + (1.0 - ALPHA) * accelPitch;
  roll = ALPHA * (roll + gy * DT) + (1.0 - ALPHA) * accelRoll;
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
