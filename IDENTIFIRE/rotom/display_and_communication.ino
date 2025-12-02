#include <Wire.h>
#include <LiquidCrystal_I2C.h>
#include <stdint.h>
#include <SPI.h>
#include <SD.h>

// ========================
// LCD + MENU DEFINITIONS
// ========================
#define LCD_I2C_ADDR 0x27
LiquidCrystal_I2C lcd(LCD_I2C_ADDR, 20, 4);

#define BTN_UP      3
#define BTN_DOWN    2
#define BTN_SELECT  4

#define DEBOUNCE_MS 50

// Application states
enum AppState {
  STATE_MENU,
  STATE_TEST_RUNNING,
  STATE_TEST_RESULT,
  WASTE_MANAGEMENT,
  STATE_BATTERY_LEVEL,
  IDLE,
};

AppState state = STATE_MENU;

uint8_t menu_index = 0;
const uint8_t menu_count = 4;

const char* menu_items[] = {
  "Start Test",
  "Latest Result",
  "Battery Level",
  "Waste Management"
};

uint8_t result_page = 0;
const uint8_t RESULT_PAGES = 4;

// ========================
// BATTERY MONITOR SETTINGS
// ========================
const int BATTERY_PIN = A0;
const float R1 = 180000.0;
const float R2 = 36000.0;
const float ADC_REF = 5.0;
const int ADC_RES = 1023;
const float V_MIN = 10.5;
const float V_MAX = 12.6;

const int warm = 40;
int temp;

File result_SD_card;

const int chipSelect = 10;

//
int response;
int ACK = 1;
int STOP_ACK = 1;
volatile int communication_counter;

// ========================
// BUTTON DEBOUNCE
// ========================
struct Button {
  uint8_t pin;
  uint8_t last_state;
  uint8_t stable_state;
  uint32_t last_change;
};

Button buttons[3] = {
  {BTN_UP, HIGH, HIGH, 0},
  {BTN_DOWN, HIGH, HIGH, 0},
  {BTN_SELECT, HIGH, HIGH, 0},
};

void buttons_init() {
  pinMode(BTN_UP, INPUT_PULLUP);
  pinMode(BTN_DOWN, INPUT_PULLUP);
  pinMode(BTN_SELECT, INPUT_PULLUP);
}

bool button_was_pressed(uint8_t i) {
  Button *b = &buttons[i];
  uint8_t reading = digitalRead(b->pin);
  uint32_t now = millis();

  if (reading != b->last_state) {
    b->last_change = now;
  }

  if ((now - b->last_change) > DEBOUNCE_MS) {
    if (reading != b->stable_state) {
      b->stable_state = reading;
      if (b->stable_state == LOW) {
        b->last_state = reading;
        return true;
      }
    }
  }

  b->last_state = reading;
  return false;
}

// ========================
// TEST RESULT STRUCTURES
// ========================
#define ARRAY_SIZE 5

volatile int statusflag = 0;

struct resultPayload {
  float averageRos;
  float peakRos;
  float burnedPercentage;
  char burnSetting[10];
  int8_t ignitionTime;
};

resultPayload recievedData;
resultPayload data_array[ARRAY_SIZE];
int array_counter = 0;
int array_counter_counter = 0;

// ========================
// BATTERY PERCENT FUNCTION
// ========================
int getBatteryPercent() {
  int adcValue = analogRead(BATTERY_PIN);
  float vADC = (adcValue * ADC_REF) / ADC_RES;
  float vBAT = vADC * ((R1 + R2) / R2);

  int percent = ((vBAT - V_MIN) / (V_MAX - V_MIN)) * 100.0;
  if (percent > 100) percent = 100;
  if (percent < 0) percent = 0;

  return percent;
}

// ========================
// LCD HELPERS
// ========================
void printBatteryCorner() {
  int pct = getBatteryPercent();
  lcd.setCursor(16, 0);
  lcd.print(pct);
  lcd.print("% ");
}

void menu_show() {
  lcd.clear();

  int start_index = 0;
  if (menu_index >= 4) start_index = menu_index - 3;

  for (int i = 0; i < 4; i++) {
    int idx = start_index + i;
    if (idx >= menu_count) break;

    lcd.setCursor(0, i);
    lcd.print(idx == menu_index ? "> " : "  ");
    lcd.print(menu_items[idx]);
  }

  printBatteryCorner();
}

