#pragma once

enum chunk_type {OTHER_CHUNK, AUDIO_CHUNK, VIDEO_CHUNK, RIFF_CHUNK, LIST_CHUNK, EMPTY_CHUNK};

enum class AVIChunkType
{
  VIDEO, AUDIO
};

typedef struct
{
  chunk_type chunkType;
  unsigned int chunkSize;
} ChunkHeader;

#define EMPTY_HEADER (ChunkHeader){EMPTY_CHUNK, 0}
// ChunkHeader EMPTY_HEADER = {EMPTY_CHUNK, 0};


class AVIParser
{
private:
  std::string mFileName;
  AVIChunkType mRequiredChunkType;
  FILE *mFile = NULL;
  long mMoviListPosition = 0;
  long mMoviListLength;

  bool isMoviListChunk(unsigned int chunkSize);

public:
  AVIParser(std::string fname, AVIChunkType requiredChunkType);
  ~AVIParser();
  bool open();
  ChunkHeader getNextHeader();
  size_t getNextChunk(ChunkHeader header, uint8_t **buffer, size_t &bufferLength, bool skipChunk=false);
};