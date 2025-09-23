#include <Arduino.h>
#include "../SDCard.h"
#include "SDCardChannelData.h"
#include "../AVIParser/AVIParser.h"

ChannelData::ChannelData(SDCard *sdCard, const char *aviPath): mSDCard(sdCard), mAviPath(aviPath) {

}

bool ChannelData::fetchChannelData() {
  // check the the sd card is mounted
  if (!mSDCard->isMounted()) {
    Serial.println("SD card is not mounted");
    return false;
  }

  // get the list of AVI files
  mAviFiles = mSDCard->listFiles(mAviPath, ".avi");
  reshuffleChannels();
  
  if (mAviFiles.size() == 0) {
    Serial.println("No AVI files found");
    return false;
  }
  return true;
}


void ChannelData::setChannel(int channel) {
  // if (!takeControl()) {
  //   Serial.println("Failed to take control of channel data.");
  //   return;
  // }
  if (!mSDCard->isMounted()) {
    Serial.println("SD card is not mounted");
    return;
  }
  // check that the channel is valid
  if (channel < 0 || channel >= mAviFiles.size()) {
    Serial.printf("Invalid channel %d\n", channel);
    return;
  }
  // close any open AVI files
  if (mCurrentChannelAudioParser) {
    delete mCurrentChannelAudioParser;
    mCurrentChannelAudioParser = NULL;
  }
  if (mCurrentChannelVideoParser) {
    delete mCurrentChannelVideoParser;
    mCurrentChannelVideoParser = NULL;
  }
  // open the AVI file
  std::string aviFilename = mAviFiles[channel];
  Serial.printf("Opening AVI file %s\n", aviFilename.c_str());
  mCurrentChannelAudioParser = new AVIParser(aviFilename, AVIChunkType::AUDIO);
  if (!mCurrentChannelAudioParser->open()) {
    Serial.printf("Failed to open AVI file %s\n", aviFilename.c_str());
    delete mCurrentChannelAudioParser;
    mCurrentChannelAudioParser = NULL;
  }
  mCurrentChannelVideoParser = new AVIParser(aviFilename, AVIChunkType::VIDEO);
  if (!mCurrentChannelVideoParser->open()) {
    Serial.printf("Failed to open AVI file %s\n", aviFilename.c_str());
    delete mCurrentChannelVideoParser;
    mCurrentChannelVideoParser = NULL;
    delete mCurrentChannelAudioParser;
    mCurrentChannelAudioParser = NULL;
  }
  mChannelNumber = channel;
}


void ChannelData::_initShuffledChannels(){
  if (mShuffledChannels.size() != mAviFiles.size()){
    mShuffledChannels.resize(mAviFiles.size());
  }
  for (int i = 0; i < mAviFiles.size(); i++){
    mShuffledChannels[i] = i;
  }
}


void ChannelData::reshuffleChannels(){
  Serial.println("Reshuffling channels...");
  _initShuffledChannels();

  for (int idx = 0; idx < mShuffledChannels.size() - 2; idx++){
    int idx2 = random(idx, mShuffledChannels.size());
    int tmp = mShuffledChannels[idx];
    mShuffledChannels[idx] = mShuffledChannels[idx2];
    mShuffledChannels[idx2] = tmp;
  }
  mShuffledChannelIndex = 0;

  #if CORE_DEBUG_LEVEL > 2
  Serial.println("Shuffled order:");
  for (int i = 0; i < mShuffledChannels.size(); i++){
    Serial.printf("%d ", mShuffledChannels[i]);
  }
  Serial.print("\n");
  #endif
}


int ChannelData::getNextChannel(){
  mShuffledChannelIndex++;
  if (mShuffledChannelIndex >= mShuffledChannels.size()){
    mShuffledChannelIndex = 0;
    reshuffleChannels();
  }
  return mShuffledChannels[mShuffledChannelIndex];
}