void computeAverages(float &avgAvgRos, float &avgPeakRos, float &avgBurned, float &avgIgnition, char *commonSetting) {
    int count = array_counter_counter;  
    if (count == 0) count = array_counter;  
    if (count == 0) return;

    float sumAvg = 0, sumPeak = 0, sumBurn = 0, sumIgn = 0;

    // Track most common burnSetting
    char settings[ARRAY_SIZE][5];
    int freq[ARRAY_SIZE] = {0};

    for (int i = 0; i < count; i++) {
        sumAvg  += data_array[i].averageRos;
        sumPeak += data_array[i].peakRos;
        sumBurn += data_array[i].burnedPercentage;
        sumIgn  += data_array[i].ignitionTime;

        strcpy(settings[i], data_array[i].burnSetting);
    }

    // Find most common burnSetting
    int bestIndex = 0;
    for (int i = 0; i < count; i++) {
        freq[i] = 1;
        for (int j = i + 1; j < count; j++) {
            if (strcmp(settings[i], settings[j]) == 0) {
                freq[i]++;
            }
        }
        if (freq[i] > freq[bestIndex]) bestIndex = i;
    }

    strcpy(commonSetting, settings[bestIndex]);

    avgAvgRos   = sumAvg  / count;
    avgPeakRos  = sumPeak / count;
    avgBurned   = sumBurn / count;
    avgIgnition = sumIgn  / count;
}

void show_latest_result_page() {
  lcd.clear();

  if (array_counter == 0) {
    lcd.setCursor(0, 0);
    lcd.print("No test results.");
    lcd.setCursor(0, 3);
    lcd.print("> Return");
    return;
  }

  int lastIndex = (array_counter == 0) ? ARRAY_SIZE - 1 : array_counter - 1;
  resultPayload &r = data_array[lastIndex];

  if (result_page == 0) {
    lcd.setCursor(0, 0);
    lcd.print("Latest Result");

    lcd.setCursor(0, 1);
    lcd.print(F("Avg: "));
    lcd.print(r.averageRos, 2);
    lcd.print(F(" cm^2/s"));

    lcd.setCursor(0, 2);
    lcd.print(F("Peak: "));
    lcd.print(r.peakRos, 2);
     lcd.print(F(" cm^2/s"));

    lcd.setCursor(0, 3);
    lcd.print("> More Details");

  } else if (result_page == 1) {

    lcd.setCursor(0, 0);
    lcd.print(F("Burn: "));
    lcd.print(r.burnedPercentage, 1);
    lcd.print(F("%"));

    lcd.setCursor(0, 1);
    lcd.print(F("Setting:"));
    lcd.print(r.burnSetting);

    lcd.setCursor(0, 2);
    lcd.print(F("Ignite: "));
    lcd.print(r.ignitionTime);
    lcd.print(F(" s"));

    lcd.setCursor(0, 3);
    lcd.print("> Avg results");
  }

  else if (result_page == 2){
    float aAvg, aPeak, aBurn, aIgn;
    char commonSet[5];
    
    computeAverages(aAvg, aPeak, aBurn, aIgn, commonSet);

    lcd.setCursor(0, 0);
    lcd.print("Avg of last ");
    lcd.print(array_counter_counter);
    lcd.print(" tests");

    lcd.setCursor(0, 1);
    lcd.print("Avg: ");
    lcd.print(aAvg, 2);

    lcd.setCursor(0, 2);
    lcd.print("Peak: ");
    lcd.print(aPeak, 2);

    lcd.setCursor(0, 3);
    lcd.print("> Next page");
  }
  else if (result_page == 3){
    
    float aAvg, aPeak, aBurn, aIgn;
    char commonSet[5];
    
    computeAverages(aAvg, aPeak, aBurn, aIgn, commonSet);

    lcd.setCursor(0, 0);
    lcd.print("Avg burn %: ");
    lcd.print(aBurn, 2);

    lcd.setCursor(0, 1);
    lcd.print("Avg ign time: ");
    lcd.print(aIgn, 2);

    lcd.setCursor(0, 2);
    lcd.print("> Return");
  }

  printBatteryCorner();
}



