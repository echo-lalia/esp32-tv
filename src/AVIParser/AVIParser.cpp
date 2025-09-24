#include <Arduino.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "AVIParser.h"


// Store some channel information in RTC ram so it persists through deep sleep.
// Whether or not a file is currently playing
RTC_DATA_ATTR bool isFilePlaying = false;
// The hash of the current file name
RTC_DATA_ATTR uint32_t currentFileNameHash = 0;
// The current file position
RTC_DATA_ATTR long currentFilePosition = 0;
// The current remaining movi list length
RTC_DATA_ATTR long currentMoviListLength = 0;



// 32-bit FNV-1 hash function (http://www.isthe.com/chongo/tech/comp/fnv/index.html#FNV-1)
#define FNV_OFFSET_BASIS 2166136261u
#define FNV_PRIME        16777619u
uint32_t fnvHash(const char *str)
{
    uint32_t hash = FNV_OFFSET_BASIS;
    unsigned char c;

    while ((c = (unsigned char)*str++)) {
        hash *= FNV_PRIME;   // multiply by FNV prime
        hash ^= c;           // XOR with the next byte
    }

    return hash;
}


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

  // attempt to resume playback if we have reopened the previous file
  if (isFilePlaying && currentFileNameHash && currentFilePosition && fnvHash(mFileName.c_str()) == currentFileNameHash){
    long previousPosition = ftell(mFile);
    Serial.printf("Resuming playback from position %ld\n", currentFilePosition);
    fseek(mFile, currentFilePosition, SEEK_SET);
    if (ftell(mFile) != currentFilePosition){
      Serial.println("Failed to seek to previous position.");
      fseek(mFile, previousPosition, SEEK_SET);
    }
  }
  isFilePlaying = true;
  currentFileNameHash = 0;
  currentFilePosition = 0;

  // keep the file open for reading the frames
  return true;
}


void AVIParser::storePosition(){
  if (mMoviListLength && mFile)
  {
    currentFileNameHash = fnvHash(mFileName.c_str());
    currentFilePosition = ftell(mFile);
    currentMoviListLength = mMoviListLength;
    Serial.printf("Storing file position %ld for file hash %u\n", currentFilePosition, currentFileNameHash);
  }
  else {
    isFilePlaying = false;
  }
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
    currentFilePosition = ftell(mFile);
    return header;
  }
  else {
    // no more chunks
    Serial.println("No more data");
    isFilePlaying = false;
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
  return 0;
}