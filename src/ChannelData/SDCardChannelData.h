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
  // Hold a shuffled list of channel indices and the current index in that list.
  std::vector<int> mShuffledChannels;
  uint32_t mShuffledChannelIndex = 0;

  AVIParser *mCurrentChannelAudioParser = NULL;
  AVIParser *mCurrentChannelVideoParser = NULL;

  SDCard *mSDCard;
  const char *mAviPath;

  // initialize the shuffled channel list to an ordered list of channel indices
  void _initShuffledChannels();

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

  // Reshuffle the channel list.
  void reshuffleChannels();
  // Get the next channel index from the shuffle.
  int getNextChannel();

  AVIParser *getAudioParser() {
    return mCurrentChannelAudioParser;
  };
  AVIParser *getVideoParser() {
    return mCurrentChannelVideoParser;
  };
  void setChannel(int channel);
  int getChannelNumber() { return mChannelNumber; }
};