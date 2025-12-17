//Waste management system

#include <avr/io.h>
#include <avr/interrupt.h>
#include <Wire.h>

volatile unsigned int positioning_count = 0;
volatile unsigned int positioning = 150;
volatile unsigned int distance_count = 0;
volatile unsigned int distance = 2000;
volatile unsigned int home_found = 0;
volatile unsigned int route_done = 0;
volatile unsigned int positioning_done = 0;
volatile unsigned int waste_management_done = 0;
volatile unsigned int duty_cycle;
int message = 0;  
volatile unsigned long time;
volatile unsigned int form_ready_for_sample = 0;



ISR(PCINT0_vect){
  
  //Encoder counting
  if (home_found == 0){
    positioning_count++;
 
  } else {
    distance_count++;
   
  }
  //Register current time
  time = millis();

}

ISR (INT0_vect){
  //Button interruption
  if (home_found == 0 && positioning_done == 1){ 
    home_found = 1;
   
  } else {
    if (waste_management_done == 1){
    route_done = 1; 
   
    }
    
   
  }

}

//Higher PWM when starting the route or if form gets stuck
void kick_start_PWM(){
  TCCR0A |=  (1 << COM0A1)  | (1 << WGM01)| (1 << WGM00);
  TCCR0B |= (1 << CS01) | (1 << CS00);
  duty_cycle = 250; //98 % duty cycle
  OCR0A = duty_cycle;

}

//Normal PWM signal
void normal_PWM(){
  TCCR0A |=  (1 << COM0A1)  | (1 << WGM01)| (1 << WGM00);
  TCCR0B |= (1 << CS01) | (1 << CS00);
  duty_cycle = 154; //60 % duty cycle
  OCR0A = duty_cycle;

}



void position_form() {

//Moving the form forward 
if (positioning_count < positioning){

  PORTB |= (1 << PORTB2); //Put pin 10 to high
  PORTB &=~ (1 << PORTB3); //Put pin 11 to low  
  
  //Check if the form is moving to determine PWM signal
  if (millis()-time > 500){
      //High PWM
      kick_start_PWM(); 
      delay(50);
    //Normal PWM
    } else {
      normal_PWM();
    }
  
//Moving the form backwards until button is pressed  
} else{

  while (home_found == 0){
    PORTB |= (1 << PORTB3); //Put pin 11 to high
    PORTB &=~ (1 << PORTB2); //Put pin 10 to low
    //Check if the form is moving to determine PWM signal
    if (millis()-time > 500){
      //High PWM
      kick_start_PWM(); 
      delay(50);
    //Normal PWM
    } else {
      normal_PWM();
    }

   positioning_done = 1;

    
  }



}


}





void waste_management(){
  
//Moving the form forward 
if (distance_count < distance){
    //High PWM in the beginning of route
    if (distance_count < distance*0.4){
    kick_start_PWM();
   
  } else {
    
    //Check if the form is moving to determine PWM signal
    if (millis()-time > 500){
      //High PWM
      kick_start_PWM(); 
      delay(150);
    //Normal PWM
    } else {
      normal_PWM();
    }  
  }
PORTB |= (1 << PORTB2); //Put pin 10 to high
PORTB &=~ (1 << PORTB3); //Put pin 11 to low


}else{
PORTB &=~ (1 << PORTB2); //Put pin 10 to low
PORTB &=~ (1 << PORTB3); //Put pin 11 to low
delay(3000);  

//Moving the form backwards until button is pressed  
while (route_done == 0){
    //High PWM when the motor has changed direction
    if ((distance*1.4) > distance_count){
    kick_start_PWM(); 
     
  } else {
    //Check if the form is moving to determine PWM signal
    if (millis()-time > 500){
      //High PWM signal
      kick_start_PWM(); 
      delay(150);
    //Normal PWM
    } else {
      normal_PWM();
    }   

  }
  PORTB |= (1 << PORTB3); //Put pin 11 to high
  PORTB &=~ (1 << PORTB2); //Put pin 10 to low
  waste_management_done = 1;  
  
}

}   
}

//Pausing the motor
void pause_motor(){
PORTB &=~ (1 << PORTB2); //Put pin 10 to low
PORTB &=~ (1 << PORTB3); //Put pin 11 to low 
}

//Stop motor and reset when route is done
void stop_motor(){
PORTB &=~ (1 << PORTB2); //Put pin 10 to low
PORTB &=~ (1 << PORTB3); //Put pin 11 to low

//Resetting variables
home_found = 0;
positioning_count = 0;
distance_count = 0;
route_done = 0;
positioning_done = 0;
form_ready_for_sample = 0;
 
}

//Read message
void read_message(){
  message = Wire.read();
}

//Communicate response messages 
void response_message(){

//position message
  if (message == 1) {
   
  //Form is positioned
    if (form_ready_for_sample == 1){
    Wire.write(3);

  } else {
    //Form is not positioned and not moving
    if (millis()-time > 1500){
      Wire.write(4);
    
    //Form is not positioned and moving
    } else {
      Wire.write(5);
    } 

  }
    //Waste management message
  } else if (message == 2){
      
      //Waste management done
      if (home_found == 0 && waste_management_done == 1){
      Wire.write(6); 
       waste_management_done = 0;
    } else {
      //Waste management is not done and form is not moving
    if (millis()-time > 1500){
      Wire.write(7);
    
    // Waste management is not done but form is moving
    } else {
      Wire.write(5);
  
    } 

      

     }

  //pausing the motor when the master arduino has confirmed that it has received info that the request is accomplished
  } else {
    PORTB &=~ (1 << PORTB2); //Put pin 10 to low
    PORTB &=~ (1 << PORTB3); //Put pin 11 to low

  }

  }


int main(void){

init(); 
//Putting pin 2, 8 and 9 to input
DDRD &=~ (DDD2 << 1);
DDRB &=~ (DDB0 << 1);
DDRB &=~ (DDB1 << 1);

//Putting pin 6, 10 and 11 to output
DDRD |= (1 << DDD6);
DDRB |= (DDB2 << 1); 
DDRB |= (DDB3 << 1);


//Activate pin change interrupt
PCICR |= (1 << PCIE0);
PCMSK0 |= (1 << PCINT0) | (1 << PCINT1);

//Activate external interrupt
EICRA |= (1 << ISC00) | (1 << ISC01); 
EIMSK |= (1 << INT0);
PORTD |= (1 << PORTD2); //Pullup resistor


sei();
Serial.begin(9600);
Wire.begin(0x11); 
Wire.onReceive(read_message);
Wire.onRequest(response_message);


normal_PWM();
home_found = 0;




while (1) {


  if (home_found == 0 && form_ready_for_sample == 0){
   position_form(); 
  
 
  }

   else if (route_done == 1 && form_ready_for_sample == 0){
    pause_motor();
    waste_management_done = 0;
    route_done = 0;
    form_ready_for_sample = 1;
    distance_count = 0;
    positioning_count = 0;

  
    } else if (home_found == 1 && form_ready_for_sample == 0){
    if (positioning_count-positioning > positioning*1.5){
    waste_management();

    
  } else {
    form_ready_for_sample = 1;
  }
    
    
    
    
   } else if (form_ready_for_sample == 1 && message == 0){
    pause_motor();

  } else if (route_done == 1 && form_ready_for_sample == 1){     
        stop_motor();

    }else if (form_ready_for_sample == 1 && message == 2) {
    waste_management(); 
  }

  }



}