#include <Arduino.h>


#include <SoftwareSerial.h>
#include <Wire.h>


// ------------------------------------------------------------
// Pins for software UART to valve control
// ------------------------------------------------------------
#define VALVE_RX 8           // R3 RX (receives from valve)
#define VALVE_TX 9           // R3 TX (sends to valve)

#define BLUETOOTH_RX 10           // R3 RX (receives from valve)
#define BLUETOOTH_TX 11           // R3 TX (sends to valve)

#define I2C_SLAVE_ADDR 0x10  // rotom Arduino will use this address

SoftwareSerial valveSerial(VALVE_RX, VALVE_TX);  // RX, TX


// ------------------------------------------------------------
// Global Variables
// ------------------------------------------------------------
int state = 0;
int burnAttempts = 0;
bool burnActive = false;
char ack = '0';
volatile uint8_t i2cCommand = 0;  // only this variable is touched in ISR
int i2cResult = 2;
int stepTime = 0;
String burnSetting;
int request;
static bool sent = false;
int cameraDelay = 0;

// ------------------------------------------------------------
// Burn sequences
// ------------------------------------------------------------
struct BurnStep {
  const int time;
  const int dutyCycle;
};

struct resultPayload {
  float averageRos;
  float peakRos;
  float burnedPercentage;
  char burnSetting[10];
  int8_t ignitionTime;
};

resultPayload data;

BurnStep dryBurns[] = {
  { 5000, 200 } // 50%
};

BurnStep mediumBurns[] = {
  { 5000, 210 }
};

BurnStep wetBurns[] = {
  { 5000, 255 }
};

void receiveEvent(int count) {
  if (count < 1) return;
  i2cCommand = Wire.read();  // just grab the byte, nothing else!
  // DO NOT print, delay, or do heavy work here!
  
}

void requestEvent() {

  if (i2cCommand == 2) {
    Wire.write((uint8_t*)&data,sizeof(resultPayload));
    state = 1;
  }
  else{
    Wire.write(state); //If state is 5 no data, if state is 7 struct
  }
}

// Start a burn cycle
void startCycle(uint16_t timeMS, uint8_t duty) {
  String cmd = String("1\n") + String(timeMS) + "\n" + String(duty) + "\n";
  valveSerial.println(cmd);
  burnActive = true;

  Serial.print("[BURN START] Time: ");
  Serial.print(timeMS);
  Serial.print(" ms, Duty: ");
  Serial.print(duty);
  Serial.println(" (255=max)");
}

// ------------------------------------------------------------
// Burn sequence function (with nice logging)
// ------------------------------------------------------------
void runBurnSequence(BurnStep* sequence, int steps, int& burnStep, const char* moistureLevel) {

  if (burnStep >= steps) {
    burnStep = 0;
    state++;
    Serial.print("[");
    Serial.print(moistureLevel);
    Serial.println(" SEQUENCE] No ignition after all steps → moving to next moisture level");
    return;
  }

  if (!burnActive) {
    cameraDelay = sequence[burnStep].time - 5000;
    delay(800);
    delay(cameraDelay);
    Serial.println("[CAMERA] Requesting start...");
    Serial1.println("start");

    delay(500);

    Serial.print("[IGNITION ATTEMPT ");
    Serial.print(burnStep + 1);
    Serial.print("/");
    Serial.print(steps);
    Serial.print("] ");
    Serial.print(moistureLevel);
    Serial.print(" | Step ");
    Serial.print(burnStep);
    Serial.print(" → ");
    Serial.print(sequence[burnStep].time);
    Serial.print(" ms @ duty ");
    Serial.println(sequence[burnStep].dutyCycle);
    
    startCycle(sequence[burnStep].time, sequence[burnStep].dutyCycle);
   

  } else if (1) {
    //ack = valveSerial.read();
    delay(5000);
    ack = '2'; 

    if (ack == '2') {
      Serial.println("[VALVE] Burn step completed → waiting 10 s for flame detection");

      delay(10000);  // stabilization delay
      Serial1.read();

      Serial.println("[CAMERA] Querying fire status after 10 s delay");
      Serial1.println("FIRESTATUS");

      
      while (Serial1.available() <= 0) {}
      bool fire = Serial1.parseInt();
      Serial1.read();


      if (fire) {
        state = 6;
        burnActive = false;
        burnSetting = moistureLevel;
        Serial.println("SUCCESS! Sample is burning → waiting for Raspberry Pi analysis data");
        return;
      } else {
        Serial.println("[NO FIRE] No flame detected after 10 s → ramping up power");

        // Stop and reset camera for next attempt
        Serial1.println("stop");
        while (Serial1.available() <= 0) {}
        bool stopOk = Serial1.parseInt();
        Serial1.read();

        if (!stopOk) {
          state = -1;
          Serial.println("[ERROR] Camera failed to stop!");
          return;
        }

        Serial1.println("reset");
        while (Serial1.available() <= 0) {}
        bool resetOk = Serial1.parseInt();
        Serial1.read();

        if (resetOk) {
          burnAttempts++;
          burnStep++;
          
          burnActive = false;
          Serial.print("[NEXT ATTEMPT] Total ignition attempts so far: ");
          Serial.println(burnAttempts);
        } else {
          state = -1;
          Serial.println("[ERROR] Camera reset failed!");
        }
      }
    }
  }
}

