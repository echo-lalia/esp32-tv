#pragma once
#ifndef LED_MATRIX
#include "Display.h"
#include <TFT_eSPI.h>

class TFT_eSPI;

class TFT: public Display {
private:
  TFT_eSPI *tft;
  uint16_t *dmaBuffer[2] = {NULL, NULL};
  int dmaBufferIndex = 0;
public:
  TFT();
  void init();
  void drawPixels(int x, int y, int width, int height, uint16_t *pixels);
  void drawPixel(int x, int y, uint16_t color);
  void startWrite();
  void endWrite();
  int width();
  int height();
  void fillScreen(uint16_t color = TFT_BLACK);
  void drawChannel(int channelIndex);
  void drawTuningText();
  void drawFPS(int fps);
  void drawSDCardFailed();
};
#endif