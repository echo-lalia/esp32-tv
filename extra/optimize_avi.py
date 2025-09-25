# Disassemble and reassemble AVI files in optimal format for playback on the ESP32TV


import os
import subprocess
import argparse


parser = argparse.ArgumentParser()
parser.add_argument("input_path")
parser.add_argument("output_path")
parser.add_argument("--force", action="store_true", help="Force overwriting of files.")
parser.add_argument("--dry_run", action="store_true", help="Just print the changes that would be made without actually making them.")
parser.add_argument("--remove_junk", type=bool, default=True, help="Remove JUNK chunks from the AVI file. (This will only save a few bytes, but is usually safe)")
parser.add_argument("--remove_unused", type=bool, default=True, help="Remove chunks types that are not used by the ESP32-TV player. (This will remove optional index chunks, which will cause issues with some players)")
parser.add_argument("--remove_empty_frames", type=bool, default=False, help="Remove any empty video frames from the AVI file. (This may cause audio/video sync issues with some players)")
parser.add_argument("--fix_big_audio_chunk", type=bool, default=True, help="Find and split up a final big (and out of order) audio chunk. (this can break any present index chunks, and therefore cause glitches in some players)")

args = parser.parse_args()
input_path = args.input_path
output_path = args.output_path
force_overwrite = args.force
dry_run = args.dry_run

remove_junk = args.remove_junk
remove_unused_chunk_types = args.remove_unused
remove_empty_frames = args.remove_empty_frames
fix_big_audio_chunk = args.fix_big_audio_chunk



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

    def get_bytes(self) -> bytes:
        output = self.chunk_type
        output += self.size.to_bytes(4, 'little')
        output += self.data
        if self.size % 2 != 0:
            output += b"\x00"
        return output


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

    def fix_big_audio_chunk(self) -> int:
        """Split up a final, large audio chunk, if present. Returns number of bytes added.
        
        AVI files encoded with ffmpeg sometimes have a single audio chunk near the end
        that is much larger than the rest. (sometimes followed by one very small chunk, but otherwise is the final chunk in the file).
        This can mess up playback because the final frames are therefore out of sync with the audio.
        As a workaround, we can look for that final large audio chunk, and split it up into smaller chunks, spaced out.
        """
        assert self.list_type == b'movi'
        added_bytes = 0

        # Find the largest audio chunk size, and average audio chunk size
        largest_audio_size = 0
        audio_sizes = {}
        audio_chunk_count = 0
        largest_chunk_index = -1
        for idx, chunk in enumerate(self.data):
            if chunk.chunk_type == b'01wb':
                audio_chunk_count += 1
                if chunk.size in audio_sizes:
                    audio_sizes[chunk.size] += 1
                else:
                    audio_sizes[chunk.size] = 1
                if chunk.size > largest_audio_size:
                    largest_audio_size = chunk.size
                    largest_chunk_index = idx

        if audio_chunk_count == 0:
            raise ValueError("No audio chunks found in movi list.")
        # Get the most common audio chunk size (the mode)
        average_audio_size = max(audio_sizes, key=audio_sizes.get)
        if largest_audio_size < average_audio_size * 2:
            # No audio chunk is more than twice the average size, so we don't need to do anything.
            return 0
        # Split the video stream at the largest audio chunk
        good_data = self.data[:largest_chunk_index]
        bad_video_chunks = []
        bad_audio_chunks = []
        for chunk in self.data[largest_chunk_index:]:
            if chunk.chunk_type == b'00dc':
                bad_video_chunks.append(chunk)
            elif chunk.chunk_type == b'01wb':
                bad_audio_chunks.append(chunk)
            else:
                print(f"Warning: unexpected chunk type {chunk.chunk_type} found while splitting movi list. (it will be discarded)")
        if len(bad_audio_chunks) > 2:
            print(
                f"Warning: found too many 'bad' audio chunks while attempting fix_big_audio_chunk (found {len(bad_audio_chunks)}, but expected 1 to 2)."
                "The fix may not work correctly for this file, so it will be skipped.",
            )
            return 0
        if not bad_audio_chunks or not bad_video_chunks:
            print("Warning: no 'bad' audio or video chunks found while attempting fix_big_audio_chunk. The fix will be skipped.")
            return 0

        bad_audio_data = b"".join([chunk.data for chunk in bad_audio_chunks])
        new_bad_audio_chunks = []
        while len(bad_audio_data) > 0:
            chunk_size = min(average_audio_size, len(bad_audio_data))
            new_chunk_data = bad_audio_data[:chunk_size]
            bad_audio_data = bad_audio_data[chunk_size:]
            new_bad_audio_chunk = RIFFChunk(b'01wb', len(new_chunk_data), new_chunk_data)
            new_bad_audio_chunks.append(new_bad_audio_chunk)
        added_bytes = len(new_bad_audio_chunks) * 8  - (len(bad_audio_chunks) * 8)
        added_bytes += sum(chunk.padded_size for chunk in new_bad_audio_chunks) - sum(chunk.padded_size for chunk in bad_audio_chunks)
        
        # Reinterleave the video and audio chunks
        num_splits = min(len(bad_video_chunks), len(new_bad_audio_chunks))
        while num_splits > 0:
            vid_chunks_per_split = len(bad_video_chunks) // num_splits
            audio_chunks_per_split = len(new_bad_audio_chunks) // num_splits
            # Evenly distribute the new audio and video chunks
            good_data += new_bad_audio_chunks[:audio_chunks_per_split]
            new_bad_audio_chunks = new_bad_audio_chunks[audio_chunks_per_split:]
            good_data += bad_video_chunks[:vid_chunks_per_split]
            bad_video_chunks = bad_video_chunks[vid_chunks_per_split:]
            num_splits -= 1
        # Add any remaining chunks
        good_data += bad_video_chunks
        good_data += new_bad_audio_chunks

        self.data = good_data
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

    def fix_big_audio_chunk(self):
        added_bytes = self.movi_list.fix_big_audio_chunk()
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

    for in_path, out_path in in_out_filepaths:
        riff_file = RIFFFile(in_path)

        if remove_junk:
            riff_file.remove_junk()
        if remove_unused_chunk_types:
            riff_file.remove_unused_chunk_types()
        if remove_empty_frames:
            riff_file.remove_empty_frames()
        if fix_big_audio_chunk:
            riff_file.fix_big_audio_chunk()

        if dry_run:
            print(f"{in_path} -> {out_path}")
            print(riff_file)
        else:
            os.makedirs(os.path.dirname(out_path), exist_ok=True)
            with open(out_path, "wb") as out_file:
                out_file.write(riff_file.get_bytes())

