import os
import subprocess
import argparse



CRT_SHADER_PATH = os.path.join(__file__, "crt_shader.hlsl")



def process_video_file(
        input_path,
        output_path,
        size: tuple[int, int] = (280, 240),
        framerates: tuple[int, ...] = (24, 10),
        unsharp_mask=True,
        crt_shader=True,
        jpeg_quality=31,
        audio_rate=8000
        ):

    # Scale then crop (and optionally apply an unsharp mask to highligh edges), before splitting into two streams
    _unsharp_filter = "unsharp=luma_msize_x=13:luma_msize_y=13:luma_amount=2.0, " if unsharp_mask else ""
    base_filter = f"scale={size[0]}:{size[1]}:force_original_aspect_ratio=increase, crop={size[0]}:{size[1]}, {_unsharp_filter}split[BASE1][BASE2]; "

    # The birst base stream is converted to the target fps by dropping frames (without blending)
    _sharp_fps_steps = ", ".join([f"minterpolate=fps={fps}:mi_mode=dup" for fps in framerates])
    base_to_sharp = f"[BASE1] {_sharp_fps_steps}[SHARP]; "

    # The second base stream is converted to the target fps by smoothly blending frames, then splitting again for further processing.
    _smooth_fps_steps = ", ".join([f"minterpolate=fps={fps}:mi_mode=blend" for fps in framerates])
    base_to_smooth = f"[BASE2] {_smooth_fps_steps}, split[SM1][SM2]; "

    # These filter chains are used to filter for dark lineart.
    # The first split is equalized to wash out most of the frame, keeping only dark areas (which line art usually is)
    # Then the second split selects edges (and grows the selection),
    # and both splits are combined to select (mostly) only dark edges.
    smooth_to_darkedges_to_smedges = (
        "[SM1] eq=brightness=1.0:contrast=20.0 [DARKS]; "
        "[SM2] edgedetect, inflate, eq=gamma=10, boxblur=2:1, negate [EDGES]; "
        "[DARKS][EDGES]blend=all_mode=lighten [SMEDGES]; "
    )

    # Init vulkan if using a shader (this is required by libplacebo) and set shader filter.
    _shader_init_hw = "-init_hw_device vulkan" if crt_shader else ""
    _crt_shader = f", libplacebo=custom_shader_path='{CRT_SHADER_PATH}'" if crt_shader else ""
    # Blend the dark edges from [SMEDGES] over the sharp frame to create a faux smear-frame look.
    blend_sharp_smedges_output = f"[SHARP][SMEDGES] blend=all_mode=darken:all_opacity=0.6{_crt_shader}"

    filter_string = f'-filter_complex "{base_filter}{base_to_sharp}{base_to_smooth}{smooth_to_darkedges_to_smedges}{blend_sharp_smedges_output}"'

    ffmpeg_cmd = f"""ffmpeg -i "{input_path}" {_shader_init_hw} {filter_string} -c:v mjpeg -q:v {jpeg_quality} -acodec pcm_u8 -af "loudnorm" -ar {audio_rate} -ac 1 "{output_path}" """

    # print(ffmpeg_cmd)

