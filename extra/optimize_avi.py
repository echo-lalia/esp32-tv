# Disassemble and reassemble AVI files in optimal format for playback on the ESP32TV


import os
import subprocess
import argparse


parser = argparse.ArgumentParser()
parser.add_argument("input_path")
parser.add_argument("output_path")
parser.add_argument("--force", action="store_true", help="Force overwriting of files.")
parser.add_argument("--dry_run", action="store_true", help="Just print the changes that would be made without actually making them.")
parser.add_argument("--remove_junk", type=str, default="True", help="Remove JUNK chunks from the AVI file. (This is usually safe)")
parser.add_argument("--remove_unused", type=str, default="True", help="Remove chunks types that are not used by the ESP32-TV player. (This will remove optional index chunks, which will cause issues with some players)")
parser.add_argument("--remove_empty_frames", type=str, default="False", help="Remove any empty video frames from the AVI file. (This may cause audio/video sync issues with some players)")
parser.add_argument("--redistribute_audio_frames", type=str, default="True", help="Redistribute audio frames so that they are evenly spaced around the video frames, and there is a maximum of 2 video frames per audio frame. This helps ensure smooth playback on the ESP32TV.")


def smart_str_bool(val: str) -> bool:
    """Convert a string to a boolean value."""
    if val.strip().casefold() in {"true", "t", "1", "yes", "y", "on"}:
        return True
    if val.strip().casefold() in {"false", "f", "0", "no", "n", "off"}:
        return False
    raise ValueError(f"Cannot convert '{val}' to a boolean value.")


args = parser.parse_args()
input_path = args.input_path
output_path = args.output_path
force_overwrite = args.force
dry_run = args.dry_run

remove_junk = smart_str_bool(args.remove_junk)
remove_unused_chunk_types = smart_str_bool(args.remove_unused)
redistribute_audio_frames = smart_str_bool(args.redistribute_audio_frames)
remove_empty_frames = smart_str_bool(args.remove_empty_frames)




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
        if isinstance(file, bytes):
            self.data = file
        else:
            self.data = file.read(size)
            if self.size % 2 != 0:
                file.seek(1, 1)
        self.padded_size = self.size + (1 if self.size % 2 != 0 else 0)
    
    def __repr__(self):
        return f"{self.chunk_type}\t({self.size})"

    def write_bytes(self, out_file) -> int:
        """Write the RIFF bytes to file, and return the number of bytes written."""
        bytes_written = out_file.write(self.chunk_type)
        bytes_written += out_file.write(self.size.to_bytes(4, 'little'))
        bytes_written += out_file.write(self.data)
        if self.size % 2 != 0:
            bytes_written += out_file.write(b"\x00")
        return bytes_written


