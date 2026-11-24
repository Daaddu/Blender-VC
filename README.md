# Blender-VC

Voice commands for common Blender 3D operations.

## Install

1. In Blender, open **Edit > Preferences > Add-ons > Install...** and select
   `blender_voice_commands.py`.
2. Enable the **Voice Commands** add-on.
3. For microphone input, install `SpeechRecognition` and `PyAudio` into
   Blender's Python environment. The add-on still supports typed commands
   without these optional packages.

Open the **Voice** tab in the 3D View sidebar. Click **Listen**, speak a
command, and the result is executed on Blender's main thread.

Supported commands include:

- `create cube`, `create sphere`, `create cylinder`, `create cone`, `create torus`
- `move 1 0 0`, `rotate 0 0 1`, `scale 2 2 2`
- `delete selected`, `delete all`, `save`

The parser can be tested without Blender with:

```sh
python -m unittest test_blender_voice_commands.py
```