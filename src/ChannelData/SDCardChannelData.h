#pragma once

#include <vector>
#include <string>

class SDCard;
class AVIParser;

class ChannelData
{
protected:
  int mChannelNumber = -1;
private:
  const char *mChannelInfoURL = NULL;

  std::vector<std::string> mAviFiles;
  std::vector<std::string> mBumperFiles;
  // Hold a shuffled list of channel indices and the current index in that list.
  std::vector<int> mShuffledChannels;

  AVIParser *mCurrentChannelVideoParser = NULL;

  SDCard *mSDCard;
  const char *mAviPath;
  const char *mBumperPath;

  // initialize the shuffled channel list to an ordered list of channel indices
  void _initShuffledChannels();
  // create and store a new shuffle seed
  void _resetShuffleSeed();
public:
  ChannelData(SDCard *sdCard, const char *aviPath, const char *bumperPath);
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

  AVIParser *getVideoParser() {
    return mCurrentChannelVideoParser;
  };
  void setChannel(int channel);
  int getChannelNumber() { return mChannelNumber; }
};