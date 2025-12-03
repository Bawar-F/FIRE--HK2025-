#include <SoftwareSerial.h>
#include <string.h>

#define spark 5
#define valve 10

// RX, TX (Arduino reads on pin 9, sends on pin 8)
SoftwareSerial mySerial(9, 8);

String input="";
int values[3];
int index = 0;

int state = 0;
unsigned long prevMillis = 0;
unsigned long timerMax = 5000;
bool timerRunning = false;

unsigned long prevMillisSpark = 0;
unsigned long timerMaxSpark = 1000;
bool timerRunningSpark = false;

char ack_status ='0'; //0-idle, 1-running, 2-finished

void setup() {
  mySerial.begin(9600);
  Serial.begin(9600);
  mySerial.write(ack_status);

  mySerial.setTimeout(100);

  TCCR1B = TCCR1B & B11111000 | B00000010;

  Serial.println("RESET FUNC WORKED");

  pinMode(spark, OUTPUT);
  pinMode(valve, OUTPUT);

  analogWrite(spark, 0);
  analogWrite(valve, 0);
}

void(* resetFunc) (void) = 0;

int i = 0;
char character;

void loop() {

  if (mySerial.available() > 0) {
    /* 
      S - start the cycle
      D - change duty cycle (default lowest 143)
      T - change time to burn (default 5 seconds)
      E - emergency stop

      When done, send some acknowledgment
      Example: S0, E0
    */

    // Wait for integer data to come
    //while (mySerial.available() == 0) {}
    int S = mySerial.parseInt();
    int T = mySerial.parseInt();
    int D = mySerial.parseInt();

    if (S == 3){
      analogWrite(valve, 0);
      analogWrite(spark, 0);
      timerRunning = false;
      timerRunningSpark = false;
    }
 /*
    int S = 0;
    int T = 0;
    int D = 0;

    

  while (mySerial.available()) {
    char c = mySerial.read();


    if (c == '\r') continue;     // ignore CR

    if (c == '\n') {             // got a full line
      if (input.length() > 0) {
        int number = input.toInt();
        if (index < 3) {
          values[index] = number;
          index++;
        }
      }

      input = "";                 // clear for next line

      // When we have 3 values, do something with them
      if (index == 3) {
        S = values[0];
        T = values[1];
        D = values[2];

        index = 0;  // reset for next command
      }
    }
    else {
      input += c;   // accumulate characters
    }
  }

    input = "";

*/

    Serial.print(S);
    Serial.print(" ");
    Serial.print(T);
    Serial.print(" ");
    Serial.println(D);
    Serial.println(prevMillisSpark);


    if ((S == 1) && (!timerRunning)){
      prevMillis = millis();
      prevMillisSpark = millis();
      analogWrite(spark, 255);
      analogWrite(valve, D) ;
      timerMax = T;
      state = 1;
      timerRunning = true;
      timerRunningSpark = true;
      
      ack_status = '1';
      mySerial.write(ack_status); 
    }


  }

  // Valve timer
  if (timerRunning) {
    if (millis() < prevMillis) {
      analogWrite(valve, 0);
      timerRunning = false;
      Serial.print("Valve recovery");
    }
    unsigned long elapsed = millis() - prevMillis;
    Serial.print("valve: ");
    Serial.println(elapsed);
    if (elapsed >= timerMax) {
      analogWrite(valve, 0);
      analogWrite(spark, 0);
      timerRunning = false;
      ack_status = '2';
      mySerial.write(ack_status); 
      
    }
  }

  // Spark timer
  if (timerRunningSpark) {
    if (millis() < prevMillisSpark) {
      analogWrite(spark, 0);
      timerRunningSpark = false;
      Serial.print("Spark recovery");
    }
    if (abs(millis()-prevMillisSpark) > 2500) {
      analogWrite(spark, 0);
      timerRunningSpark = false;
      Serial.print("Spark recovery");
    }
    unsigned long elapsedSpark = millis() - prevMillisSpark;
    if (elapsedSpark % 50 == 0) {Serial.println(elapsedSpark);}
    if (elapsedSpark >= timerMaxSpark) {
      analogWrite(spark, 0);
      timerRunningSpark = false;
    }
  }

}