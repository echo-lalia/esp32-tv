import os
import subprocess
import argparse


parser = argparse.ArgumentParser()
parser.add_argument("input_path")
parser.add_argument("output_path")
parser.add_argument("--size", nargs=2, type=int, default=[280, 240], help="If provided, should be two integers representing the width and height of the output video.")
parser.add_argument("--fps", nargs='*', type=int, default=[12], help="The target FPS to convert to. Multiple values can be provided to step down the fps in increments.")
parser.add_argument("--audio_rate", type=int, default=16000, help="The audio rate to use for the output video. This must match the audio rate set in your platformio.ini file.")
parser.add_argument("--quality", type=int, default=26, help="The jpeg quality to use for the video. Should be a value from 0-31, where lower numbers are higher quality, and higher numbers have a smaller file size.")
parser.add_argument("--crt", action="store_true", help="If provided, enable the CRT filter.")
parser.add_argument("--sharpen", action="store_true", help="If provided, adds a sharpening filter to the video, which can improve detail on the low-resolution output.")
parser.add_argument("--dry_run", action="store_true", help="Just print the changes that would be made without actually making them.")
parser.add_argument("--force", action="store_true", help="Force overwriting of files.")

args = parser.parse_args()
input_path = args.input_path
output_path = args.output_path
size = args.size
fps_steps = args.fps
audio_rate = args.audio_rate
jpeg_quality = args.quality
enable_crt = args.crt
enable_sharpen = args.sharpen
force_overwrite = args.force
dry_run = args.dry_run


VIDEO_EXTENSIONS = {".mkv", ".avi", ".mp4", ".mov", ".gif", ".webm", ".mjpeg"}

CRT_SHADER_PATH = os.path.join(os.path.dirname(__file__), "crt_shader.hlsl")

OUT_EXTENSION = "avi"


def _format_ffmpeg_path(path: str) -> str:
    """Escape special ffmpeg filter characters so that a file path can be input."""
    _COLON = r"\\:"
    _BSLASH = "/\\"
    return path.replace("\\", _BSLASH).replace(":", _COLON)


def _step_down_fps_fancy(fps: int, in_tag: str|None = None, out_tag: str|None = None) -> str:
    """Return a filter graph that steps reduces to the target fps and applies a smear frame like effect."""
    in_str = f"[{in_tag}]" if in_tag else ""
    out_str = f"[{out_tag}];" if out_tag else ""
    # Split the video into two streams
    fltr = f"{in_str}split[FPS{fps}A][FPS{fps}B];"
    # Convert the first stream using "dup" mode (no smoothing)
    fltr += f"[FPS{fps}A] minterpolate=fps={fps}:mi_mode=dup [SHARP{fps}];"

    # Convert the second stream using "blend" mode to apply smoothing
    fltr += f"[FPS{fps}B] minterpolate=fps={fps}:mi_mode=blend [SMOOTH{fps}];"

    # Finally, blend the alpha-overed stream onto the main stream again, with a reduced opacity (in an effort to make effect more subtle)
    fltr += f"[SHARP{fps}][SMOOTH{fps}] blend=all_mode=normal:all_opacity=0.5 {out_str}"

    return fltr


def process_video_file(
        input_path,
        output_path,
        size: tuple[int, int] = (280, 240),
        framerates: tuple[int, ...] = (24, 12),
        sharpen=True,
        crt_shader=True,
        jpeg_quality=31,
        audio_rate=16000
        ):
    
    # Ensure the target directory exists
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    # Scale then crop (and optionally apply an unsharp mask to highligh edges), before splitting into two streams
    _sharp_filter = ", cas=strength=0.9, unsharp=luma_msize_x=13:luma_msize_y=13:luma_amount=1.0" if sharpen else ""
    base_filter = f"[INPUT]scale={size[0]}:{size[1]}:force_original_aspect_ratio=increase, crop={size[0]}:{size[1]}{_sharp_filter}[BASE];"

    # Create a chain of fps-stepdown filters as defined by `framerates`
    _fps_filters = ""
    for idx, fps in enumerate(framerates):
        _in_tag = "BASE" if idx == 0 else f"FPS{framerates[idx-1]}"
        _out_tag = None if idx == len(framerates)-1 else f"FPS{fps}"
        _fps_filters += _step_down_fps_fancy(fps, _in_tag, _out_tag)


    # # Init vulkan if using a shader (this is required by libplacebo) and set shader filter.
    _shader_init_hw = "-init_hw_device vulkan" if crt_shader else ""
    _crt_shader = f", libplacebo=custom_shader_path={_format_ffmpeg_path(CRT_SHADER_PATH)}" if crt_shader else ""

    # filter_string = f'-filter_complex "{base_filter}{base_to_sharp}{base_to_smooth}{smooth_to_darkedges_to_smedges}{blend_sharp_smedges_output}"'
    filter_string = f'-filter_complex "{base_filter}{_fps_filters}{_crt_shader}"'

    ffmpeg_cmd = f"""ffmpeg -i "{input_path}" -y {_shader_init_hw} {filter_string} -c:v mjpeg -q:v {jpeg_quality} -acodec pcm_u8 -af "loudnorm" -ar {audio_rate} -ac 1 "{output_path}" """

    subprocess.run(ffmpeg_cmd)


def _replace_extension(file_name: str) -> str:
    """Replace the file extension with `OUT_EXTENSION`."""
    return os.extsep.join([os.path.splitext(file_name)[0], OUT_EXTENSION])


def _get_relative_output(input_file: str, input_path: str, output_path: str) -> str:
    """Conditionaly figure out the correct output path to use for the input file.
    
    If a full file name is provided as an output_path, it will be returned.
    If a directory is provided as an output path, the result will use the input file name.
    If a directory is provided as both the input path and output path,
    the output path will copy the file structure of the input file relative to the input path.
    """
    if os.path.isdir(output_path):
        if os.path.samefile(input_file, input_path):
            # Input file is same as input path, and output path is directory;
            # Use input filename as new file name.
            name = os.path.basename(input_file)
            # Add correct extension onto output path 
            return _replace_extension(os.path.join(output_path, name))
        # Input file is different from input path, and output is a directory.
        # Therefore, we should find the relative path to the file, and copy that for the output.
        relative_path = os.path.relpath(input_file, input_path)
        return _replace_extension(os.path.join(output_path, relative_path))
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

    # Confirm whether or not we should replace any extant files
    if not force_overwrite:
        in_out_filepaths = verify_overwrite(in_out_filepaths)

    if dry_run:
        print("Options:\n---")
        print(f"size:            {size}")
        print(f"fps_steps:       {fps_steps}")
        print(f"audio_rate:      {audio_rate}")
        print(f"jpeg_quality:    {jpeg_quality}")
        print(f"enable_crt:      {enable_crt}")
        print(f"enable_sharpen:  {enable_sharpen}")
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
                framerates=fps_steps,
                sharpen=enable_sharpen,
                crt_shader=enable_crt,
                jpeg_quality=jpeg_quality,
                audio_rate=audio_rate,
            )
