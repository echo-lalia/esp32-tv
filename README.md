# ESP32 Video Player

Display AVI video from an SDCard on a Cheap Yellow Display.

This video player reads MJPEG video and PCM audio from an AVI container, and can draw it to the display with a peak of about 20fps (it supports variable-framerate video).


</br>

**This program is a work-in-progress, and is based on atomic14's [esp32-tv](https://github.com/atomic14/esp32-tv) repo (which has code for a wifi video streaming client and server)**  

The source repo has many additional supported boards, and more support for various output methods. However, I had issues with video playback from the SDCard.  
Because I was not super comfortable with PlatformIO or C++ development, and I don't have access to the hardware to test the various options supported by the original repo, I decided to simplify things by trimming the code down to just the logic related to SDCard video playback on my board.  
> Note: It may still be possible to re-add support for additional video/audio output types by pulling code from the source repo. Feel free to open a pull request if you want to add support for your hardware to this fork!

Almost all the configuration is done in the `platformio.ini` file. You can use the existing settings as the basis for new boards.


</br>

## Support for AVI files on an SDCard

This player uses AVI files with MJPEG video, and 8-bit pcm audio.  
The rate of the audio must match the rate set in `platformio.ini` to play correctly.  
Variable framerates are supported, as the timing is controlled by the audio task.

I wrote a little Python script in `extra/` that can convert a single video or a folder into the required format, along with several  optional enhancements, such as a sharpening filter, and a CRT shader.  
You'll need Python 3 and ffmpeg installed (and both must be in your PATH) to use the script.  
Example usage:
```
python3 extra/process_video.py input.mp4 output.avi --size 280 240 --crt --sharpen
```

And here's the full output of `python3 extra/process_video.py -h`:
```
usage: process_video.py [-h] [--size SIZE SIZE] [--fps_max FPS_MAX] [--fps_min FPS_MIN] [--frame_drop FRAME_DROP] [--audio_rate AUDIO_RATE] [--quality QUALITY] [--crt] [--sharpen] [--dry_run] [--force] input_path output_path

positional arguments:
  input_path
  output_path

options:
  -h, --help            show this help message and exit
  --size SIZE SIZE      If provided, should be two integers representing the width and height of the output video.
  --fps_max FPS_MAX     The maximum target FPS to allow.
  --fps_min FPS_MIN     The minimum target FPS to allow.
  --frame_drop FRAME_DROP
                        The aggresiveness of the frame dropping filter (from 0.0 to 1.0). Lower values drop less frames, higher values drop more.
  --audio_rate AUDIO_RATE
                        The audio rate to use for the output video. This must match the audio rate set in your platformio.ini file.
  --quality QUALITY     The jpeg quality to use for the video. Should be a value from 0-31, where lower numbers are higher quality, and higher numbers have a smaller file size.
  --crt                 If provided, enable the CRT filter.
  --sharpen             If provided, adds a sharpening filter to the video, which can improve detail on the low-resolution output.
  --dry_run             Just print the changes that would be made without actually making them.
  --force               Force overwriting of files.
```