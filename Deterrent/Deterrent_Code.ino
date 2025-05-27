/*#include <Arduino.h>

// === Pins ===
const int ledPins[] = {4, 15, 32};           // LEDs
const int buzzerPins[] = {13, 21, 25};       // Buzzers
const int freqChoices[] = {500, 1000, 1500}; // Frequencies

// === UART ===
#define RXD2 16  // Connect to Pi TX
#define TXD2 17  // Connect to Pi RX
#define BAUD_RATE 115200

String serialBuffer = "";

void setup() {
  Serial.begin(115200); // USB debug
  Serial2.begin(BAUD_RATE, SERIAL_8N1, RXD2, TXD2); // UART with Pi
  Serial.println("ESP32 ready. Listening for TRIGGER on Serial2...");

  // Init pins
  for (int i = 0; i < 3; i++) {
    pinMode(ledPins[i], OUTPUT);
    digitalWrite(ledPins[i], LOW);
    pinMode(buzzerPins[i], OUTPUT);
    digitalWrite(buzzerPins[i], LOW);
  }
}

void loop() {
  // Read from Serial2 (UART)
  while (Serial2.available()) {
    char c = Serial2.read();
    if (c == '\n') {
      serialBuffer.trim();
      handleCommand(serialBuffer);
      serialBuffer = "";
    } else {
      serialBuffer += c;
    }
  }
}

void handleCommand(String command) {
  if (command.equalsIgnoreCase("TRIGGER")) {
    Serial.println("✅ Received TRIGGER from Pi");
    Serial2.println("ACK");  // Send acknowledgment to Raspberry Pi

    // Pick a frequency for this run
    int freq = freqChoices[random(0, 3)];
    Serial.printf("🔊 Using frequency: %d Hz\n", freq);

    // Start buzzing all buzzers
    for (int i = 0; i < 3; i++) {
      tone(buzzerPins[i], freq);
    }

    // Flash LEDs randomly for 10 seconds
    unsigned long start = millis();
    while (millis() - start < 10000) {
      int pattern = random(0, 8); // 3-bit random LED pattern
      for (int i = 0; i < 3; i++) {
        digitalWrite(ledPins[i], (pattern >> i) & 1);
      }
      delay(random(50, 150));
    }

    // Turn off everything
    for (int i = 0; i < 3; i++) {
      digitalWrite(ledPins[i], LOW);
      noTone(buzzerPins[i]);
    }

    Serial.println("✅ Deterrent sequence complete.");
  } else {
    Serial.print("❓ Unknown command: ");
    Serial.println(command);
  }
}
*/

#include <WiFi.h>
#include <HTTPClient.h>
#include <ArduinoJson.h>
#include <time.h>

// Wifi connection
const char* ssid = "azrah";            
const char* password = "yourmom:)"; 
const char* firebaseURL = "https://penguin-deterrent-64225-default-rtdb.firebaseio.com/commands/trigger_deterrent/time.json";

// GPIO pins 
const int ledPins[] = {4, 15, 32};
const int buzzerPins[] = {13, 21, 25};
const int freqChoices[] = {6000, 1000, 1500};

// UART parameters
#define RXD2 16  // Pi TX → ESP RX
#define TXD2 17  // Pi RX ← ESP TX
#define BAUD_RATE 115200
String serialBuffer = "";

// Timing for Firebase
unsigned long lastFirebaseCheck = 0;
const unsigned long firebaseInterval = 10000; // check every 10s

// Deterrent control
bool deterrentActive = false;
unsigned long deterrentStart = 0;
const unsigned long deterrentDuration = 10000; // 10s
int currentFreq = 1000;