// ------------------------------------------------------------
// Setup
// ------------------------------------------------------------
void setup() {
  Serial.begin(9600);
  Serial1.begin(9600);
  valveSerial.begin(9600);
  
  // I2C Setup
  Wire.begin(I2C_SLAVE_ADDR);
  Wire.onReceive(receiveEvent);
  Wire.onRequest(requestEvent);

  Serial.println();
  Serial.println("========================================");
  Serial.println("    R3 - Flame Spread Test Controller   ");
  Serial.println("          Software UART Simulation      ");
  Serial.println("========================================");
  Serial.println();

  Serial.println("[SYSTEM] Waiting for Raspberry Pi handshake...");

  while (Serial1.available() <= 0) {}
  bool ping = Serial1.parseInt();
  Serial1.read();

  if (!ping) {
    Serial.println("[ERROR] Raspberry Pi initial ping failed!");
    state = -1;
    return;
  }

  Serial1.println("PING");
  while (Serial1.available() <= 0) {}
  ping = Serial1.parseInt();
  Serial1.read();

  if (!ping) {
    state = -1;
    Serial.println("[ERROR] Handshake failed – no response to PING");
  } else {
    state = 1;
    Serial.println("✓ Handshake successful – system ready!");
    Serial.println();
  }
}

// ------------------------------------------------------------
// Main loop
// ------------------------------------------------------------
void loop() {
  switch (state) {

    case 1:
      {
        static bool printed = false;
        if (!printed) {
          Serial.println("[STATE 1] Idle – waiting for I2C START command...");
          printed = true;
          burnAttempts = 0;

        }
        
        if (i2cCommand == 1) {
          state = 2;
          Serial.println("[I2C] START command received → beginning test");
          printed = false;
        }
        break;
      }

    case 2:
      {
        i2cCommand = 0;
        static int burnStep = 0;
        stepTime += dryBurns[0].time;
        runBurnSequence(dryBurns, 1, burnStep, "DRY");
        break;
      }

    case 3:
      {
        static int burnStep = 0;
        stepTime += mediumBurns[0].time;
        runBurnSequence(mediumBurns, 1, burnStep, "MEDIUM");
        break;
      }

    case 4:
      {
        static int burnStep = 0;
        stepTime += wetBurns[0].time;
        runBurnSequence(wetBurns, 1, burnStep, "WET");
        state = 6;
        
        break;
      }

    case 5:
      Serial.println("[RESULT] Sample never ignited after all sequences → test failed");
      delay(5000);
      if(i2cCommand == 1){
        i2cCommand= 0;
        state = 1;
      }
    
      break;

    case 6:
      Serial.println("[STATE 6] Sample is burning – waiting for Raspberry Pi to send measurement data...");
      if (Serial1.available() > 0) {
        String check = Serial1.readStringUntil(',');
        if (check == "status:complete") {

          // Skip "duration_sec:" label
          Serial1.find("duration_sec:");
          float duration = Serial1.parseFloat(); // Duration

          // Skip "final_burn_percentage:" label
          Serial1.find("final_burn_percentage:");
          data.burnedPercentage = Serial1.parseFloat();

          // Skip "avg_ros_cm2_per_sec:" label
          Serial1.find("avg_ros_cm2_per_sec:");
          data.averageRos = Serial1.parseFloat();

          // Skip "max_ros_cm2_per_sec:" label
          Serial1.find("max_ros_cm2_per_sec:");
          data.peakRos = Serial1.parseFloat();

          // Skip "max_temp_celsius:" label (optional)
          Serial1.find("max_temp_celsius:");
          float maxTemp = Serial1.parseFloat();
          data.ignitionTime = stepTime;
          burnSetting.toCharArray(data.burnSetting, sizeof(data.burnSetting));
          Serial1.read();


        } else {
          Serial.println("[ERROR] Data header was not correct");
          Serial.print("Header: ");
          Serial.print(check);
          state = -1;
          return;
        }
        Serial.println("──────────────────────────────────────────────────");
        Serial.println("   Measurement Results:");
        Serial.println("──────────────────────────────────────────────────");
        Serial.print("   • Average Rate of Spread (ROS)   : ");
        Serial.print(data.averageRos, 4);
        Serial.println(" cm/s");

        Serial.print("   • Peak Rate of Spread            : ");
        Serial.print(data.peakRos, 4);
        Serial.println(" cm/s");

        Serial.print("   • Burned Area Percentage         : ");
        Serial.print(data.burnedPercentage, 2);
        Serial.println(" %");

        Serial.print("   • Moisture Level Setting         : ");
        Serial.println(data.burnSetting);

        Serial.print("   • Ignition Time (total ramp)    : ");
        Serial.print(data.ignitionTime);
        Serial.println(" ms");

        Serial.print("   • Total Ignition Attempts       : ");
        Serial.println(burnAttempts);

        Serial.println("──────────────────────────────────────────────────");
        Serial.println("   Test completed successfully!");
        Serial.println("==================================================");
        Serial.println();

        state = 7;  
      }
      burnActive = false;
      break;

    case 7:
    {
        if (!sent) {
            Serial.println("[STATE 7] Test complete – sending summary to rotom");
            sent = true;
        }
        sent = false;
        delay(1000);
        state = 1;
        break;
    }

    case -1:
      Serial.println("!!! SYSTEM IN ERROR STATE – HALTED !!!");
      delay(1000);
      break;

    default:
      Serial.println("[ERROR] Unknown state!");
      delay(1000);
      break;
  }



  

  // Small delay to keep serial monitor readable
  delay(100);
}
