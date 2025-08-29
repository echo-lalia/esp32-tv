#include <Arduino.h>
#include "AVIParser/AVIParser.h"
#include "VideoPlayer.h"
#include "AudioOutput/AudioOutput.h"
#include "ChannelData/SDCardChannelData.h"
// #include "VideoSource/VideoSource.h"
// #include "AudioSource/AudioSource.h"
#include "Displays/Display.h"
#include <list>


#ifndef AUDIO_BUFFER_SAMPLES
#define AUDIO_BUFFER_SAMPLES 1000
#endif
#define BYTES_PER_SAMPLE 8


void VideoPlayer::_framePlayerTask(void *param)
{
  VideoPlayer *player = (VideoPlayer *)param;
  player->framePlayerTask();
}

void VideoPlayer::_audioPlayerTask(void *param)
{
  VideoPlayer *player = (VideoPlayer *)param;
  player->audioPlayerTask();
}

VideoPlayer::VideoPlayer(ChannelData *channelData, Display &display, AudioOutput *audioOutput)
: mChannelData(channelData), mDisplay(display), mState(VideoPlayerState::STOPPED), mAudioOutput(audioOutput)
{
}

void VideoPlayer::start()
{
  // allocate some small initial buffers for jpeg data
  jpegDecodeBuffer = (uint8_t *) malloc(1024);
  jpegDecodeBufferLength = 1024;
  jpegReadBuffer = (uint8_t *) malloc(1024);
  jpegReadBufferLength = 1024;

  // launch the frame player task
  xTaskCreatePinnedToCore(
      _framePlayerTask,
      "Frame Player",
      10000,
      this,
      1,
      NULL,
      0);
  xTaskCreatePinnedToCore(_audioPlayerTask, "audio_loop", 10000, this, 1, NULL, 1);
}

void VideoPlayer::setChannel(int channel)
{
  mChannelData->setChannel(channel);
  // set the audio sample to 0 - TODO - move this somewhere else?
  mCurrentAudioSample = 0;
  mChannelVisible = millis();
  // update the video source
  // mVideoSource->setChannel(channel);
}

void VideoPlayer::play()
{
  if (mState == VideoPlayerState::PLAYING)
  {
    return;
  }
  mState = VideoPlayerState::PLAYING;
  // mVideoSource->setState(VideoPlayerState::PLAYING);
  mCurrentAudioSample = 0;
}

void VideoPlayer::stop()
{
  if (mState == VideoPlayerState::STOPPED)
  {
    return;
  }
  mState = VideoPlayerState::STOPPED;
  // mVideoSource->setState(VideoPlayerState::STOPPED);
  mCurrentAudioSample = 0;
  mDisplay.fillScreen(DisplayColors::BLACK);
}

void VideoPlayer::pause()
{
  if (mState == VideoPlayerState::PAUSED)
  {
    return;
  }
  mState = VideoPlayerState::PAUSED;
  // mVideoSource->setState(VideoPlayerState::PAUSED);
}

void VideoPlayer::playStatic()
{
  if (mState == VideoPlayerState::STATIC)
  {
    return;
  }
  mState = VideoPlayerState::STATIC;
  // mVideoSource->setState(VideoPlayerState::STATIC);
}


// double buffer the dma drawing otherwise we get corruption
uint16_t *dmaBuffer[2] = {NULL, NULL};
int dmaBufferIndex = 0;
int _doDraw(JPEGDRAW *pDraw)
{
  VideoPlayer *player = (VideoPlayer *)pDraw->pUser;
  player->mDisplay.drawPixels(pDraw->x, pDraw->y, pDraw->iWidth, pDraw->iHeight, pDraw->pPixels);
  return 1;
}

static unsigned short x = 12345, y = 6789, z = 42, w = 1729;

unsigned short xorshift16()
{
  unsigned short t = x ^ (x << 5);
  x = y;
  y = z;
  z = w;
  w = w ^ (w >> 1) ^ t ^ (t >> 3);
  return w & 0xFFFF;
}