class RIFFList(RIFFChunk):
    def __init__(self, chunk_type: bytes, size: int, file):
        self.chunk_type = chunk_type
        self.size = size
        self.list_type = file.read(4)
        self.data = self.find_chunks(file, size - 4)
        self.padded_size = self.size + (1 if self.size % 2 != 0 else 0)

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
        string = f"[{self.chunk_type}] <{self.list_type}> <{self.size}>\n"
        for chunk in self.data:
            string += indent(f"{chunk}\n")
        return string

    def write_bytes(self, out_file) -> int:
        """Write the RIFF bytes to file, and return the number of bytes written."""
        bytes_written = out_file.write(self.chunk_type)
        bytes_written += out_file.write(self.size.to_bytes(4, 'little'))
        bytes_written += out_file.write(self.list_type)
        for chunk in self.data:
            bytes_written += chunk.write_bytes(out_file)

        if bytes_written != self.size + 8:
            print(f"Warning: size mismatch in list {self.list_type}| expected size: {self.size + 8}, real size: {bytes_written}")

        if bytes_written % 2 != 0:
            bytes_written += out_file.write(b"\x00")
        return bytes_written

    def get_bytes(self) -> bytes:
        output = self.chunk_type
        output += self.size.to_bytes(4, 'little')
        assert self.size % 2 == 0
        data_bytes = self.list_type
        for chunk in self.data:
            data_bytes += chunk.get_bytes()
        if len(data_bytes) != self.size:
            raise ValueError(f"Size mismatch in list {self.list_type}| expected size: {self.size}, real size: {len(data_bytes)}")
        output += data_bytes
        
        if len(data_bytes) % 2 != 0:
            output += b"\x00"
        return output

    def remove_junk(self) -> int:
        """Recursively remove JUNK chunks, if present, returns number of bytes freed."""
        freed_bytes = 0
        new_data = []
        for chunk in self.data:
            if chunk.chunk_type == b"JUNK":
                freed_bytes += chunk.size + 8
                if chunk.size % 2 != 0:
                    freed_bytes += 1
            elif isinstance(chunk, RIFFList):
                freed_bytes += chunk.remove_junk()
                new_data.append(chunk)
            else:
                new_data.append(chunk)
        self.data = new_data
        self.size -= freed_bytes
        return freed_bytes

    def remove_empty_frames(self) -> int:
        """Remove any blank video frames from the movi list, if present."""
        assert self.list_type == b'movi'
        freed_bytes = 0
        new_data = []
        for chunk in self.data:
            if chunk.chunk_type == b'00dc' and chunk.size == 0:
                freed_bytes += chunk.size + 8
                if chunk.size % 2 != 0:
                    freed_bytes += 1
            else:
                new_data.append(chunk)
        self.data = new_data
        self.size -= freed_bytes
        return freed_bytes

    def redistribute_audio_frames(self) -> int:
        """Combine, then split, and redistribute audio frames, so that there are ~2 video frames per audio frame. Returns number of bytes added."""
        assert self.list_type == b'movi'

        # Sort video and audio frames.
        source_video_chunks = []
        source_audio_chunks = []
        for chunk in self.data:
            if chunk.chunk_type == b'01wb':
                source_audio_chunks.append(chunk)
            elif chunk.chunk_type == b'00dc':
                source_video_chunks.append(chunk)
            else:
                print(f"WARNING: found chunk of type {chunk.chunk_type} in movi list. This script will discard this chunk.")
        
        if not (source_audio_chunks and source_video_chunks):
            print("WARNING: Audio or video chunks are empty! Can't redistribute them!")
            return 0

        # Extract audio data (We're using a bytearray/memoryview rather than bytes for speed)
        audio_data_len = sum(chunk.size for chunk in source_audio_chunks)
        audio_array = bytearray(audio_data_len)
        audio_data = memoryview(audio_array)
        current_index = 0
        for chunk in source_audio_chunks:
            audio_data[current_index:current_index + chunk.size] = chunk.data
            current_index += chunk.size

        # find optimal audio chunk length to maintain 2 frames per audio chunk
        optimal_audio_size = int(len(audio_data) / len(source_video_chunks) * 2)
        # Keep the chunk sizes even.
        if optimal_audio_size % 2 != 0:
            optimal_audio_size += 1
        print(f"\t\t - Calculated optimal audio chunk size: {optimal_audio_size}")

        # Create the new audio chunks
        new_audio_chunks = []
        while audio_data:
            this_chunk_data = bytes(audio_data[:optimal_audio_size])
            audio_data = audio_data[optimal_audio_size:]
            new_audio_chunk = RIFFChunk(b'01wb', len(this_chunk_data), this_chunk_data)
            new_audio_chunks.append(new_audio_chunk)
        
        # interleave the new video and audio chunks together
        remaining_audio_chunks = new_audio_chunks.copy()
        remaining_video_chunks = source_video_chunks.copy()
        # Video stream should always start with one audio and one video chunk
        new_interleave_data = [remaining_video_chunks.pop(0), remaining_audio_chunks.pop(0)]
        while remaining_audio_chunks:
            frames_this_split = int(len(remaining_video_chunks) / len(remaining_audio_chunks))
            new_interleave_data += remaining_video_chunks[:frames_this_split]
            remaining_video_chunks = remaining_video_chunks[frames_this_split:]
            new_interleave_data.append(remaining_audio_chunks.pop(0))
        # Add any final video chunks
        new_interleave_data += remaining_video_chunks

        # Calculate byte difference.
        added_bytes = 8*len(new_audio_chunks) - 8*len(source_audio_chunks)
        added_bytes += sum(chunk.padded_size for chunk in new_audio_chunks) - sum(chunk.padded_size for chunk in source_audio_chunks)

        self.data = new_interleave_data
        self.size += added_bytes
        return added_bytes




class RIFFFile(RIFFList):
    def __init__(self, path: str):
        self.path = path
        with open(path, "rb") as file:
            chunk_type = file.read(4)
            assert chunk_type == b"RIFF"
            size = int.from_bytes(file.read(4), 'little')
            super().__init__(chunk_type, size, file)
        self.movi_list = self.find_movi_list()
        if not self.movi_list:
            print(self)
            raise ValueError("No 'movi' list found in AVI file.")

    def find_movi_list(self) -> RIFFList | None:
        """Find and return the 'movi' list, if present."""
        for chunk in self.data:
            if isinstance(chunk, RIFFList) and chunk.list_type == b'movi':
                return chunk
        return None

    def remove_unused_chunk_types(self):
        """Remove all but the mandatory list types from the root RIFFFile, if present."""
        freed_bytes = 0
        required_list_types = {b'hdrl', b'movi'}
        new_data = []
        for chunk in self.data:
            keep_chunk = isinstance(chunk, RIFFList) and chunk.list_type in required_list_types
            if keep_chunk:
                new_data.append(chunk)
            else:
                freed_bytes += chunk.size + 8
                if chunk.size % 2 != 0:
                    freed_bytes += 1
        self.data = new_data
        self.size -= freed_bytes

    def remove_empty_frames(self):
        """Remove any blank video frames from the movi list, if present."""
        freed_bytes = self.movi_list.remove_empty_frames()
        self.size -= freed_bytes

    def redistribute_audio_frames(self):
        added_bytes = self.movi_list.redistribute_audio_frames()
        self.size += added_bytes


