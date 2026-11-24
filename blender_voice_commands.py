"""Voice commands for common Blender modelling operations.

Install this file as a Blender add-on.  The command parser is deliberately
independent of Blender so it can also be used by tests or other frontends.
"""

from __future__ import annotations

from dataclasses import dataclass
import queue
import re
import threading

bl_info = {
    "name": "Blender Voice Commands",
    "author": "Blender-VC",
    "version": (1, 0, 0),
    "blender": (3, 0, 0),
    "location": "3D View > Sidebar > Voice",
    "category": "3D View",
}


@dataclass(frozen=True)
class Command:
    """A parsed command ready to be executed in Blender."""

    action: str
    values: tuple = ()


_NUMBER = r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)"
_TRIPLE = rf"({_NUMBER})\s+({_NUMBER})\s+({_NUMBER})"
_OBJECTS = "cube|sphere|cylinder|cone|torus"


def parse_command(text: str) -> Command:
    """Parse a spoken command, raising ValueError when it is unsupported."""
    normalized = re.sub(r"\s+", " ", text.strip().lower())
    if not normalized:
        raise ValueError("Say a command first")

    match = re.fullmatch(rf"(?:add|create)\s+({_OBJECTS})", normalized)
    if match:
        return Command("add", (match.group(1),))

    if normalized in {"delete", "delete selected", "remove selected"}:
        return Command("delete")
    if normalized in {"delete all", "remove all"}:
        return Command("delete_all")
    if normalized in {"save", "save file"}:
        return Command("save")

    for action, aliases in (
        ("move", ("move", "translate")),
        ("rotate", ("rotate",)),
        ("scale", ("scale",)),
    ):
        prefix = "(?:" + "|".join(aliases) + ")"
        match = re.fullmatch(rf"{prefix}\s+{_TRIPLE}", normalized)
        if match:
            return Command(action, tuple(float(value) for value in match.groups()))

    raise ValueError(f"Unsupported command: {text.strip() or 'empty'}")


def execute_command(command: Command) -> None:
    """Execute a parsed command using Blender's current scene."""
    import bpy

    if command.action == "add":
        operators = {
            "cube": bpy.ops.mesh.primitive_cube_add,
            "sphere": bpy.ops.mesh.primitive_uv_sphere_add,
            "cylinder": bpy.ops.mesh.primitive_cylinder_add,
            "cone": bpy.ops.mesh.primitive_cone_add,
            "torus": bpy.ops.mesh.primitive_torus_add,
        }
        operators[command.values[0]](location=bpy.context.scene.cursor.location)
    elif command.action == "delete":
        bpy.ops.object.delete(use_global=False)
    elif command.action == "delete_all":
        for obj in bpy.context.scene.objects:
            obj.select_set(True)
        bpy.ops.object.delete(use_global=False)
    elif command.action == "save":
        bpy.ops.wm.save_as_mainfile()
    elif command.action in {"move", "rotate", "scale"}:
        if bpy.context.object is None:
            raise RuntimeError("Select an object first")
        attribute = {
            "move": "location",
            "rotate": "rotation_euler",
            "scale": "scale",
        }[command.action]
        setattr(bpy.context.object, attribute, command.values)


_pending_commands: queue.Queue[str] = queue.Queue()


def _run_pending_command() -> float | None:
    """Run speech results on Blender's main thread."""
    while True:
        try:
            text = _pending_commands.get_nowait()
        except queue.Empty:
            return 0.1
        try:
            execute_command(parse_command(text))
        except (ValueError, RuntimeError) as error:
            print(f"Voice command: {error}")


try:
    import bpy
except ImportError:
    bpy = None


if bpy is not None:

  class VOICECOMMANDS_OT_execute(bpy.types.Operator):
      bl_idname = "voice_commands.execute"
      bl_label = "Execute Voice Command"
      bl_options = {"REGISTER", "UNDO"}

      command: bpy.props.StringProperty(name="Command")

      def execute(self, context):
          try:
              execute_command(parse_command(self.command))
          except (ValueError, RuntimeError) as error:
              self.report({"ERROR"}, str(error))
              return {"CANCELLED"}
          self.report({"INFO"}, f"Executed: {self.command}")
          return {"FINISHED"}


  class VOICECOMMANDS_OT_listen(bpy.types.Operator):
      bl_idname = "voice_commands.listen"
      bl_label = "Listen"
      bl_options = {"REGISTER"}

      def execute(self, context):
          try:
              import speech_recognition as sr
          except ImportError:
              self.report(
                  {"ERROR"},
                  "Install SpeechRecognition and PyAudio in Blender's Python",
              )
              return {"CANCELLED"}

          def listen():
              recognizer = sr.Recognizer()
              try:
                  with sr.Microphone() as microphone:
                      recognizer.adjust_for_ambient_noise(microphone, duration=0.3)
                      audio = recognizer.listen(microphone, timeout=5, phrase_time_limit=8)
                  _pending_commands.put(recognizer.recognize_google(audio))
              except Exception as error:
                  print(f"Voice command microphone error: {error}")

          threading.Thread(target=listen, daemon=True).start()
          self.report({"INFO"}, "Listening...")
          return {"FINISHED"}


  class VOICECOMMANDS_PT_panel(bpy.types.Panel):
      bl_label = "Voice Commands"
      bl_idname = "VOICECOMMANDS_PT_panel"
      bl_space_type = "VIEW_3D"
      bl_region_type = "UI"
      bl_category = "Voice"

      def draw(self, context):
          layout = self.layout
          row = layout.row()
          row.operator("voice_commands.listen", icon="REC")
          command = row.operator("voice_commands.execute", text="Run")
          command.command = "create cube"
          layout.label(text="Try: create cube, move 1 0 0")


  _CLASSES = (VOICECOMMANDS_OT_execute, VOICECOMMANDS_OT_listen, VOICECOMMANDS_PT_panel)
else:
  _CLASSES = ()


def register():
    for cls in _CLASSES:
        bpy.utils.register_class(cls)
    bpy.app.timers.register(_run_pending_command, first_interval=0.1)


def unregister():
    if bpy.app.timers.is_registered(_run_pending_command):
        bpy.app.timers.unregister(_run_pending_command)
    for cls in reversed(_CLASSES):
        bpy.utils.unregister_class(cls)

if bpy is not None:
    register()
