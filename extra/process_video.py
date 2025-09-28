import os
import subprocess
import argparse


parser = argparse.ArgumentParser()
parser.add_argument("input_path")
parser.add_argument("output_path")
parser.add_argument("--size", nargs=2, type=int, default=[320, 240], help="If provided, should be two integers representing the width and height of the output video.")
parser.add_argument("--fps_max", type=int, default=20, help="The maximum target FPS to allow.")
parser.add_argument("--fps_min", type=int, default=6, help="The minimum target FPS to allow.")
parser.add_argument("--frame_drop", type=float, default=0.5, help="The aggresiveness of the frame dropping filter (from 0.0 to 1.0). Lower values drop less frames, higher values drop more.")
parser.add_argument("--audio_rate", type=int, default=16000, help="The audio rate to use for the output video. This must match the audio rate set in your platformio.ini file.")
parser.add_argument("--quality", type=int, default=31, help="The jpeg quality to use for the video. Should be a value from 0-31, where lower numbers are higher quality, and higher numbers have a smaller file size.")
parser.add_argument("--crt", type=str, default="True", help="If True, enable the CRT filter.")
parser.add_argument("--sharpen", type=str, default="True", help="If True, adds a sharpening filter to the video, which can improve detail on the low-resolution output.")
parser.add_argument("--normalize_audio", type=str, default="False", help="If True, apply loudness normalization to the audio track.")
parser.add_argument("--relpath", action="store_true", help="Keep the relative directory structure for output files (otherwise collapse output files into one folder).")
parser.add_argument("--dry_run", action="store_true", help="Just print the changes that would be made without actually making them.")
parser.add_argument("--force", action="store_true", help="Force overwriting of files.")


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
size = args.size
fps_max = args.fps_max
fps_min = args.fps_min
frame_drop = args.frame_drop
audio_rate = args.audio_rate
jpeg_quality = args.quality
enable_crt = smart_str_bool(args.crt)
enable_sharpen = smart_str_bool(args.sharpen)
enable_audio_normalization = smart_str_bool(args.normalize_audio)
keep_relpath = args.relpath
force_overwrite = args.force
dry_run = args.dry_run


VIDEO_EXTENSIONS = {".mkv", ".avi", ".mp4", ".mov", ".gif", ".webm", ".mjpeg"}

CRT_SHADER_PATH = os.path.join(os.path.dirname(__file__), "crt_shader.hlsl")

OUT_EXTENSION = "avi"



def mix(val1, val2, fac:float = 0.5) -> float:
    """Mix two values to the weight of fac."""
    return (val2 * fac) + (val1 * (1.0 - fac))


def roundi(val: float) -> int:
    return int(round(val))


def _format_ffmpeg_path(path: str) -> str:
    """Escape special ffmpeg filter characters so that a file path can be input."""
    _COLON = r"\\:"
    _BSLASH = "/\\"
    return path.replace("\\", _BSLASH).replace(":", _COLON)


def _get_framerate_filter(fps_min: int, fps_max: int, frame_drop: float) -> str:
    """Get a filter that first limits the framerate, then drops similar frames."""
    # Aggresive:
    # frac=0.9:lo=64*128:hi=64*192:max=20
    # Subtle:
    # frac=0.3:lo=64*16:hi=64*32:max=5
    
    _hi = roundi(mix(64*16, 64*192, frame_drop))  # If any 8*8 area has at least this difference, the frame is kept.  
    _lo = roundi(mix(64*5, 64*128, frame_drop))   # If an 8*8 area has at least this difference, it counts for `_frac`
    _frac = mix(0.3, 0.9, frame_drop)             # If at least this fraction of 8*8 areas beat the `_lo` threshold, the frame is kept.
    _max = roundi(fps_max / fps_min)  # Max number of frames to drop (in a row)

    return f", minterpolate=fps={fps_max}:mi_mode=dup, mpdecimate=frac={_frac}:lo={_lo}:hi={_hi}:max={_max}"


def process_video_file(
        input_path,
        output_path,
        size: tuple[int, int] = (280, 240),
        fps_max: int = 20,
        fps_min: int = 6,
        frame_drop: float = 0.5,
        sharpen=True,
        crt_shader=True,
        jpeg_quality=31,
        audio_rate=16000,
        normalize_audio=True,
    ):
    
    # Ensure the target directory exists
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    # Scale and crop the video stream
    base_filter = f"scale={size[0]}:{size[1]}:force_original_aspect_ratio=increase, crop={size[0]}:{size[1]}"
    # Optional sharpness filter.
    _sharp_filter = ", cas=strength=0.9, unsharp=luma_msize_x=13:luma_msize_y=13:luma_amount=1.0" if sharpen else ""
    # Limit the framerate, then drop similar frames.
    _framerate_filter = _get_framerate_filter(fps_min, fps_max, frame_drop)

    # # Init vulkan if using a shader (this is required by libplacebo) and set shader filter.
    _shader_init_hw = "-init_hw_device vulkan" if crt_shader else ""
    _crt_shader = f", libplacebo=custom_shader_path={_format_ffmpeg_path(CRT_SHADER_PATH)}" if crt_shader else ""

    filter_string = f'-vf "{base_filter}{_sharp_filter}{_framerate_filter}{_crt_shader}"'

    normalize_audio_filter = '-filter:a "loudnorm"' if normalize_audio else ''

    ffmpeg_cmd = f"""ffmpeg -i "{input_path}" -y {_shader_init_hw} {filter_string} -c:v mjpeg -q:v {jpeg_quality} -fps_mode vfr -acodec pcm_u8 {normalize_audio_filter} -ar {audio_rate} -ac 1 "{output_path}" """

    print()
    print(ffmpeg_cmd)
    print()

    subprocess.run(ffmpeg_cmd)


