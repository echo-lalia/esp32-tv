#pragma once

#include <vector>
#include <string>

class SDCard;
class AVIParser;

class ChannelData
{
protected:
  int mChannelNumber = 0;
private:
  const char *mChannelInfoURL = NULL;
  std::vector<std::string> mAviFiles;
  AVIParser *mCurrentChannelAudioParser = NULL;
  AVIParser *mCurrentChannelVideoParser = NULL;

  // Mutex lock to protect control of current channel and parser.
  // SemaphoreHandle_t controlMutex = xSemaphoreCreateMutex();

  SDCard *mSDCard;
  const char *mAviPath;
public:
  ChannelData(SDCard *sdCard, const char *aviPath);
  bool fetchChannelData();
  int getChannelCount() {
    return mAviFiles.size();
  };
  int getChannelLength(int channelIndex) {
    // we don't know the length of the AVI file
    return -1;
  };
  // bool takeControl() {
  //   Serial.println("Someone took control of ChannelData.");
  //   return xSemaphoreTake(controlMutex, portMAX_DELAY);
  // }
  // bool giveControl() {
  //   Serial.println("Released control of ChannelData.");
  //   return xSemaphoreGive(controlMutex);
  // }
  AVIParser *getAudioParser() {
    return mCurrentChannelAudioParser;
  };
  AVIParser *getVideoParser() {
    return mCurrentChannelVideoParser;
  };
  void setChannel(int channel);
  int getChannelNumber() { return mChannelNumber; }
};