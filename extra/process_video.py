import os
import subprocess
import argparse


parser = argparse.ArgumentParser()
parser.add_argument("input_path")
parser.add_argument("output_path")

args = parser.parse_args()
input_path = args.input_path
output_path = args.output_path



CRT_SHADER_PATH = os.path.join(os.path.dirname(__file__), "crt_shader.hlsl")


def _format_ffmpeg_path(path: str) -> str:
    """Escape special ffmpeg filter characters so that a file path can be input."""
    _COLON = r"\\:"
    _BSLASH = "/\\"
    return path.replace("\\", _BSLASH).replace(":", _COLON)


# def _step_down_fps_fancy(fps: int, in_tag: str|None = None, out_tag: str|None = None) -> str:
#     """Return a filter graph that steps reduces to the target fps and applies a smear frame like effect."""
#     in_str = f"[{in_tag}]" if in_tag else ""
#     out_str = f"[{out_tag}]" if out_tag else ""
#     # Split the video into two streams
#     fltr = f"{in_str}split[FPS{fps}A][FPS{fps}B];"
#     # Convert the first stream using "dup" mode (no smoothing) and split it again
#     fltr += f"[FPS{fps}A] minterpolate=fps={fps}:mi_mode=dup, split=3[SHARP{fps}A][SHARP{fps}B][SHARP{fps}C];"
#     # Take one of the "sharp" streams, apply edge detection and negate (outputs black edges on white)
#     fltr += f"[SHARP{fps}A] edgedetect, inflate, eq=gamma=10, boxblur=4:2, negate [HARDEDGES{fps}];"

#     # Convert the second stream using "blend" mode to apply smoothing
#     fltr += f"[FPS{fps}B] minterpolate=fps={fps}:mi_mode=blend, split[SMOOTH{fps}A][SMOOTH{fps}B];"
#     # Take one of the smooth streams, apply edge detection (outputs white edges on black)
#     fltr += f"[SMOOTH{fps}A] edgedetect, inflate, eq=gamma=10, boxblur=2:1 [SMOOTHEDGES{fps}];"
#     # subtract both edge streams (resulting in only white smooth edges where there were no black hard edges)
#     fltr += f"[HARDEDGES{fps}][SMOOTHEDGES{fps}]blend=all_mode=subtract, eq=contrast=10.0[EDGES{fps}];"

#     # Use the processed edges as the alpha channel for the "smooth" video
#     fltr += f"[SMOOTH{fps}B][EDGES{fps}]alphamerge[SMOOTHALPHA{fps}];"

#     # Alpha-overlay the smooth edges stream onto the main sharp stream
#     fltr += f"[SHARP{fps}B][SMOOTHALPHA{fps}] overlay[EDGEALPHAOVER{fps}];"

#     # Finally, blend the alpha-overed stream onto the main stream again, but keeping only darker colors (selecting mostly outlines)
#     fltr += f"[EDGEALPHAOVER{fps}][SHARP{fps}C] blend=all_mode=darken{out_str};"

#     return fltr


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
    fltr += f"[SHARP{fps}][SMOOTH{fps}] blend=all_mode=normal:all_opacity=0.3 {out_str}"

    return fltr




def process_video_file(
        input_path,
        output_path,
        size: tuple[int, int] = (280, 240),
        framerates: tuple[int, ...] = (12,),
        sharpen=True,
        crt_shader=True,
        jpeg_quality=29,
        audio_rate=16000
        ):

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

    ffmpeg_cmd = f"""ffmpeg -i "{input_path}" {_shader_init_hw} {filter_string} -c:v mjpeg -q:v {jpeg_quality} -acodec pcm_u8 -af "loudnorm" -ar {audio_rate} -ac 1 "{output_path}" """
    print()
    print(ffmpeg_cmd)
    print()
    subprocess.run(ffmpeg_cmd)



# def process_video_file(
#         input_path,
#         output_path,
#         size: tuple[int, int] = (280, 240),
#         framerates: tuple[int, ...] = (24, 16, 12, 9),
#         unsharp_mask=True,
#         crt_shader=True,
#         jpeg_quality=31,
#         audio_rate=16000
#         ):

#     # TODO: Consider also extracting edges from main "sharp" video, and subtracting those edges from the smooth edges before mixing smooth edges in.

#     # Scale then crop (and optionally apply an unsharp mask to highligh edges), before splitting into two streams
#     _unsharp_filter = "unsharp=luma_msize_x=13:luma_msize_y=13:luma_amount=2.0, " if unsharp_mask else ""
#     base_filter = f"scale={size[0]}:{size[1]}:force_original_aspect_ratio=increase, crop={size[0]}:{size[1]}, {_unsharp_filter}split[BASE1][BASE2]; "

#     # The birst base stream is converted to the target fps by dropping frames (without blending)
#     _sharp_fps_steps = ", ".join([f"minterpolate=fps={fps}:mi_mode=dup" for fps in framerates])
#     base_to_sharp = f"[BASE1] {_sharp_fps_steps}[SHARP]; "

#     # The second base stream is converted to the target fps by smoothly blending frames, then splitting again for further processing.
#     _smooth_fps_steps = ", ".join([f"minterpolate=fps={fps}:mi_mode=blend" for fps in framerates])
#     base_to_smooth = f"[BASE2] {_smooth_fps_steps}, split[SM1][SM2]; "

#     # These filter chains are used to filter for dark lineart.
#     # The first split is equalized to wash out most of the frame, keeping only dark areas (which line art usually is)
#     # Then the second split selects edges (and grows the selection),
#     # and both splits are combined to select (mostly) only dark edges.
#     smooth_to_darkedges_to_smedges = (
#         "[SM1] eq=brightness=1.0:contrast=20.0 [DARKS]; "
#         "[SM2] edgedetect, inflate, eq=gamma=10, boxblur=2:1, negate [EDGES]; "
#         "[DARKS][EDGES]blend=all_mode=lighten [SMEDGES]; "
#     )

#     # Init vulkan if using a shader (this is required by libplacebo) and set shader filter.
#     _shader_init_hw = "-init_hw_device vulkan" if crt_shader else ""
#     _crt_shader = f", libplacebo=custom_shader_path={_format_ffmpeg_path(CRT_SHADER_PATH)}" if crt_shader else ""
#     # Blend the dark edges from [SMEDGES] over the sharp frame to create a faux smear-frame look.
#     blend_sharp_smedges_output = f"[SHARP][SMEDGES] blend=all_mode=darken:all_opacity=0.6{_crt_shader}"

#     filter_string = f'-filter_complex "{base_filter}{base_to_sharp}{base_to_smooth}{smooth_to_darkedges_to_smedges}{blend_sharp_smedges_output}"'

#     ffmpeg_cmd = f"""ffmpeg -i "{input_path}" {_shader_init_hw} {filter_string} -c:v mjpeg -q:v {jpeg_quality} -acodec pcm_u8 -af "loudnorm" -ar {audio_rate} -ac 1 "{output_path}" """

#     subprocess.run(ffmpeg_cmd)

#     # print(ffmpeg_cmd)


if __name__ == "__main__":
    process_video_file(input_path, output_path)


