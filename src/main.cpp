#include <Arduino.h>
#include "Displays/TFT.h"
#include "Displays/Matrix.h"
#include "VideoPlayer.h"
#include "AudioOutput/I2SOutput.h"
#include "AudioOutput/DACOutput.h"
#include "AudioOutput/PDMTimerOutput.h"
#include "AudioOutput/PWMTimerOutput.h"
#include "AudioOutput/PDMOutput.h"
#include "ChannelData/SDCardChannelData.h"
#include "AudioSource/SDCardAudioSource.h"
#include "VideoSource/SDCardVideoSource.h"
#include "AVIParser/AVIParser.h"
#include "SDCard.h"
#include "Button.h"
#include <Wire.h>


#ifndef HAS_BUTTONS
#warning "No Input - Will default to playing channel 0"
#endif

#ifndef USE_DMA
#warning "No DMA - Drawing may be slower"
#endif

VideoSource *videoSource = NULL;
AudioSource *audioSource = NULL;
VideoPlayer *videoPlayer = NULL;
AudioOutput *audioOutput = NULL;
ChannelData *channelData = NULL;
#ifdef LED_MATRIX
Matrix display;
#else
TFT display;
#endif

TwoWire wire2(0);

void setup()
{
  Serial.begin(115200);
  Serial.printf("CPU freq: %dmhz\n", ESP.getCpuFreqMHz());
  Serial.printf("Total heap: %d\n", ESP.getHeapSize());
  Serial.printf("Free heap: %d\n", ESP.getFreeHeap());
  Serial.printf("Total PSRAM: %d\n", ESP.getPsramSize());
  Serial.printf("Free PSRAM: %d\n", ESP.getFreePsram());
  buttonInit();


  #ifdef AUDIO_ENABLE_PIN
  // Enable audio (if required)
  pinMode(AUDIO_ENABLE_PIN, OUTPUT);
  #ifdef AUDIO_ENABLE_VAL
  Serial.printf("Enabling audio by setting Pin %d to %d\n", AUDIO_ENABLE_PIN, AUDIO_ENABLE_VAL);
  digitalWrite(AUDIO_ENABLE_PIN, AUDIO_ENABLE_VAL);
  #else
  Serial.printf("Enabling audio by setting Pin %d LOW", AUDIO_ENABLE_PIN);
  digitalWrite(AUDIO_ENABLE_PIN, LOW);
  #endif
  #endif


  Serial.println("Using SD Card");
  // power on the SD card
  #ifdef SD_CARD_PWR
  if (SD_CARD_PWR != GPIO_NUM_NC) {
    pinMode(SD_CARD_PWR, OUTPUT);
    digitalWrite(SD_CARD_PWR, SD_CARD_PWR_ON);
  }
  #endif
  #ifdef USE_SDIO
  SDCard *card = new SDCard(SD_CARD_CLK, SD_CARD_CMD, SD_CARD_D0, SD_CARD_D1, SD_CARD_D2, SD_CARD_D3);
  #else
  SDCard *card = new SDCard(SD_CARD_MISO, SD_CARD_MOSI, SD_CARD_CLK, SD_CARD_CS);
  #endif
  // check that the SD Card has mounted properly
  if (!card->isMounted()) {
    Serial.println("Failed to mount SD Card");
    display.drawSDCardFailed();
    while(true) {
      delay(1000);
    }
  }
  channelData = new SDCardChannelData(card, "/");
  audioSource = new SDCardAudioSource((SDCardChannelData *) channelData);
  videoSource = new SDCardVideoSource((SDCardChannelData *) channelData);


#ifdef USE_DAC_AUDIO
  audioOutput = new DACOutput(I2S_NUM_0);
  audioOutput->start(16000);
#endif
#ifdef PDM_GPIO_NUM
  i2s speaker pins
  i2s_pin_config_t i2s_speaker_pins = {
      .bck_io_num = I2S_PIN_NO_CHANGE,
      .ws_io_num = GPIO_NUM_0,
      .data_out_num = PDM_GPIO_NUM,
      .data_in_num = I2S_PIN_NO_CHANGE};
  audioOutput = new PDMOutput(I2S_NUM_0, i2s_speaker_pins);
  audioOutput->start(8000);
#endif
#ifdef PWM_GPIO_NUM
  audioOutput = new PWMTimerOutput(PWM_GPIO_NUM);
  audioOutput->start(8000);
#endif
#ifdef I2S_SPEAKER_SERIAL_CLOCK
#ifdef SPK_MODE
  pinMode(SPK_MODE, OUTPUT);
  digitalWrite(SPK_MODE, HIGH);
#endif
  // i2s speaker pins
  i2s_pin_config_t i2s_speaker_pins = {
      .bck_io_num = I2S_SPEAKER_SERIAL_CLOCK,
      .ws_io_num = I2S_SPEAKER_LEFT_RIGHT_CLOCK,
      .data_out_num = I2S_SPEAKER_SERIAL_DATA,
      .data_in_num = I2S_PIN_NO_CHANGE};

  audioOutput = new I2SOutput(I2S_NUM_1, i2s_speaker_pins);
  audioOutput->start(8000);
#endif
  videoPlayer = new VideoPlayer(
    channelData,
    videoSource,
    audioSource,
    display,
    audioOutput
  );
  videoPlayer->start();

  display.drawTuningText();
  // get the channel info
  while(!channelData->fetchChannelData()) {
    Serial.println("Failed to fetch channel data");
    delay(1000);
  }
  // default to first channel
  videoPlayer->setChannel(0);
  delay(500);
  videoPlayer->play();

}

int channel = 0;

void volumeUp() {
  audioOutput->volumeUp();
  delay(500);
  Serial.println("VOLUME_UP");
}

void volumeDown() {
  audioOutput->volumeDown();
  delay(500);
  Serial.println("VOLUME_DOWN");
}

void channelDown() {
  videoPlayer->playStatic();
  delay(500);
  channel--;
  if (channel < 0) {
    channel = channelData->getChannelCount() - 1;
  }
  videoPlayer->setChannel(channel);
  videoPlayer->play();
  Serial.printf("CHANNEL_DOWN %d\n", channel);
}

void channelUp() {
  videoPlayer->playStatic();
  delay(500);
  channel = (channel + 1) % channelData->getChannelCount();
  videoPlayer->setChannel(channel);
  videoPlayer->play();
  Serial.printf("CHANNEL_UP %d\n", channel);
}

void loop()
{

#ifdef HAS_BUTTONS
  if (buttonLeft()) {
    channelDown();
  }
  if (buttonRight()) {
    channelUp();
  }
  if (buttonUp()) {
    volumeUp();
  }
  if (buttonDown()) {
    volumeDown();
  }
  if (buttonPowerOff()) {
    Serial.println("POWER OFF");
    delay(500);
    powerDeepSeep();
  }
  buttonLoop();
#else
    // important this needs to stay otherwise we are constantly polling the IR Remote
    // and there's no time for anything else to run.
    delay(200);
#endif
}
