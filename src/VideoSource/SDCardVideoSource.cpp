
#include <Arduino.h>
#include "SDCardVideoSource.h"
#include "../AVIParser/AVIParser.h"
#include "../ChannelData/SDCardChannelData.h"

#ifndef DEFAULT_FPS
#define DEFAULT_FPS 15
#endif


SDCardVideoSource::SDCardVideoSource(SDCardChannelData *mChannelData) : mChannelData(mChannelData)
{
}

void SDCardVideoSource::start()
{
  // nothing to do!
}

bool SDCardVideoSource::getVideoFrame(uint8_t **buffer, size_t &bufferLength, size_t &frameLength)
{
  AVIParser *parser = mChannelData->getVideoParser();
  if (!parser) {
    return false;
  }
  if (mState == VideoPlayerState::STOPPED || mState == VideoPlayerState::STATIC)
  {
    vTaskDelay(100 / portTICK_PERIOD_MS);
    Serial.println("SDCardVideoSource::getVideoFrame: video is stopped or static");
    return false;
  }
  if (mState == VideoPlayerState::PAUSED)
  {
    // video time is not passing, so keep moving the start time forward so it is now
    mLastAudioTimeUpdateMs = millis();
    vTaskDelay(100 / portTICK_PERIOD_MS);
    Serial.println("SDCardVideoSource::getVideoFrame: video is paused");
    return false;
  }
  // work out the video time from a combination of the currentAudioSample and the elapsed time
  int elapsedTime = millis() - mLastAudioTimeUpdateMs;
  int videoTime = mAudioTimeMs + elapsedTime;
  int targetFrame = videoTime * DEFAULT_FPS / 1000;
  if (mFrameCount >= targetFrame){
    return false;
  }

  // Skip some number of frames if we have fallen behind
  while (targetFrame - mFrameCount > 1){
    mFrameCount++;
    // Serial.printf("Skipping frame: %d\n", mFrameCount);
    frameLength = parser->skipNextChunk();
  }

  // We are caught up to targetFrame-1, so load the next frame to show.
  mFrameCount++;
  #if CORE_DEBUG_LEVEL > 0
  Serial.printf("Parsing frame %d\n", mFrameCount);
  #endif
  // Serial.printf("Getting Frame: %d\n", mFrameCount);
  frameLength = parser->getNextChunk((uint8_t **)buffer, bufferLength);

  return true;
}
