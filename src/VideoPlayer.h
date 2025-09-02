#pragma once
#include <Arduino.h>
// #ifdef LED_MATRIX
// struct File; // fixes weird compilation error
// #endif
#include "JPEGDEC.h"
#include "ChannelData/SDCardChannelData.h"
#include "VideoPlayerState.h"

#ifndef AUDIO_RATE
#define AUDIO_RATE 16000
#endif

class Display;
class AudioOutput;

// class VideoSource;
// class AudioSource;

class VideoPlayer {
  private:
    int mChannelVisible = 0;
    VideoPlayerState mState = VideoPlayerState::STOPPED;

    // video playing
    Display &mDisplay;
    JPEGDEC mJpeg;

    // video source
    // VideoSource *mVideoSource = NULL;
    // audio source
    // AudioSource *mAudioSource = NULL;
    // channel information
    ChannelData *mChannelData = NULL;

    // audio playing
    int mCurrentAudioSample = 0;
    AudioOutput *mAudioOutput = NULL;


    // The buffer to use for jpeg frame decoding.
    uint8_t *jpegDecodeBuffer = NULL;
    // The total size of the jpeg decode buffer
    size_t jpegDecodeBufferLength = 0;
    // The real length of jpeg data stored in the buffer (might be less than buffer length)
    size_t jpegDecodeLength = 0;
    // The buffer to read jpeg data into
    uint8_t *jpegReadBuffer = NULL;
    // The total size of the jpeg decode buffer
    size_t jpegReadBufferLength = 0;
    // The real length of jpeg data stored in the buffer (might be less than buffer length)
    size_t jpegReadLength = 0;
    bool frameReady = false;
    // Mutex used to lock jpeg decoding while the audio task is swapping the buffers (and setting frameReady).
    // Otherwise the audio task only writes to the "read" buffer, and the frame task only reads from the "decode" buffer.
    SemaphoreHandle_t jpegBufferMutex = xSemaphoreCreateMutex();

    static void _framePlayerTask(void *param);
    static void _audioPlayerTask(void *param);

    void framePlayerTask();
    void audioPlayerTask();
    int _getAudioSamples(uint8_t **buffer, size_t &bufferSize, int currentAudioSample);

    friend int _doDraw(JPEGDRAW *pDraw);

  public:
    VideoPlayer(ChannelData *channelData, Display &display, AudioOutput *audioOutput);
    void setChannel(int channelIndex);
    void start();
    void play();
    void _setPlayingFinished();
    bool isFinished() {return (mState == VideoPlayerState::PLAYING_FINISHED);}
    void stop();
    void pause();
    void playStatic();
    bool takeMutex() {return xSemaphoreTake(jpegBufferMutex, portMAX_DELAY);}
    void giveMutex() {xSemaphoreGive(jpegBufferMutex);}
};