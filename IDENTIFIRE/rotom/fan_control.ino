#include <Adafruit_MAX31865.h>
#include <Wire.h>
#define MAX31865_CS 10   // Chip select on D10

// Create MAX31865 object using hardware SPI
Adafruit_MAX31865 rtd = Adafruit_MAX31865(MAX31865_CS);

#define RTD_NOMINAL 100.0
#define REF_RESISTOR 430.0   // Default on Adafruit MAX31865

const int fanControlPin = 3;
const float TEMP_REF = 20.0;
const float max_speed_temp = 80.0;
const float P_fancontrol = (255 / (max_speed_temp - TEMP_REF));

volatile float temperature;

void setup() {
  Serial.begin(9600);
  pinMode(fanControlPin, OUTPUT);
  delay(500);

  Serial.println("MAX31865 PT100 Reader (3-wire mode)");

  // IMPORTANT: 3-wire mode
  rtd.begin(MAX31865_3WIRE);

  Wire.begin(0x12);
  //Wire.onReceive(sendHi);
  Wire.onRequest(sendTemp);
}

void loop() {

  temperature = rtd.temperature(RTD_NOMINAL, REF_RESISTOR);

  Serial.print("Temperature: ");
  Serial.print(temperature);
  Serial.println(" °C");

  uint16_t raw = rtd.readRTD();
  Serial.print("RTD raw: ");
  Serial.println(raw);

    if (temperature < TEMP_REF) {
    analogWrite(fanControlPin, 0);
    Serial.print("Brrrrr cold");
  } 
  else if (temperature > max_speed_temp) {
    Serial.print("uhhhhhh warm");
    analogWrite(fanControlPin, 255);
  }
  else {
    Serial.print("Normal temp");
    analogWrite(fanControlPin, int((temperature - TEMP_REF)*P_fancontrol));
  }


  delay(1000);
}

void sendHi(){

}

void sendTemp(){
  int temp = temperature;
  Wire.write(temp);
}