// ========================
// NON-BLOCKING TEST LOGIC
// ========================
bool handle_test_state() {
  bool flag = false;
  switch (statusflag) {

    case 0:
    
          {
            communication_counter = 0;
            while (communication_counter < 100){
             // Serial.print(" Comm error 324");
             Serial.print(statusflag);
             Serial.print(" ");
             Serial.println(communication_counter);

            if (Wire.available()) {Wire.read();}
            Wire.beginTransmission(0x10);
            Wire.write(1);
            Wire.endTransmission();
            Wire.requestFrom(0x10, 1);

            if (Wire.available()) statusflag = Wire.read();

            if (statusflag != 0) { break; }
            communication_counter += 1;

            if (communication_counter == 100){
              flag = true;
            }
            //break;
            }
            break;
          }
    case 1:
    case 2:
    case 3:
    case 4:
    case 32:
    case 6: {
      if (Wire.available()) {Wire.read();}
      Wire.beginTransmission(0x10);
      Wire.write(1);
      Wire.endTransmission();
      Wire.requestFrom(0x10, 1);

      if (Wire.available()) statusflag = Wire.read();
      communication_counter = 0;
      break;
    }

    case 5:  // Not ignited
      lcd.clear();
      lcd.setCursor(0, 0);
      lcd.print(F("Sample not ignited"));
      delay(3000);
      state = WASTE_MANAGEMENT;
      menu_show();
      statusflag = 9;
      break;

    case 7: { // Full result available
      Wire.beginTransmission(0x10);
      Wire.write(2);
      Wire.endTransmission();
      delay(20);

      Wire.requestFrom(0x10, sizeof(resultPayload));
      uint8_t *p = (uint8_t*)&recievedData;

      for (int i = 0; i < sizeof(recievedData); i++)
        if (Wire.available()) p[i] = Wire.read();

      data_array[array_counter] = recievedData;
      array_counter = (array_counter + 1) % ARRAY_SIZE;
      if (array_counter_counter < ARRAY_SIZE) {array_counter_counter += 1;}

      resultPayload &r = recievedData;
      result_SD_card = SD.open("test.txt", FILE_WRITE);

      //while (!result_SD_card){
      //  result_SD_card = SD.open("resultfile.txt", FILE_WRITE);
     // }

      result_SD_card.print("Test result: ");
      result_SD_card.print("Average rate of spread [cm^2/s]: ");
      result_SD_card.print(r.averageRos);
      result_SD_card.print(", ");
      result_SD_card.print("Peak rate of spread [cm^2/s]: ");
      result_SD_card.print(r.peakRos);
      result_SD_card.print(", ");
      result_SD_card.print("Burned percentage [%]: ");
      result_SD_card.print(r.burnedPercentage);
      result_SD_card.print(", ");
      result_SD_card.print("Burn: ");
      result_SD_card.print(r.burnSetting);
      result_SD_card.print(", ");
      result_SD_card.print("Ignition time [s]: ");
      result_SD_card.println(r.ignitionTime);
      result_SD_card.close();

      lcd.clear();
      lcd.setCursor(0, 0);
      lcd.print(F("Test Completed!"));
      lcd.setCursor(0,2);
      lcd.print(F("Results available"));
      lcd.print(F("in 'Latest Results'"));
      delay(3000);

      state = WASTE_MANAGEMENT;
      menu_show();
      statusflag = 9;
      break;
    }

    case 9:
    default:
      break;
  }

  if (flag) { return true; } else  { return false; }
}

bool send_message_to_sample(int message) {
  ACK = 1;
  communication_counter = 0;
  while (ACK != 0 && communication_counter < 10) { 
    Wire.beginTransmission(0x11); 
    Wire.write(message);  
    ACK = Wire.endTransmission();
    //Serial.print("MEDDELANDET SOM SKICKAS ÄR: ");
    //Serial.println(message);
    delay(40);
    communication_counter += 1;
  }
  if (communication_counter == 10){
    return true;
  } 
  return false;     
}

void request_status_from_sample(int wanted_response) {
  do
  {
    Wire.requestFrom(0x11, 1);
    response = Wire.read();
    switch(response) {
      //form positioned
      case 3: 
        //form ready for sample
        //Serial.println("form ready for sample");
        break;
      
      //form not positioned and not moving
      case 4:
        //error message
        //Serial.println("form not positioned and not moving");
        break;

      //form not positioned but moving
      case 5:
        //wait
       // Serial.println("form not positioned but moving");
        break;
      
      //waste management done
      case 6:
        //everything done
        //Serial.println("waste management done");
        break;

      //waste management but form not moving
      case 7:
        //wait
        //Serial.println("waste management but form not moving");
        break;
      
      default:
       // Serial.println("Unknown");
        break;
    }
    delay(100);
  } 
  while (response != wanted_response);
}

bool get_in_position(){
  if (send_message_to_sample(1)){
    return true;
  }
  request_status_from_sample(3);
  send_message_to_sample(0);
  return false;
}

bool check_temperature(){
  /*Wire.beginTransmission(0x12);
  Wire.write(2);
  delay(20);*/

  communication_counter = 0;
  temp = -1;
  while (communication_counter < 10 && temp == -1)
    {
    Wire.requestFrom(0x12, 1);
    temp = Wire.read();
    //Serial.println(temp);
    delay(20);
    communication_counter += 1;
    }

  if (communication_counter == 10) {
    lcd.clear();
    lcd.setCursor(0,0);
    lcd.print("Timeout due to");
    lcd.setCursor(0,1);
    lcd.print("communication error");
    delay(3000);
    return true;
  }
  if (temp < warm){
    return false;
  }
  else{
    lcd.clear();
    lcd.print("Too warm for test,");
    lcd.setCursor(0, 1);
    lcd.print("must cool down");
    lcd.setCursor(0, 2);
    lcd.print("Temperature: ");
    lcd.print(temp);
    lcd.print(" degC");
    delay(3000);
    menu_show();
    return true;
  }
}



