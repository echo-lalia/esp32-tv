#include <Arduino.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "AVIParser.h"


// #define PROFILE_START int start_time = millis(); int new_time = start_time;
// #define PROFILE_CHECKPOINT(text) new_time = millis(); Serial.printf(text ": %dms\n", new_time - start_time); start_time = new_time;


// enum chunk_type {AUDIO_CHUNK, VIDEO_CHUNK, RIFF_CHUNK, LIST_CHUNK, OTHER_CHUNK};




void readChunk(FILE *file, ChunkHeader *header)
{
  char chunkId[4];
  fread(chunkId, 4, 1, file);
  fread(&header->chunkSize, 4, 1, file);

  if (strncmp(chunkId, "00dc", 4) == 0){
    header->chunkType = VIDEO_CHUNK;
  } 
  else if (strncmp(chunkId, "01wb", 4) == 0){
    // Serial.println("Reading AudioChunkHeader.");
    header->chunkType = AUDIO_CHUNK;
  }
  else if (strncmp(chunkId, "RIFF", 4) == 0){
    header->chunkType = RIFF_CHUNK;
  }
  else if (strncmp(chunkId, "LIST", 4) == 0){
    header->chunkType = LIST_CHUNK;
  }
  else {
    header->chunkType = OTHER_CHUNK;
  }
  
  // Serial.printf("ChunkId %c%c%c%c, size %u\n",
  //        header->chunkId[0], header->chunkId[1],
  //        header->chunkId[2], header->chunkId[3],
  //        header->chunkSize);
}

AVIParser::AVIParser(std::string fname, AVIChunkType requiredChunkType): mFileName(fname), mRequiredChunkType(requiredChunkType)
{
}

AVIParser::~AVIParser()
{
  if (mFile)
  {
    fclose(mFile);
  }
}

bool AVIParser::isMoviListChunk(unsigned int chunkSize)
{
  char listType[4];
  fread(&listType, 4, 1, mFile);
  chunkSize -= 4;
  Serial.printf("LIST type %c%c%c%c\n",
                listType[0], listType[1],
                listType[2], listType[3]);
  // check for the movi list - contains the video frames and audio data
  if (strncmp(listType, "movi", 4) == 0)
  {
    Serial.printf("Found movi list.\n");
    Serial.printf("List Chunk Length: %d\n", chunkSize);
    mMoviListPosition = ftell(mFile);
    mMoviListLength = chunkSize;
    return true;
  }
  else
  {
    // skip the rest of the bytes
    fseek(mFile, chunkSize, SEEK_CUR);
  }
  return false;
}

bool AVIParser::open()
{
  mFile = fopen(mFileName.c_str(), "rb");
  if (!mFile)
  {
    Serial.printf("Failed to open file.\n");
    return false;
  }

  #ifdef FILE_BUFFER_SIZE
  // Increase size of file buffer if needed.
  Serial.printf("Setting file buffer size to %d bytes.\n", FILE_BUFFER_SIZE);
  setvbuf(mFile, NULL, _IOFBF, FILE_BUFFER_SIZE);
  #endif

  // check the file is valid
  ChunkHeader header;
  // Read RIFF header
  readChunk(mFile, &header);
  if (header.chunkType != RIFF_CHUNK)
  {
    Serial.println("Not a valid AVI file.");
    fclose(mFile);
    mFile = NULL;
    return false;
  }
  else
  {
    Serial.printf("RIFF header found.\n");
  }
  // next four bytes are the RIFF type which should be 'AVI '
  char riffType[4];
  fread(&riffType, 4, 1, mFile);
  if (strncmp(riffType, "AVI ", 4) != 0)
  {
    Serial.println("Not a valid AVI file.");
    fclose(mFile);
    mFile = NULL;
    return false;
  }
  else
  {
    Serial.println("RIFF Type is AVI.");
  }

  // now read each chunk and find the movi list
  while (!feof(mFile) && !ferror(mFile))
  {
    readChunk(mFile, &header);
    if (feof(mFile) || ferror(mFile))
    {
      break;
    }
    // is it a LIST chunk?
    if (header.chunkType == LIST_CHUNK)
    {
      if (isMoviListChunk(header.chunkSize))
      {
        break;
      }
    }
    else
    {
      // skip the chunk data bytes
      fseek(mFile, header.chunkSize, SEEK_CUR);
    }
  }
  // did we find the list?
  if (mMoviListPosition == 0)
  {
    Serial.printf("Failed to find the movi list.\n");
    fclose(mFile);
    mFile = NULL;
    return false;
  }
  // keep the file open for reading the frames
  return true;
}


ChunkHeader AVIParser::getNextHeader(){
  // check if the file is open
  if (!mFile)
  {
    Serial.println("No file open.");
    return EMPTY_HEADER;
  }
  // did we find the movi list?
  if (mMoviListPosition == 0) {
    Serial.println("No movi list found.");
    return EMPTY_HEADER;
  }

  if (mMoviListLength > 0){
    // get the next chunk of data from the list
    ChunkHeader header;
    readChunk(mFile, &header);
    mMoviListLength -= 8;
    return header;
  }
  else {
    // no more chunks
    Serial.println("No more data");
    return EMPTY_HEADER;
  }

}


size_t AVIParser::getNextChunk(ChunkHeader header, uint8_t **buffer, size_t &bufferLength, bool skipChunk)
{
  if (skipChunk)
  {
    // the data is not what was required - skip over the chunk
    fseek(mFile, header.chunkSize, SEEK_CUR);
    mMoviListLength -= header.chunkSize;
    // handle any padding bytes
    if (header.chunkSize % 2 != 0){
      fseek(mFile, 1, SEEK_CUR);
      mMoviListLength--;
    }
  }
  else
  {
    // we've got the required chunk - copy it into the provided buffer
    if (header.chunkSize > bufferLength)
    {
      Serial.printf("Buffer size %d is too small to read next chunk. Reallocating %d bytes.\n", bufferLength, header.chunkSize);
      *buffer = (uint8_t *)realloc(*buffer, header.chunkSize);
      bufferLength = header.chunkSize;
      Serial.println("Reallocated!");
    }
    // copy the chunk data
    fread(*buffer, header.chunkSize, 1, mFile);
    
    mMoviListLength -= header.chunkSize;
    // handle any padding bytes
    if (header.chunkSize % 2 != 0)
    {
      fseek(mFile, 1, SEEK_CUR);
      mMoviListLength--;
    }
    return header.chunkSize;
  }
}