def _get_relative_output(input_file: str, input_path: str, output_path: str) -> str:
    """Conditionaly figure out the correct output path to use for the input file.

    If a full file name is provided as an output_path, it will be returned.
    If a directory is provided as an output path, the result will use the input file name.
    If a directory is provided as both the input path and output path,
    the input filename will just be used in the output folder.
    """
    if os.path.isdir(output_path):
        if os.path.samefile(input_file, input_path):
            # Input file is same as input path, and output path is directory;
            # Use input filename as new file name.
            name = os.path.basename(input_file)
            # Add correct extension onto output path 
            return os.path.join(output_path, name)
        # Input file is different from input path, and output is a directory.
        # Append the filename to the output directory (collapsing the file structure to one folder).
        name = os.path.basename(input_file)
        return os.path.join(output_path, name)
    # Output path is not a directory. We must assume this is the path we should save to.
    return output_path


def _find_video_files_in_dir(scan_path: str) -> list[os.DirEntry]:
    """Recursively scan a given directory for video files."""
    files_found = []
    for dir_entry in os.scandir(scan_path):
        if dir_entry.is_dir():
            files_found += _find_video_files_in_dir(dir_entry.path)
        elif dir_entry.is_file() and os.path.splitext(dir_entry.name)[1].casefold() == ".avi":
            files_found.append(dir_entry)
    return files_found


def get_file_paths(input_path: str, output_path: str) -> list[(str, str)]:
    """Get a list of input file paths.

    If the input path is a single file, it will be the only entry in the list.
    If the input path is a directory, that directory will be scanned recursively to find video files within.
    """
    # Guard against nonexistant inputs
    if not os.path.exists(input_path):
        raise OSError(f"Input path '{input_path}' doesn't exist.")

    in_out_pairs = []

    if os.path.isfile(input_path):
        # This is a single input file. Just process this one.
        in_out_pairs.append((
            input_path,
            _get_relative_output(input_path, input_path, output_path),
        ))
        return in_out_pairs

    # Input must be a directory. Scan it to find files within.
    vid_files = _find_video_files_in_dir(input_path)
    for dir_entry in vid_files:
        in_out_pairs.append((
            dir_entry.path,
            _get_relative_output(dir_entry.path, input_path, output_path),
        ))

    return in_out_pairs


def verify_overwrite(in_out_filepaths: list[tuple[str, str]]) -> list[tuple[str, str]]:
    """If any of the given files already exist, confirm whether or not we should overwrite the files."""
    extant_outputs = []
    for _, outpt in in_out_filepaths:
        if os.path.exists(outpt):
            extant_outputs.append(outpt)

    if extant_outputs:
        if len(extant_outputs) == 1:
            print(f"'{extant_outputs[0]}' already exists. Overwrite?")
        else:
            print(f"{len(extant_outputs)} / {len(in_out_filepaths)} output files already exist. Overwrite them? ('y' to overwrite, 'n' to abort, 'skip' to skip existing files)")
        response = input("y/N/skip: ").casefold()
        if response == "y":
            return in_out_filepaths

        if "skip" in response:
            # Return only files that don't already exist
            return [(inpt, outpt) for inpt, outpt in in_out_filepaths if outpt not in extant_outputs]
        
        # User said no, or provided an unsupported response. Abort!
        return []
    
    # If none of the output files exist, we're all good!
    return in_out_filepaths



if __name__ == "__main__":
    in_out_filepaths = get_file_paths(input_path, output_path)

    # Confirm whether or not we should replace any extant files
    if not force_overwrite:
        in_out_filepaths = verify_overwrite(in_out_filepaths)

    print()

    for idx, in_out in enumerate(in_out_filepaths):
        in_path, out_path = in_out
        print(f" [{idx+1} / {len(in_out_filepaths)}] Processing '{in_path}' -> '{out_path}'...")
        riff_file = RIFFFile(in_path)

        if remove_junk:
            print("\tRemoving JUNK...")
            riff_file.remove_junk()
        if remove_unused_chunk_types:
            print("\tRemoving runused chunks...")
            riff_file.remove_unused_chunk_types()
        if redistribute_audio_frames:
            print("\tRedistributing audio frames...")
            riff_file.redistribute_audio_frames()
        if remove_empty_frames:
            print("\tRemoving empty frames...")
            riff_file.remove_empty_frames()

        if dry_run:
            print(f"{in_path} -> {out_path}")
            print(riff_file)
        else:
            print("\tWriting output...")
            os.makedirs(os.path.dirname(out_path), exist_ok=True)
            with open(out_path, "wb") as out_file:
                riff_file.write_bytes(out_file)