// ========================
// STATE MACHINE
// ========================
void state_machine() {

  switch (state) {

    // ---------------------------
    // MAIN MENU
    // ---------------------------
    case STATE_MENU:

      if (button_was_pressed(0)) { // UP
        menu_index = (menu_index == 0) ? menu_count - 1 : menu_index - 1;
        menu_show();
      }

      if (button_was_pressed(1)) { // DOWN
        menu_index = (menu_index + 1) % menu_count;
        menu_show();
      }

      if (button_was_pressed(2)) { // SELECT
        if (menu_index == 0) {
          // Start test
          statusflag = 0;
          state = STATE_TEST_RUNNING;
          lcd.clear();
          lcd.setCursor(0, 0);
          lcd.print(F("Test Running..."));

        } else if (menu_index == 1) {
          // Latest result
          result_page = 0;
          state = STATE_TEST_RESULT;
          show_latest_result_page();

        } else if (menu_index == 2) {
          // Battery only screen
          state = STATE_BATTERY_LEVEL;
          lcd.clear();
          lcd.setCursor(0, 0);
          lcd.print(F("Battery Level"));
          lcd.setCursor(0, 1);
          lcd.print(getBatteryPercent());
          lcd.print("%");
          lcd.setCursor(0, 3);
          lcd.print("> Return");

        } else if (menu_index == 3) {
          lcd.clear();
          lcd.print(F("Emptying burn box.."));
          state = WASTE_MANAGEMENT;
        }
      }
      break;

    // ---------------------------
    // TEST RUNNING SCREEN
    // ---------------------------
    case STATE_TEST_RUNNING:
      if (check_temperature()){
        state = STATE_MENU;
        menu_show();
        break;
      }
      if (get_in_position()){
        lcd.clear();
        lcd.setCursor(0,0);
        lcd.print(F("Waste system"));
        lcd.setCursor(0,1);
        lcd.print(F("communication error"));
        delay(3000);
        state = STATE_MENU;
        menu_show();
        break;
        }
      if (handle_test_state()){
        Serial.print(" Error 624");
        lcd.clear();
        lcd.setCursor(0,0);
        lcd.print(F("Fire system"));
        lcd.setCursor(0,1);
        lcd.print(F("communication error"));
        delay(3000);
        state = STATE_MENU;
        menu_show();
        break;
      }
      lcd.print(F("Test in progress.."));
      state = IDLE;
      break;

    case WASTE_MANAGEMENT:
      if (send_message_to_sample(2)){
        lcd.clear();
        lcd.setCursor(0,0);
        lcd.print(F("Waste system"));
        lcd.setCursor(0,1);
        lcd.print(F("communication error"));
        delay(3000);
        state = STATE_MENU;
        menu_show();
        break;
      }
      request_status_from_sample(6);
      send_message_to_sample(0);
      state = STATE_MENU;
      menu_show();
      break;

    case STATE_BATTERY_LEVEL:
      if (button_was_pressed(2)) {           // SELECT
        state = STATE_MENU;
        menu_show();
      }


      break;
    
    case IDLE:
    {

      //get_in_position();
      if (handle_test_state() == true){
        Serial.print("ERror 671");
        lcd.clear();
        lcd.setCursor(0,0);
        lcd.print(F("Fire system"));
        lcd.setCursor(0,1);
        lcd.print(F("communication error"));
        delay(3000);
        state = STATE_MENU;
        menu_show();
        break;
      }
      //Serial.println(statusflag);
    }
    break;

    // ---------------------------
    // LATEST RESULT SCREEN
    // ---------------------------
    case STATE_TEST_RESULT:

      if (button_was_pressed(0)) {
        result_page = (result_page == 0) ? RESULT_PAGES - 1 : result_page - 1;
        show_latest_result_page();
      }

      if (button_was_pressed(1)) {
        result_page = (result_page + 1) % RESULT_PAGES;
        show_latest_result_page();
      }

      if (button_was_pressed(2)) {
        state = STATE_MENU;
        menu_show();
      }

      break;
  }
}

// ========================
// SETUP + LOOP
// ========================
void setup() {
  Serial.begin(9600);
  if(!SD.begin()) { Serial.print("no");}
  Wire.begin();
  lcd.init();
  lcd.backlight();
  buttons_init();
  menu_show();
}

void loop() {
  state_machine();
}
