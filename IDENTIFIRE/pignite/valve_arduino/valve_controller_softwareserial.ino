#include <SoftwareSerial.h>


#define spark 5
#define valve 10

// RX, TX (Arduino reads on pin 9, sends on pin 8)
SoftwareSerial mySerial(9, 8);

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

  mySerial.setTimeout(10);

  TCCR1B = TCCR1B & B11111000 | B00000010;

  pinMode(spark, OUTPUT);
  pinMode(valve, OUTPUT);
}

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

    Serial.print(S);
    Serial.print(" ");
    Serial.print(T);
    Serial.print(" ");
    Serial.println(D);


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
    unsigned long elapsed = millis() - prevMillis;
    if (elapsed >= timerMax) {
      analogWrite(valve, 0);
      timerRunning = false;
      ack_status = '2';
      mySerial.write(ack_status);
    }
  }

  // Spark timer
  if (timerRunningSpark) {
    unsigned long elapsedSpark = millis() - prevMillisSpark;
    if (elapsedSpark >= timerMaxSpark) {
      analogWrite(spark, 0);
      timerRunningSpark = false;
    }
  }
}