def _replace_extension(file_name: str) -> str:
    """Replace the file extension with `OUT_EXTENSION`."""
    return os.extsep.join([os.path.splitext(file_name)[0], OUT_EXTENSION])


def _get_relative_output(input_file: str, input_path: str, output_path: str) -> str:
    """Conditionaly figure out the correct output path to use for the input file.

    If a full file name is provided as an output_path, it will be returned.
    If a directory is provided as an output path, the result will use the input file name.
    If a directory is provided as both the input path and output path:
        If `keep_relpath` is `True`, the output path will copy the file structure of the
        input file relative to the input path.
        Otherwise, the input filename will just be used in the output folder.
    """
    if os.path.isdir(output_path):
        if os.path.samefile(input_file, input_path):
            # Input file is same as input path, and output path is directory;
            # Use input filename as new file name.
            name = os.path.basename(input_file)
            # Add correct extension onto output path 
            return _replace_extension(os.path.join(output_path, name))
        # Input file is different from input path, and output is a directory.
        if keep_relpath:
            # We should find the relative path to the file, and copy that for the output.
            relative_path = os.path.relpath(input_file, input_path)
            return _replace_extension(os.path.join(output_path, relative_path))
        else:
            # Append the filename to the output directory (collapsing the file structure to one folder).
            name = os.path.basename(input_file)
            return _replace_extension(os.path.join(output_path, name))
    # Output path is not a directory. We must assume this is the path we should save to.
    return output_path


def _find_video_files_in_dir(scan_path: str) -> list[os.DirEntry]:
    """Recursively scan a given directory for video files."""
    files_found = []
    for dir_entry in os.scandir(scan_path):
        if dir_entry.is_dir():
            files_found += _find_video_files_in_dir(dir_entry.path)
        elif dir_entry.is_file() and os.path.splitext(dir_entry.name)[1].casefold() in VIDEO_EXTENSIONS:
            files_found.append(dir_entry)
    return files_found


def get_file_paths(input_path: str, output_path: str) -> list[tuple[str, str]]:
    """Get a list of input/output file path pairs.
    
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


def _add_num_to_path(path: str, num: int) -> str:
    """Add an integer to a file name."""
    path, ext = os.path.splitext(path)
    return os.extsep.join(f"{path}_{num}", OUT_EXTENSION)


def prevent_duplicate_outpaths(in_out_filepaths: list[tuple[str, str]]) -> list[tuple[str, str]]:
    """Ensure there are no duplicate output paths by appending numbers to filenames."""
    out_paths = []
    replacements = {}
    for in_path, out_path in in_out_filepaths:
        if out_path in out_paths:
            replacements[in_path] = _add_num_to_path(out_path, out_paths.count(out_path))
    new_in_out_paths = []
    for in_path, out_path in in_out_filepaths:
        if in_path in replacements:
            out_path = replacements[in_path]
        new_in_out_paths.append((in_path, out_path))
    return 


def any_duplicate_outpaths(in_out_filepaths: list[tuple[str, str]]) -> bool:
    """Return true if any output filepaths are duplicates."""
    out_paths = []
    for _, out_path in in_out_filepaths:
        if out_path in out_paths:
            return True
        out_paths.append(out_path)
    return False


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
    # Get a list of input/output file path pairs based on provided arguments
    in_out_filepaths = get_file_paths(input_path, output_path)

    # If we are not preserving the input file structure, we must ensure there are no duplicate output paths.
    if not keep_relpath:
        while any_duplicate_outpaths(in_out_filepaths):
            print("Found duplicate output paths; attempting to fix...")
            in_out_filepaths = prevent_duplicate_outpaths(in_out_filepaths)

    # Confirm whether or not we should replace any extant files
    if not force_overwrite:
        in_out_filepaths = verify_overwrite(in_out_filepaths)

    if dry_run:
        print("Options:\n---")
        print(f"size:            {size}")
        print(f"fps_max:         {fps_max}")
        print(f"fps_min:         {fps_min}")
        print(f"frame_drop:      {frame_drop}")
        print(f"audio_rate:      {audio_rate}")
        print(f"jpeg_quality:    {jpeg_quality}")
        print(f"enable_crt:      {enable_crt}")
        print(f"enable_sharpen:  {enable_sharpen}")
        print(f"enable_audio_normalization: {enable_audio_normalization}")
        print(f"keep_relpath: {keep_relpath}")
        print(f"force_overwrite: {force_overwrite}")
        print("---")
        for inpt, outpt in in_out_filepaths:
            print(f"'{inpt}' -> '{outpt}'")
        if not in_out_filepaths:
            print("No files written.")
    
    else:
        for inpt, outpt in in_out_filepaths:
            process_video_file(
                inpt, outpt,
                size=size,
                fps_max=fps_max,
                fps_min=fps_min,
                frame_drop=frame_drop,
                sharpen=enable_sharpen,
                crt_shader=enable_crt,
                jpeg_quality=jpeg_quality,
                audio_rate=audio_rate,
                normalize_audio=enable_audio_normalization,
            )
