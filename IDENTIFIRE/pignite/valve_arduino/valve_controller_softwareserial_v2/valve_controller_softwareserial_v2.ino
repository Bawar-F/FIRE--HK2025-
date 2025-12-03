#include <SoftwareSerial.h>

#define SPARK 5
#define VALVE 10

SoftwareSerial mySerial(9, 8);   // RX, TX

char ack_status = '0';

void setup() {
  Serial.begin(9600);
  mySerial.begin(9600);

  pinMode(SPARK, OUTPUT);
  pinMode(VALVE, OUTPUT);
  analogWrite(SPARK, 0);
  analogWrite(VALVE, 0);

  mySerial.write('0'); // idle
}

void loop() {

  if (mySerial.available() > 0) {

    int S = mySerial.parseInt();   // 1=start, 3=stop
    int T = mySerial.parseInt();   // ignored
    int D = mySerial.parseInt();   // duty
    mySerial.read();
    
    Serial.print("RX: ");
    Serial.print(S); Serial.print(" ");
    Serial.print(T); Serial.print(" ");
    Serial.println(D);

    // START: S=1
    if (S == 1) {
      analogWrite(SPARK, 255);
      analogWrite(VALVE, D);

      ack_status = '1';  // running
      mySerial.write(ack_status);
    }

    // STOP: S=3
    if (S == 3) {
      analogWrite(SPARK, 0);
      analogWrite(VALVE, 0);

      ack_status = '2';  // finished
      mySerial.write(ack_status);
    }
  }
}
