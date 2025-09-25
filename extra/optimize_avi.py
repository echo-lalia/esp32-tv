# Disassemble and reassemble AVI files in optimal format for playback on the ESP32TV


import os
import subprocess
import argparse


parser = argparse.ArgumentParser()
parser.add_argument("input_path")

args = parser.parse_args()
input_path = args.input_path



def indent(string: str, indentation: int=1) -> str:
    lines = string.splitlines(keepends=True)
    output = ""
    for line in lines:
        output += ("  " * indentation) + line
    return output



class RIFFChunk:
    def __init__(self, chunk_type: bytes, size: int, file):
        self.chunk_type = chunk_type
        self.size = size
        self.data = file.read(size)
        if self.size % 2 != 0:
            file.seek(1, 1)
    
    def __repr__(self):
        return f"{self.chunk_type}\t({self.size})"


class RIFFList(RIFFChunk):
    def __init__(self, chunk_type: bytes, size: int, file):
        self.chunk_type = chunk_type
        self.size = size
        self.list_type = file.read(4)
        self.data = self.find_chunks(file, size - 4)

    @staticmethod
    def find_chunks(file, list_size) -> list[RIFFChunk]:
        data = []
        while list_size > 0:
            chunk_type = file.read(4)
            if not chunk_type:
                break
            size = int.from_bytes(file.read(4), 'little')
            if chunk_type == b"LIST":
                data.append(RIFFList(chunk_type, size, file))
            else:
                data.append(RIFFChunk(chunk_type, size, file))
            list_size -= size + 8
            if size % 2 != 0:
                list_size -= 1
        return data

    def __repr__(self):
        string = f"[LIST] <{self.list_type}> <{self.size}>\n"
        for chunk in self.data:
            string += indent(f"{chunk}\n")
        return string


class RIFFFile(RIFFList):
    def __init__(self, path: str):
        self.path = path
        with open(path, "rb") as file:
            chunk_type = file.read(4)
            assert chunk_type == b"RIFF"
            size = int.from_bytes(file.read(4), 'little')
            super().__init__(chunk_type, size, file)

    def __repr__(self):
        string = "[RIFF]\n"
        for chunk in self.data:
            string += indent(f"{chunk}\n")
        return string




def _find_video_files_in_dir(scan_path: str) -> list[os.DirEntry]:
    """Recursively scan a given directory for video files."""
    files_found = []
    for dir_entry in os.scandir(scan_path):
        if dir_entry.is_dir():
            files_found += _find_video_files_in_dir(dir_entry.path)
        elif dir_entry.is_file() and os.path.splitext(dir_entry.name)[1].casefold() == ".avi":
            files_found.append(dir_entry)
    return files_found


def get_file_paths(input_path: str) -> list[str]:
    """Get a list of input file paths.

    If the input path is a single file, it will be the only entry in the list.
    If the input path is a directory, that directory will be scanned recursively to find video files within.
    """
    # Guard against nonexistant inputs
    if not os.path.exists(input_path):
        raise OSError(f"Input path '{input_path}' doesn't exist.")

    input_paths = []

    if os.path.isfile(input_path):
        # This is a single input file. Just process this one.
        input_paths.append(input_path)
        return input_paths

    # Input must be a directory. Scan it to find files within.
    vid_files = _find_video_files_in_dir(input_path)
    for dir_entry in vid_files:
        input_paths.append(dir_entry.path)

    return input_paths


if __name__ == "__main__":
    file_paths = get_file_paths(input_path)
    print(file_paths)

    for path in file_paths:
        print(RIFFFile(path))

