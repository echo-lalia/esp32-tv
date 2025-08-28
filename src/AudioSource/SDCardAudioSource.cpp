// #include <Arduino.h>
// // #include "SDCardAudioSource.h"
// #include "../AVIParser/AVIParser.h"
// #include "../ChannelData/SDCardChannelData.h"

// SDCardAudioSource::SDCardAudioSource(ChannelData *channelData): mChannelData(channelData)
// {
// }

// int SDCardAudioSource::getAudioSamples(uint8_t **buffer, size_t &bufferSize, int currentAudioSample)
// {
//   // read the audio data into the buffer
//   AVIParser *parser = mChannelData->getAudioParser();
//   if (parser) {
//     ChunkHeader header;
    
//     while (header.chunkType != EMPTY_CHUNK)
//     {
//       header = parser->getNextHeader();
//       if (header.chunkType == AUDIO_CHUNK){
//         // read audio data
//         int audioLength = parser->getNextChunk((uint8_t **) buffer, bufferSize);
//         return audioLength;
//       }
//       if (header.chunkType == VIDEO_CHUNK){
//         // read video data

//         // read video data into the storage buffer for the video playing task.
//         // call the apropriate video handler function, which swaps the draw and store buffers, and queues a draw for the newly filled buffer.

//       }
//     }
//   }
//   return 0;
// }