void VideoPlayer::framePlayerTask()
{
  // uint16_t *staticBuffer = NULL;
  // uint8_t *jpegBuffer = NULL;
  // size_t jpegBufferLength = 0;
  // size_t jpegLength = 0;
  // used for calculating frame rate
  std::list<int> frameTimes;
  while (true)
  {
    if (mState == VideoPlayerState::STOPPED || mState == VideoPlayerState::PAUSED)
    {
      // nothing to do - just wait
      vTaskDelay(100 / portTICK_PERIOD_MS);
      continue;
    }
    // get the next frame
    // if (!mVideoSource->getVideoFrame(&jpegBuffer, jpegBufferLength, jpegLength))
    // {
    //   // no frame ready yet
    //   vTaskDelay(10 / portTICK_PERIOD_MS);
    //   continue;
    // }

    bool frameDrawn = false;
    // Take the mutex lock and draw a frame if one is ready. Otherwise just delay.
    if (xSemaphoreTake(jpegBufferMutex, portMAX_DELAY)){
      if (frameReady){
        // Draw the frame!
        // Serial.println("Frame is ready!");
        mDisplay.startWrite();
        if (mJpeg.openRAM(jpegDecodeBuffer, jpegDecodeLength, _doDraw))
        {
          mJpeg.setUserPointer(this);
          #ifdef LED_MATRIX
          mJpeg.setPixelType(RGB565_LITTLE_ENDIAN);
          #else
          mJpeg.setPixelType(RGB565_BIG_ENDIAN);
          #endif
          mJpeg.decode(0, 0, 0);
          mJpeg.close();
          // Serial.println("Frame drawn.");
        }
        frameReady = false;
        frameDrawn = true;
      }
      xSemaphoreGive(jpegBufferMutex);

    }

    // If we drew a new frame above, finish any final tasks that dont require the mutex.
    if (frameDrawn){
      frameTimes.push_back(millis());
      // keep the frame rate elapsed time to 5 seconds
      while(frameTimes.size() > 0 && frameTimes.back() - frameTimes.front() > 2000) {
        frameTimes.pop_front();
      }
      
      // show channel indicator 
      if (millis() - mChannelVisible < 2000) {
        mDisplay.drawChannel(mChannelData->getChannelNumber());
      }
      #if CORE_DEBUG_LEVEL > 0
      mDisplay.drawFPS(frameTimes.size() / 2);
      #endif
      mDisplay.endWrite();
    }
  }
}


void VideoPlayer::audioPlayerTask()
{
  size_t bufferLength = AUDIO_BUFFER_SAMPLES * BYTES_PER_SAMPLE;
  uint8_t *audioData = (uint8_t *)malloc(bufferLength);
  while (true)
  {
    if (mState != VideoPlayerState::PLAYING)
    {
      // nothing to do - just wait
      vTaskDelay(100 / portTICK_PERIOD_MS);
      continue;
    }
    // get audio data to play
    int audioLength = _getAudioSamples(&audioData, bufferLength, mCurrentAudioSample);
    // have we reached the end of the channel?
    if (audioLength == 0) {
      // we want to loop the video so reset the channel data and start again
      stop();
      setChannel(mChannelData->getChannelNumber());
      play();
      continue;
    }
    if (audioLength > 0) {
      // play the audio
      for(int i=0; i<audioLength; i+=AUDIO_BUFFER_SAMPLES) {
        mAudioOutput->write(audioData + i, min(AUDIO_BUFFER_SAMPLES, audioLength - i));
        mCurrentAudioSample += min(AUDIO_BUFFER_SAMPLES, audioLength - i);
        if (mState != VideoPlayerState::PLAYING)
        {
          mCurrentAudioSample = 0;
          // mVideoSource->updateAudioTime(0);
          break;
        }
        // mVideoSource->updateAudioTime(1000 * mCurrentAudioSample / AUDIO_RATE);
      }
    }
    else
    {
      vTaskDelay(10 / portTICK_PERIOD_MS);
    }
  }
}


int VideoPlayer::_getAudioSamples(uint8_t **buffer, size_t &bufferSize, int currentAudioSample)
{
  // read the audio data into the buffer
  AVIParser *parser = mChannelData->getAudioParser();
  if (parser) {
    ChunkHeader header;
    
    while (header.chunkType != EMPTY_CHUNK)
    {
      header = parser->getNextHeader();

      if (header.chunkType == AUDIO_CHUNK){
        // read audio data
        int audioLength = parser->getNextChunk(header, (uint8_t **) buffer, bufferSize);
        // Serial.println("Got audio chunk");
        return audioLength;
      }

      else if (header.chunkType == VIDEO_CHUNK){

        // TODO: instead of immediately swapping the buffers, just read, and set a flag to swap the buffers later (to prevent waiting too long for the lock)
        // read video data
        jpegReadLength = parser->getNextChunk(header, (uint8_t **) &jpegReadBuffer, jpegReadBufferLength);
        // Serial.println("Got video chunk");

        // Take the mutex lock and swap the read/decode buffers
        if (xSemaphoreTake(jpegBufferMutex, portMAX_DELAY)){
          if (frameReady) {Serial.println("Overwriting video chunk!");}

          uint8_t *tempBuffer = jpegDecodeBuffer;
          size_t tempBufferLength = jpegDecodeBufferLength;
          size_t tempLength = jpegReadLength;

          jpegDecodeBuffer = jpegReadBuffer;
          jpegDecodeBufferLength = jpegReadBufferLength;
          jpegDecodeLength = jpegReadLength;

          jpegReadBuffer = tempBuffer;
          jpegReadBufferLength = tempBufferLength;
          jpegReadLength = tempLength;
          frameReady = true;
          xSemaphoreGive(jpegBufferMutex);
        }
        else{
          parser->getNextChunk(header, (uint8_t **) jpegReadBuffer, jpegReadBufferLength, true);
          Serial.println("Failed to get semaphore and skipped video chunk.");
        }
      }

      else {
        // this chunk is of no use to us. Skip it!
        parser->getNextChunk(header, (uint8_t **) buffer, bufferSize, true);
      }

    }
  }
  Serial.println("No audio or video chunks found!");
  return 0;
}
