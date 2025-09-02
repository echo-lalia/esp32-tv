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
#include "AVIParser/AVIParser.h"
#include "SDCard.h"
#include "Button.h"
#include <Wire.h>


#ifndef USE_DMA
#warning "No DMA - Drawing may be slower"
#endif

// VideoSource *videoSource = NULL;
// AudioSource *audioSource = NULL;
VideoPlayer *videoPlayer = NULL;
AudioOutput *audioOutput = NULL;
ChannelData *channelData = NULL;
// #ifdef LED_MATRIX
// Matrix display;
// #else
TFT display;
// #endif

// TwoWire wire2(0);

void randomChannel();
int prevChannel = 99999;
int channel = 99999;


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
  #ifndef AUDIO_ENABLE_VAL
  #define AUDIO_ENABLE_VAL LOW
  #endif
  pinMode(AUDIO_ENABLE_PIN, OUTPUT);
  Serial.printf("Enabling audio by setting Pin %d to %d\n", AUDIO_ENABLE_PIN, AUDIO_ENABLE_VAL);
  digitalWrite(AUDIO_ENABLE_PIN, AUDIO_ENABLE_VAL);
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
  channelData = new ChannelData(card, "/");
  // audioSource = new SDCardAudioSource((ChannelData *) channelData);
  // videoSource = new SDCardVideoSource((ChannelData *) channelData);


#ifdef USE_DAC_AUDIO
  audioOutput = new DACOutput(I2S_NUM_0);
  audioOutput->start(AUDIO_RATE);
#endif
#ifdef PDM_GPIO_NUM
  i2s speaker pins
  i2s_pin_config_t i2s_speaker_pins = {
      .bck_io_num = I2S_PIN_NO_CHANGE,
      .ws_io_num = GPIO_NUM_0,
      .data_out_num = PDM_GPIO_NUM,
      .data_in_num = I2S_PIN_NO_CHANGE};
  audioOutput = new PDMOutput(I2S_NUM_0, i2s_speaker_pins);
  audioOutput->start(AUDIO_RATE);
#endif
#ifdef PWM_GPIO_NUM
  audioOutput = new PWMTimerOutput(PWM_GPIO_NUM);
  audioOutput->start(AUDIO_RATE);
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
  audioOutput->start(AUDIO_RATE);
#endif
  videoPlayer = new VideoPlayer(
    channelData,
    // videoSource,
    // audioSource,
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

  videoPlayer->playStatic();
  delay(1000);

  randomChannel();

  // // default to first channel
  // videoPlayer->setChannel(0);
  // delay(500);
  // videoPlayer->play();


  audioOutput->setVolume(4);
}



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



// get a random int between 0, and the given limit, excluding 2 numbers.
uint_fast32_t randomExceptTwo(uint_fast32_t limit, uint_fast32_t exclude1, uint_fast32_t exclude2){
  // This math requires that the two excludes are different.
  if (exclude1 == exclude2){
      exclude2 = limit + 1;
    }
  uint_fast32_t excludeLower = min(exclude1, exclude2);
  uint_fast32_t excludeUpper = max(exclude1, exclude2);

  // If the bigger exclude can be reached, our range is smaller by one.
  if (excludeUpper >= 0 and excludeUpper < limit) {limit--;}
  // If the smaller exclude can be reached, our range shrinks by one.
  if (excludeLower >= 0 and excludeLower < limit) {limit--;}

  uint_fast32_t rand = random(limit);

  // re-add to the random value if it is equal to or above each limit
  if (rand >= excludeLower) {rand++;}
  if (rand >= excludeUpper) {rand++;}

  return rand;
}


// Get a random channel, attempting to avoid repeats.
int getRandomChannel(){
  int channelCount = channelData->getChannelCount();
  // If there's only one option; return it.
  if (channelCount == 1) {return 0;}
  // Otherwise, if there's only two options, return the one that ISNT the current channel.
  if (channelCount == 2) {
    return (channel == 0) ? 1 : 0;
  }
  // If there's 3 or more channels, randomly pick a channel, but DONT pick the current or previous channel.
  Serial.printf("randomExceptTwo(%d, %d, %d\n)", channelCount, channel, prevChannel);
  return randomExceptTwo(channelCount, channel, prevChannel);
}


void randomChannel() {
  videoPlayer->playStatic();
  delay(500);
  int newChannel = getRandomChannel();
  prevChannel = channel;
  channel = newChannel;

  videoPlayer->setChannel(channel);
  videoPlayer->play();
  Serial.printf("randomChannel: %d\n", channel);
}


void loop()
{
  if (change_channel_pressed || videoPlayer->isFinished()){
    Serial.println("Setting random channel.");
    videoPlayer->stop();
    delay(100);
    randomChannel();
    videoPlayer->play();
    
  }

  buttonLoop();

  delay(100);

}
