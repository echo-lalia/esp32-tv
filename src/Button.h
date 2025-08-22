#include <Arduino.h>

int _btn_left=-1;
int _btn_right=-1;

bool buttonRight(){
#ifdef BUTTON_R
  return (_btn_right == 0);
#endif
  return false;
}

bool buttonLeft(){
#ifdef BUTTON_L
  return (_btn_left == 0);
#endif
  return false;
}

bool buttonUp(){
  return false;
}

bool buttonDown(){
  return false;
}

bool buttonPowerOff() {
#ifdef BUTTON_L
  #ifdef BUTTON_R
    return (_btn_left == 0 && _btn_right == 0);
  #endif
#endif
  return false;
}

void buttonInit(){
#ifdef BUTTON_L
  #ifdef BUTTON_R
  pinMode(BUTTON_L, INPUT_PULLUP);
  pinMode(BUTTON_R, INPUT);
  #endif
#endif
}

void buttonLoop(){
  static uint_fast64_t buttonTimeStamp = 0;
  if (millis() - buttonTimeStamp > 20) {
    buttonTimeStamp = millis();
    #ifdef BUTTON_L
      #ifdef BUTTON_R
    _btn_right = digitalRead(BUTTON_R);
    _btn_left = digitalRead(BUTTON_L);
      #endif
    #endif
  }
}