void setup() {
  Serial.begin(115200);
  Serial2.begin(BAUD_RATE, SERIAL_8N1, RXD2, TXD2);  // UART with Pi
  Serial.println("ESP32 ready for UART and Firebase triggers");

  // Pin setup
  for (int i = 0; i < 3; i++) {
    pinMode(ledPins[i], OUTPUT);
    digitalWrite(ledPins[i], LOW);
    pinMode(buzzerPins[i], OUTPUT);
    digitalWrite(buzzerPins[i], LOW);
  }

  // Connect to wifi/hotspot
  WiFi.begin(ssid, password);
  Serial.print("Connecting to iPhone Hotspot");
  int retries = 0;
  while (WiFi.status() != WL_CONNECTED && retries < 30) {
    delay(500);
    Serial.print(".");
    retries++;
  }

  if (WiFi.status() == WL_CONNECTED) {
    Serial.println("\n✅ Connected to Hotspot");
  } else {
    Serial.println("\n❌ Failed to connect to WiFi");
  }

  // NTP time for Firebase comparison - NTP is used to synchronise clocks over the internet
  configTime(0, 0, "pool.ntp.org", "time.nist.gov");
  struct tm timeinfo;
  while (!getLocalTime(&timeinfo)) {
    Serial.println("Waiting for NTP...");
    delay(1000);
  }
}

void loop() {
  handleUART();         // Instant UART trigger
  checkFirebase();      // Periodic website check
  handleDeterrent();    // Deterrent action
}

// UART trigger handling
void handleUART() {
  while (Serial2.available()) {
    char c = Serial2.read();
    if (c == '\n') {
      serialBuffer.trim();
      if (serialBuffer.equalsIgnoreCase("TRIGGER")) { // If the sensing sends "TRIGGER"
        Serial.println("📡 UART: TRIGGER received");
        Serial2.println("ACK");                       // Send "ACK" back to sensing
        startDeterrent();
      }
      serialBuffer = "";
    } else {
      serialBuffer += c;
    }
  }
}

// Firebase trigger handling
void checkFirebase() {
  if (millis() - lastFirebaseCheck >= firebaseInterval && !deterrentActive) { // A non-blocking timing pattern instead of delay so that UART trigger can still come in when periodically checking database
    lastFirebaseCheck = millis(); 

    HTTPClient http;
    http.begin(firebaseURL);                  // Connect to Firebase
    int httpCode = http.GET();                // Send GET request

    if (httpCode == 200) {                    // Check if request was successful 
      String payload = http.getString();      // Read response
      payload.replace("\"", "");             
      Serial.println("🌐 Firebase time: " + payload); // Print timestamp

      // Convert string into time structure
      struct tm tm;
      if (strptime(payload.c_str(), "%Y-%m-%dT%H:%M:%S", &tm) != NULL) {
        time_t firebaseTime = mktime(&tm);
        time_t currentTime = time(NULL);      // Get time from ESP32
        double diff = difftime(currentTime, firebaseTime);  // Calculate time different
        Serial.printf("🕒 Time diff: %.0f seconds\n", diff);

        if (abs(diff) < 10) {
          Serial.println("🔥 Firebase: trigger detected");
          startDeterrent();
        }
      } else {
        Serial.println("❌ Failed to parse Firebase time");
      }
    } else {
      Serial.printf("❌ HTTP error: %d\n", httpCode); // If HTTP request is invalid
    }

    http.end();                               // Close connection
  }
}

// Start deterring
void startDeterrent() {
  if (deterrentActive) return;
  deterrentActive = true;
  deterrentStart = millis();
  currentFreq = freqChoices[random(0, 3)];
  Serial.printf("🚨 DETERRENT START: %d Hz\n", currentFreq);

  // Buzzers ON
  for (int i = 0; i < 3; i++) {
    tone(buzzerPins[i], currentFreq);
  }
}

// Running deterrent
void handleDeterrent() {
  if (deterrentActive) {
    if (millis() - deterrentStart >= deterrentDuration) {   // Check if deterrent duration has elapsed
      deterrentActive = false;
      for (int i = 0; i < 3; i++) {
        digitalWrite(ledPins[i], LOW);                      // Lights off
        noTone(buzzerPins[i]);                              // Buzzers off
      }
      Serial.println("✅ DETERRENT COMPLETE");
    } else {
      // Flash LEDs in random patterns; only change pattern if enough time has passed
      static unsigned long lastFlash = 0;
      if (millis() - lastFlash >= random(50, 150)) {
        lastFlash = millis(); 
        int pattern = random(0, 8);                         // Generate a random 3-bit pattern to control LEDs
        for (int i = 0; i < 3; i++) {
          digitalWrite(ledPins[i], (pattern >> i) & 1);
        }
      }
    }
  }
}

