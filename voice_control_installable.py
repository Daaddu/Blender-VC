# Keep add-on metadata off the first line for Blender's Preferences scanner.
bl_info = {
    "name": "Blender VC",
    "author": "OpenAI",
    "version": (1, 2, 0),
    "blender": (4, 0, 0),
    "location": "View3D > Sidebar > Voice",
    "description": "Switch Blender tools and control common interface features by voice",
    "category": "3D View",
}

import json
import os
import queue
import re
import threading
import time

import bpy
import bmesh
from bpy.props import EnumProperty, IntProperty, StringProperty

_COMMAND_QUEUE = queue.Queue()
_stop_event = None
_listening = False
_timer_registered = False
_last_heard = ""
_last_status = "Voice input is stopped"
_pending_object_action = None
_delete_request_id = 0
_object_names = ()
_grammar_queue = None
_rename_context = None
_rename_request_id = 0
_symmetrize_context = None
_symmetrize_request_id = 0

_TOOLS = {
    "select": "builtin.select_box",
    "box select": "builtin.select_box",
    "move": "builtin.move",
    "grab": "builtin.move",
    "rotate": "builtin.rotate",
    "scale": "builtin.scale",
    "transform": "builtin.transform",
    "annotate": "builtin.annotate",
    "cursor": "builtin.cursor",
    "measure": "builtin.measure",
}

_EDIT_MESH_TOOLS = {
    "extrude": "builtin.extrude_region",
    "inset": "builtin.inset_faces",
    "bevel": "builtin.bevel",
    "knife": "builtin.knife",
    "loop cut": "builtin.loop_cut",
}

_ORIENTATIONS = {}
for _orientation in ("global", "local", "normal"):
    for _phrase in (_orientation, _orientation + " orientation",
                    "switch to " + _orientation, "switch to " + _orientation + " orientation"):
        _ORIENTATIONS[_phrase] = _orientation.upper()

_SCULPT_BRUSHES = {
    "draw": "builtin_brush.Draw",
    "sharp": "builtin_brush.Draw Sharp",
    "clay": "builtin_brush.Clay",
    "clay strips": "builtin_brush.Clay Strips",
    "clay thumb": "builtin_brush.Clay Thumb",
    "layer": "builtin_brush.Layer",
    "inflate": "builtin_brush.Inflate",
    "blob": "builtin_brush.Blob",
    "crease": "builtin_brush.Crease",
    "smooth": "builtin_brush.Smooth",
    "flatten": "builtin_brush.Flatten",
    "fill": "builtin_brush.Fill",
    "scrape": "builtin_brush.Scrape",
    "pinch": "builtin_brush.Pinch",
    "grab brush": "builtin_brush.Grab",
    "snake hook": "builtin_brush.Snake Hook",
    "thumb": "builtin_brush.Thumb",
    "pose brush": "builtin_brush.Pose",
    "nudge": "builtin_brush.Nudge",
    "rotate brush": "builtin_brush.Rotate",
    "simplify": "builtin_brush.Simplify",
    "mask": "builtin_brush.Mask",
}

_COMMANDS = {
    "toggle sidebar": "sidebar",
    "toggle n panel": "sidebar",
    "toggle toolbar": "toolbar",
    "toggle overlays": "overlays",
    "hide overlays": "overlays off",
    "show overlays": "overlays on",
    "toggle gizmos": "gizmos",
    "hide gizmos": "gizmos off",
    "show gizmos": "gizmos on",
    "see through": "see through",
    "toggle see through": "see through",
    "frame selected": "frame selected",
    "focus selected": "frame selected",
    "deselect": "deselect",
    "deselect all": "deselect",
    "de select": "deselect",
    "de select all": "deselect",
    "clear selection": "deselect",
    "save file": "save file",
    "save as": "save file",
    "object mode": "object mode",
    "switch to object mode": "object mode",
    "edit mode": "edit mode",
    "switch to edit mode": "edit mode",
    "sculpt mode": "sculpt mode",
    "switch to sculpt mode": "sculpt mode",
    "texture paint": "texture paint",
    "texture paint mode": "texture paint",
    "pose mode": "pose mode",
    "switch to pose mode": "pose mode",
    "switch to texture paint": "texture paint",
    "switch to texture paint mode": "texture paint",
    "weight paint": "weight paint",
    "weight paint mode": "weight paint",
    "switch to weight paint": "weight paint",
    "switch to weight paint mode": "weight paint",
    "dyntopo on": "dyntopo on",
    "enable dyntopo": "dyntopo on",
    "dynamic topology on": "dyntopo on",
    "enable dynamic topology": "dyntopo on",
    "dyntopo off": "dyntopo off",
    "disable dyntopo": "dyntopo off",
    "dynamic topology off": "dyntopo off",
    "disable dynamic topology": "dyntopo off",
    "dyntopo detail 6": "dyntopo detail 6",
    "detail size 6": "dyntopo detail 6",
    "set dyntopo detail size 6": "dyntopo detail 6",
    "dyntopo detail six": "dyntopo detail 6",
    "detail size six": "dyntopo detail 6",
    "set dyntopo detail size six": "dyntopo detail 6",
    "dynamic topology detail size six": "dyntopo detail 6",
    "set dynamic topology detail size six": "dyntopo detail 6",
    "dynamic detail size six": "dyntopo detail 6",
    "dyntopo detail 3": "dyntopo detail 3",
    "dyntopo detail size 3": "dyntopo detail 3",
    "set dyntopo detail size 3": "dyntopo detail 3",
    "dyntopo detail three": "dyntopo detail 3",
    "dyntopo detail size three": "dyntopo detail 3",
    "set dyntopo detail size three": "dyntopo detail 3",
    "detail size three": "dyntopo detail 3",
    "set dynamic topology detail size three": "dyntopo detail 3",
    "dynamic detail size three": "dyntopo detail 3",
    "dyntopo detail 1": "dyntopo detail 1",
    "detail size 1": "dyntopo detail 1",
    "set dyntopo detail size 1": "dyntopo detail 1",
    "dyntopo detail one": "dyntopo detail 1",
    "dyntopo detail size one": "dyntopo detail 1",
    "set dyntopo detail size one": "dyntopo detail 1",
    "detail size one": "dyntopo detail 1",
    "set dynamic topology detail size one": "dyntopo detail 1",
    "dynamic detail size one": "dyntopo detail 1",
    "invert brush": "invert brush",
    "toggle brush": "invert brush",
    "brush invert": "invert brush",
    "invert mask": "invert mask",
    "mask invert": "invert mask",
    "invert sculpt mask": "invert mask",
    "clear mask": "clear mask",
    "remove mask": "clear mask",
    "remesh": "voxel remesh",
    "re mesh": "voxel remesh",
    "voxel remesh": "voxel remesh",
    "sculpt re mesh": "voxel remesh",
    "x symmetry": "x symmetry",
    "ex symmetry": "x symmetry",
    "x symmetry on": "x symmetry on",
    "ex symmetry on": "x symmetry on",
    "x symmetry off": "x symmetry off",
    "ex symmetry off": "x symmetry off",
    "y symmetry": "y symmetry",
    "why symmetry": "y symmetry",
    "y symmetry on": "y symmetry on",
    "why symmetry on": "y symmetry on",
    "y symmetry off": "y symmetry off",
    "why symmetry off": "y symmetry off",
    "z symmetry": "z symmetry",
    "zee symmetry": "z symmetry",
    "zed symmetry": "z symmetry",
    "z symmetry on": "z symmetry on",
    "zee symmetry on": "z symmetry on",
    "zed symmetry on": "z symmetry on",
    "z symmetry off": "z symmetry off",
    "zee symmetry off": "z symmetry off",
    "zed symmetry off": "z symmetry off",
    "undo": "undo",
    "redo": "redo",
}

_EDIT_MESH_ACTIONS = {
    "separate by selection": ("separate", {"type": "SELECTED"}),
    "symmetrize": ("symmetrize", {}),
    "make symmetric": ("symmetrize", {}),
    "make symmetrical": ("symmetrize", {}),
}
for _name, _selection_type in (("vertex", "VERT"), ("vertices", "VERT"),
                               ("vertice", "VERT"), ("edge", "EDGE"), ("face", "FACE")):
    for _prefix in ("", "switch to "):
        _EDIT_MESH_ACTIONS[_prefix + _name + " mode"] = (
            "select_mode", {"type": _selection_type, "use_extend": False, "use_expand": False})
for _name in ("vertex", "edge", "face"):
    _EDIT_MESH_ACTIONS[_name] = _EDIT_MESH_ACTIONS[_name + " mode"]
_EDIT_MESH_ACTIONS["vertex select"] = _EDIT_MESH_ACTIONS["vertex mode"]
_EDIT_MESH_ACTIONS["face select"] = _EDIT_MESH_ACTIONS["face mode"]

_OBJECT_ACTIONS = {
    "duplicate object": ("object.duplicate", {"linked": False}),
    "duplicate linked": ("object.duplicate", {"linked": True}),
    "join objects": ("object.join", {}),
    "copy objects": ("view3d.copybuffer", {}),
    "paste objects": ("view3d.pastebuffer", {}),
    "delete": ("object.delete", {"use_global": False}),
    "delete objects": ("object.delete", {"use_global": False}),
    "delete object": ("object.delete", {"use_global": False}),
    "delete globally": ("object.delete", {"use_global": True}),
    "shade smooth": ("object.shade_smooth", {}),
    "shade flat": ("object.shade_flat", {}),
    "origin to geometry": ("object.origin_set", {"type": "ORIGIN_GEOMETRY"}),
    "geometry to origin": ("object.origin_set", {"type": "GEOMETRY_ORIGIN"}),
    "origin to cursor": ("object.origin_set", {"type": "ORIGIN_CURSOR"}),
    "origin to center of mass": ("object.origin_set", {"type": "ORIGIN_CENTER_OF_MASS"}),
    "origin to center of volume": ("object.origin_set", {"type": "ORIGIN_CENTER_OF_VOLUME"}),
    "clear location": ("object.location_clear", {"clear_delta": False}),
    "clear rotation": ("object.rotation_clear", {"clear_delta": False}),
    "clear scale": ("object.scale_clear", {"clear_delta": False}),
    "clear origin": ("object.origin_clear", {}),
    "apply location": ("object.transform_apply", {"location": True, "rotation": False, "scale": False}),
    "apply rotation": ("object.transform_apply", {"location": False, "rotation": True, "scale": False}),
    "apply scale": ("object.transform_apply", {"location": False, "rotation": False, "scale": True}),
    "apply all transforms": ("object.transform_apply", {"location": True, "rotation": True, "scale": True}),
    "apply rotation and scale": ("object.transform_apply", {"location": False, "rotation": True, "scale": True}),
    "location to deltas": ("object.transforms_to_deltas", {"mode": "LOC"}),
    "rotation to deltas": ("object.transforms_to_deltas", {"mode": "ROT"}),
    "scale to deltas": ("object.transforms_to_deltas", {"mode": "SCALE"}),
    "all transforms to deltas": ("object.transforms_to_deltas", {"mode": "ALL"}),
    "animation to deltas": ("object.anim_transforms_to_deltas", {}),
    "apply visual transform": ("object.visual_transform_apply", {}),
    "make instances real": ("object.duplicates_make_real", {}),
    "apply parent inverse": ("object.parent_inverse_apply", {}),
    "selection to grid": ("view3d.snap_selected_to_grid", {}),
    "selection to cursor": ("view3d.snap_selected_to_cursor", {"use_offset": False}),
    "selection to cursor keep offset": ("view3d.snap_selected_to_cursor", {"use_offset": True}),
    "selection to active": ("view3d.snap_selected_to_active", {}),
    "cursor to selected": ("view3d.snap_cursor_to_selected", {}),
    "cursor to origin": ("view3d.snap_cursor_to_center", {}),
    "cursor to grid": ("view3d.snap_cursor_to_grid", {}),
    "cursor to active": ("view3d.snap_cursor_to_active", {}),
    "parent objects": ("object.parent_set", {"type": "OBJECT"}),
    "parent with automatic weights": ("object.parent_set", {"type": "ARMATURE_AUTO"}),
    "parent with empty groups": ("object.parent_set", {"type": "ARMATURE_NAME"}),
    "parent to bone": ("object.parent_set", {"type": "BONE"}),
    "parent to curve": ("object.parent_set", {"type": "CURVE"}),
    "parent to lattice": ("object.parent_set", {"type": "LATTICE"}),
    "parent without inverse": ("object.parent_no_inverse_set", {"keep_transform": False}),
    "parent without inverse keep transform": ("object.parent_no_inverse_set", {"keep_transform": True}),
    "clear parent": ("object.parent_clear", {"type": "CLEAR"}),
    "clear parent keep transform": ("object.parent_clear", {"type": "CLEAR_KEEP_TRANSFORM"}),
    "clear parent inverse": ("object.parent_clear", {"type": "CLEAR_INVERSE"}),
    "clear constraints": ("object.constraints_clear", {}),
    "copy constraints": ("object.constraints_copy", {}),
    "track to": ("object.track_set", {"type": "TRACKTO"}),
    "damped track": ("object.track_set", {"type": "DAMPTRACK"}),
    "locked track": ("object.track_set", {"type": "LOCKTRACK"}),
    "clear track": ("object.track_clear", {"type": "CLEAR"}),
    "clear track keep transform": ("object.track_clear", {"type": "CLEAR_KEEP_TRANSFORM"}),
    "convert to mesh": ("object.convert", {"target": "MESH"}),
    "convert to curve": ("object.convert", {"target": "CURVE"}),
    "convert to curves": ("object.convert", {"target": "CURVES"}),
    "hide selected": ("object.hide_view_set", {"unselected": False}),
    "hide not selected": ("object.hide_view_set", {"unselected": True}),
    "show hidden": ("object.hide_view_clear", {}),
    "remove unused materials": ("object.material_slot_remove_unused", {}),
    "clean vertex weights": ("object.vertex_group_clean", {"group_select_mode": "ALL"}),
    "limit vertex groups": ("object.vertex_group_limit_total", {"group_select_mode": "ALL"}),
    "mark asset": ("asset.mark", {}),
    "clear asset": ("asset.clear", {"set_fake_user": False}),
    "clear asset keep user": ("asset.clear", {"set_fake_user": True}),
    "add active rigid body": ("rigidbody.objects_add", {"type": "ACTIVE"}),
    "add passive rigid body": ("rigidbody.objects_add", {"type": "PASSIVE"}),
    "remove rigid body": ("rigidbody.objects_remove", {}),
    "copy rigid body settings": ("rigidbody.object_settings_copy", {}),
    "quick fur": ("object.quick_fur", {}),
    "quick explode": ("object.quick_explode", {}),
    "quick smoke": ("object.quick_smoke", {}),
    "quick liquid": ("object.quick_liquid", {}),
    "copy uv maps": ("object.join_uvs", {}),
    "make local objects": ("object.make_local", {"type": "SELECT_OBJECT"}),
    "make local object data": ("object.make_local", {"type": "SELECT_OBDATA"}),
    "make local materials": ("object.make_local", {"type": "SELECT_OBDATA_MATERIAL"}),
    "make all local": ("object.make_local", {"type": "ALL"}),
    "make single user object": ("object.make_single_user", {"object": True, "obdata": False, "material": False, "animation": False, "obdata_animation": False}),
    "make single user object and data": ("object.make_single_user", {"object": True, "obdata": True, "material": False, "animation": False, "obdata_animation": False}),
    "make single user materials": ("object.make_single_user", {"object": False, "obdata": False, "material": True, "animation": False, "obdata_animation": False}),
    "make single user animation": ("object.make_single_user", {"object": False, "obdata": False, "material": False, "animation": True, "obdata_animation": False}),
    "make library override": ("object.make_override_library", {}),
    "reset library override": ("object.reset_override_library", {}),
    "clear library override": ("object.clear_override_library", {}),
    "link object data": ("object.make_links_data", {"type": "OBDATA"}),
    "link materials": ("object.make_links_data", {"type": "MATERIAL"}),
    "link animation": ("object.make_links_data", {"type": "ANIMATION"}),
    "link modifiers": ("object.make_links_data", {"type": "MODIFIERS"}),
    "create collection": ("collection.create", {}),
    "remove from collections": ("collection.objects_remove_all", {}),
    "add to active collection": ("collection.objects_add_active", {}),
    "remove from active collection": ("collection.objects_remove_active", {}),
    "delete key frames": ("anim.keyframe_delete_v3d", {}),
    "clear key frames": ("anim.keyframe_clear_v3d", {}),
    "bake rigid bodies to key frames": ("rigidbody.bake_to_keyframes", {}),
    "connect rigid bodies": ("rigidbody.connect", {}),
}
for _orientation in ("global", "local"):
    for _index, _axis in enumerate("xyz"):
        _constraint = tuple(index == _index for index in range(3))
        _OBJECT_ACTIONS["mirror " + _axis + " " + _orientation] = (
            "transform.mirror", {"constraint_axis": _constraint, "orient_type": _orientation.upper()})

_ADD_OBJECTS = {
    "plane": ("mesh.primitive_plane_add", {}),
    "cube": ("mesh.primitive_cube_add", {}),
    "circle": ("mesh.primitive_circle_add", {}),
    "sphere": ("mesh.primitive_uv_sphere_add", {}),
    "uv sphere": ("mesh.primitive_uv_sphere_add", {}),
    "ico sphere": ("mesh.primitive_ico_sphere_add", {}),
    "cylinder": ("mesh.primitive_cylinder_add", {}),
    "cone": ("mesh.primitive_cone_add", {}),
    "torus": ("mesh.primitive_torus_add", {}),
    "grid": ("mesh.primitive_grid_add", {}),
    "monkey": ("mesh.primitive_monkey_add", {}),
    "suzanne": ("mesh.primitive_monkey_add", {}),
    "bezier curve": ("curve.primitive_bezier_curve_add", {}),
    "bezier circle": ("curve.primitive_bezier_circle_add", {}),
    "bee zee curve": ("curve.primitive_bezier_curve_add", {}),
    "bee zee circle": ("curve.primitive_bezier_circle_add", {}),
    "nurbs curve": ("curve.primitive_nurbs_curve_add", {}),
    "nurbs circle": ("curve.primitive_nurbs_circle_add", {}),
    "nerve curve": ("curve.primitive_nurbs_curve_add", {}),
    "nerve circle": ("curve.primitive_nurbs_circle_add", {}),
    "path": ("curve.primitive_nurbs_path_add", {}),
    "nurbs path": ("curve.primitive_nurbs_path_add", {}),
    "surface curve": ("surface.primitive_nurbs_surface_curve_add", {}),
    "surface circle": ("surface.primitive_nurbs_surface_circle_add", {}),
    "surface": ("surface.primitive_nurbs_surface_surface_add", {}),
    "surface cylinder": ("surface.primitive_nurbs_surface_cylinder_add", {}),
    "surface sphere": ("surface.primitive_nurbs_surface_sphere_add", {}),
    "surface torus": ("surface.primitive_nurbs_surface_torus_add", {}),
    "surface donut": ("surface.primitive_nurbs_surface_torus_add", {}),
    "metaball": ("object.metaball_add", {"type": "BALL"}),
    "meta ball": ("object.metaball_add", {"type": "BALL"}),
    "metaball capsule": ("object.metaball_add", {"type": "CAPSULE"}),
    "metaball plane": ("object.metaball_add", {"type": "PLANE"}),
    "metaball ellipsoid": ("object.metaball_add", {"type": "ELLIPSOID"}),
    "metaball cube": ("object.metaball_add", {"type": "CUBE"}),
    "meta ball capsule": ("object.metaball_add", {"type": "CAPSULE"}),
    "meta ball plane": ("object.metaball_add", {"type": "PLANE"}),
    "meta ball ellipsoid": ("object.metaball_add", {"type": "ELLIPSOID"}),
    "meta ball cube": ("object.metaball_add", {"type": "CUBE"}),
    "text": ("object.text_add", {}),
    "volume": ("object.volume_add", {}),
    "empty volume": ("object.volume_add", {}),
    "grease pencil": ("object.gpencil_add", {"type": "EMPTY"}),
    "grease pencil stroke": ("object.gpencil_add", {"type": "STROKE"}),
    "grease pencil monkey": ("object.gpencil_add", {"type": "MONKEY"}),
    "rig": ("object.armature_add", {}),
    "lattice": ("object.add", {"type": "LATTICE"}),
    "empty": ("object.empty_add", {"type": "PLAIN_AXES"}),
    "empty axes": ("object.empty_add", {"type": "PLAIN_AXES"}),
    "empty arrows": ("object.empty_add", {"type": "ARROWS"}),
    "empty arrow": ("object.empty_add", {"type": "SINGLE_ARROW"}),
    "empty circle": ("object.empty_add", {"type": "CIRCLE"}),
    "empty cube": ("object.empty_add", {"type": "CUBE"}),
    "empty sphere": ("object.empty_add", {"type": "SPHERE"}),
    "empty cone": ("object.empty_add", {"type": "CONE"}),
    "point light": ("object.light_add", {"type": "POINT"}),
    "sun light": ("object.light_add", {"type": "SUN"}),
    "spot light": ("object.light_add", {"type": "SPOT"}),
    "area light": ("object.light_add", {"type": "AREA"}),
    "reflection cubemap": ("object.lightprobe_add", {"type": "CUBEMAP"}),
    "reflection cube map": ("object.lightprobe_add", {"type": "CUBEMAP"}),
    "reflection plane": ("object.lightprobe_add", {"type": "PLANAR"}),
    "irradiance volume": ("object.lightprobe_add", {"type": "GRID"}),
    "radiation volume": ("object.lightprobe_add", {"type": "GRID"}),
    "camera": ("object.camera_add", {}),
    "speaker": ("object.speaker_add", {}),
    "force field": ("object.effector_add", {"type": "FORCE"}),
    "wind field": ("object.effector_add", {"type": "WIND"}),
    "vortex field": ("object.effector_add", {"type": "VORTEX"}),
    "magnetic field": ("object.effector_add", {"type": "MAGNET"}),
    "harmonic field": ("object.effector_add", {"type": "HARMONIC"}),
    "charge field": ("object.effector_add", {"type": "CHARGE"}),
    "lennard jones field": ("object.effector_add", {"type": "LENNARDJ"}),
    "texture field": ("object.effector_add", {"type": "TEXTURE"}),
    "curve guide": ("object.effector_add", {"type": "GUIDE"}),
    "boid field": ("object.effector_add", {"type": "BOID"}),
    "bird field": ("object.effector_add", {"type": "BOID"}),
    "turbulence field": ("object.effector_add", {"type": "TURBULENCE"}),
    "drag field": ("object.effector_add", {"type": "DRAG"}),
    "fluid flow field": ("object.effector_add", {"type": "FLUID"}),
}


def _status(message):
    global _last_status
    _last_status = message
    print("Blender VC: " + message)


def _view3d_areas():
    for window in bpy.context.window_manager.windows:
        screen = window.screen
        if screen:
            for area in screen.areas:
                if area.type == "VIEW_3D":
                    yield window, area


def _call_operator(operator, override, **kwargs):
    if override is None:
        return operator(**kwargs)
    return operator(override, **kwargs)


def _run_in_view3d(callback):
    for window, area in _view3d_areas():
        region = next((region for region in area.regions if region.type == "WINDOW"), None)
        if region is None:
            continue
        try:
            if hasattr(bpy.context, "temp_override"):
                with bpy.context.temp_override(window=window, area=area, region=region):
                    callback(area, None)
            else:
                override = {"window": window, "screen": window.screen,
                            "area": area, "region": region}
                callback(area, override)
            return True
        except (RuntimeError, TypeError) as error:
            _status("Could not apply command: " + str(error))
            return False
    _status("No 3D View is currently available")
    return False


def _object_action_context():
    active = bpy.context.view_layer.objects.active
    return (bpy.context.scene.as_pointer(), bpy.context.view_layer.as_pointer(),
            active.as_pointer() if active else None,
            tuple(sorted(obj.as_pointer() for obj in bpy.context.selected_objects)))


def _object_action(phrase):
    global _pending_object_action
    if phrase == "cancel action":
        _pending_object_action = None
        _status("Object action cancelled")
        return
    if phrase != "confirm action":
        _pending_object_action = None

    def run_action(_area, override):
        global _pending_object_action, _delete_request_id
        if bpy.context.mode != 'OBJECT':
            _pending_object_action = None
            _status("Object menu actions require Object Mode")
            return
        if phrase == "confirm action":
            pending = _pending_object_action
            _pending_object_action = None
            if pending is None or time.monotonic() > pending[2]:
                _status("No object action awaiting confirmation")
                return
            if _object_action_context() != pending[1]:
                _status("Selection or scene changed; object action cancelled")
                return
            action = pending[0]
        elif _OBJECT_ACTIONS[phrase][0] == "object.delete":
            if not bpy.context.selected_objects or not bpy.ops.object.delete.poll():
                _status("Select an object in Object Mode before deleting")
                return
            if bpy.app.background:
                _status("Delete confirmation requires a Blender window")
                return
            _delete_request_id += 1
            request_id = _delete_request_id
            _pending_object_action = (phrase, _object_action_context(), time.monotonic() + 30, request_id)
            try:
                result = bpy.ops.voice_control.confirm_delete('INVOKE_DEFAULT', request_id=request_id)
            except (RuntimeError, TypeError) as error:
                _pending_object_action = None
                _status("Could not open the delete confirmation: " + str(error))
                return
            if 'RUNNING_MODAL' not in result:
                _pending_object_action = None
                _status("Could not open the delete confirmation: " + str(result))
                return
            _status("Confirm deletion in the popup or say confirm action within 30 seconds")
            return
        else:
            action = phrase
        operator_name, options = _OBJECT_ACTIONS[action]
        category, name = operator_name.split(".")
        operator = getattr(getattr(bpy.ops, category), name)
        try:
            operator.get_rna_type()
        except (AttributeError, RuntimeError):
            _status(action + " is not available in this Blender version")
            return
        if not operator.poll():
            _status("Cannot " + action + " in the current Blender context")
            return
        result = _call_operator(operator, override, **options)
        if 'FINISHED' in result:
            _status("Completed: " + action)
        else:
            _status("Blender could not complete " + action + ": " + str(result))
    _run_in_view3d(run_action)


def _mesh_selection_context():
    objects = []
    for obj in bpy.context.objects_in_mode_unique_data:
        mesh = bmesh.from_edit_mesh(obj.data)
        selection = tuple((len(elements), tuple(index for index, element in enumerate(elements) if element.select))
                          for elements in (mesh.verts, mesh.edges, mesh.faces))
        objects.append((obj.as_pointer(), obj.data.as_pointer(), selection))
    return (_object_action_context(), tuple(sorted(objects)))


def _edit_mesh_action(phrase):
    def run_action(_area, override):
        global _symmetrize_context, _symmetrize_request_id
        obj = bpy.context.active_object
        if bpy.context.mode != 'EDIT_MESH' or obj is None or obj.type != 'MESH':
            _status("Mesh actions require an active mesh in Edit Mode")
            return
        operator_name, options = _EDIT_MESH_ACTIONS[phrase]
        operator = getattr(bpy.ops.mesh, operator_name)
        try:
            operator.get_rna_type()
        except (AttributeError, RuntimeError):
            _status(phrase + " is not available in this Blender version")
            return
        if not operator.poll():
            _status("Cannot " + phrase + " in the current Blender context")
            return
        if operator_name == "symmetrize":
            if bpy.app.background:
                _status("Symmetrize direction dialog requires a Blender window")
                return
            _symmetrize_request_id += 1
            _symmetrize_context = _mesh_selection_context()
            try:
                result = bpy.ops.voice_control.symmetrize_dialog('INVOKE_DEFAULT', request_id=_symmetrize_request_id)
            except (RuntimeError, TypeError) as error:
                _symmetrize_context = None
                _status("Could not open Symmetrize dialog: " + str(error))
                return
            if 'RUNNING_MODAL' not in result:
                _symmetrize_context = None
                _status("Could not open Symmetrize dialog: " + str(result))
                return
            _status("Choose a Symmetrize direction and confirm")
            return
        if operator_name == "select_mode":
            index = {"VERT": 0, "EDGE": 1, "FACE": 2}[options["type"]]
            current = tuple(bpy.context.tool_settings.mesh_select_mode)
            if current == tuple(i == index for i in range(3)):
                _status("Already active: " + phrase)
                return
        result = _call_operator(operator, override, **options)
        if 'FINISHED' in result:
            _status("Completed: " + phrase)
        else:
            _status("Blender could not complete " + phrase + ": " + str(result))
    _run_in_view3d(run_action)


def _spoken_object_name(name):
    if not name.isascii():
        return ""
    digits = ("zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine")
    name = re.sub(r"[0-9]", lambda match: " " + digits[int(match.group())] + " ", name.lower())
    return " ".join(re.findall(r"[a-z]+", name))


def _select_object(obj, add):
    if obj.hide_select or not obj.visible_get():
        _status("Object cannot be selected because it is hidden or unselectable: " + obj.name)
        return
    try:
        obj.select_set(True)
    except RuntimeError as error:
        _status("Cannot select " + obj.name + ": " + str(error))
        return
    if not obj.select_get():
        _status("Cannot select " + obj.name + " in the current view layer")
        return
    if not add:
        for selected in bpy.context.selected_objects:
            if selected != obj:
                selected.select_set(False)
    bpy.context.view_layer.objects.active = obj
    _status(("Added to selection: " if add else "Selected object: ") + obj.name)


def _select_named_object(name, add):
    name = _spoken_object_name(name)
    def select_object(_area, _override):
        if bpy.context.mode != 'OBJECT':
            _status("Object selection requires Object Mode")
            return
        objects = [obj for obj in bpy.context.view_layer.objects
                   if _spoken_object_name(obj.name) == name]
        if not objects:
            _status("No object named " + name + " in the current view layer")
            return
        if len(objects) != 1:
            _status("Object name is ambiguous: " + name + "; rename the objects")
            return
        _select_object(objects[0], add)
    _run_in_view3d(select_object)


def _select_next_object(add):
    def select_next(_area, _override):
        if bpy.context.mode != 'OBJECT':
            _status("Object selection requires Object Mode")
            return
        active = bpy.context.view_layer.objects.active
        if active is None or not active.select_get():
            _status("Select an active object before saying next")
            return
        match = re.fullmatch(r"(.*)\.([0-9]{3,})", active.name)
        base = match.group(1) if match else active.name
        objects = []
        for obj in bpy.context.view_layer.objects:
            suffix = re.fullmatch(re.escape(base) + r"\.([0-9]{3,})", obj.name)
            if obj.name == base:
                objects.append((-1, obj.name, obj))
            elif suffix:
                objects.append((int(suffix.group(1)), obj.name, obj))
        objects.sort(key=lambda item: (item[0], item[1]))
        index = next(i for i, item in enumerate(objects) if item[2] == active)
        for offset in range(1, len(objects)):
            candidate = objects[(index + offset) % len(objects)][2]
            if not candidate.hide_select and candidate.visible_get():
                _select_object(candidate, add)
                return
        _status("No other selectable numbered objects for " + base)
    _run_in_view3d(select_next)


def _cancel_rename(message):
    global _rename_context
    _rename_context = None
    _status(message)


def _begin_rename():
    def begin(_area, _override):
        global _rename_context, _rename_request_id
        obj = bpy.context.view_layer.objects.active
        if bpy.context.mode != 'OBJECT' or obj is None or not obj.select_get():
            _status("Select an active object in Object Mode before renaming")
            return
        if obj.library is not None or obj.override_library is not None:
            _status("Cannot rename linked or library override objects")
            return
        if bpy.app.background:
            _status("Voice rename requires a Blender window")
            return
        _rename_context = _object_action_context()
        _rename_request_id += 1
        bpy.context.window_manager.voice_control_rename_text = obj.name
        try:
            result = bpy.ops.voice_control.rename_dialog('INVOKE_DEFAULT', request_id=_rename_request_id)
        except (RuntimeError, TypeError) as error:
            _cancel_rename("Could not open rename dialog: " + str(error))
            return
        if 'RUNNING_MODAL' not in result:
            _cancel_rename("Could not open rename dialog: " + str(result))
            return
        _status("Type the new name and click OK")
    _run_in_view3d(begin)


def _execute_command(phrase):
    global _pending_object_action
    phrase = " ".join(phrase.lower().strip().split())
    if _rename_context is not None:
        _status("Finish or cancel the rename dialog first")
        return
    if _symmetrize_context is not None:
        _status("Finish or cancel the Symmetrize dialog first")
        return
    if phrase in ("rename to", "rename object"):
        _pending_object_action = None
        _begin_rename()
        return
    if phrase in _OBJECT_ACTIONS or phrase in ("confirm action", "cancel action"):
        _object_action(phrase)
        return
    _pending_object_action = None
    if phrase == "select" and bpy.context.mode == 'EDIT_MESH':
        def toggle_component_selection(_area, override):
            tool = bpy.context.workspace.tools.from_space_view3d_mode('EDIT_MESH', create=False)
            enabled = tool is not None and tool.idname == VOICECONTROL_WST_additive_select.bl_idname
            name = "builtin.select_box" if enabled else VOICECONTROL_WST_additive_select.bl_idname
            operator = bpy.ops.wm.tool_set_by_id
            if not operator.poll():
                _status("Cannot toggle component selection in the current Blender context")
                return
            result = _call_operator(operator, override, name=name)
            if 'FINISHED' in result:
                _status("Multiple component selection " + ("off" if enabled else "on"))
            else:
                _status("Blender could not toggle component selection: " + str(result))
        _run_in_view3d(toggle_component_selection)
        return
    if phrase in _EDIT_MESH_ACTIONS:
        _edit_mesh_action(phrase)
        return
    if phrase in _ORIENTATIONS:
        def set_orientation(_area, _override):
            orientation = _ORIENTATIONS[phrase]
            bpy.context.scene.transform_orientation_slots[0].type = orientation
            _status("Transform orientation: " + orientation.title())
        _run_in_view3d(set_orientation)
        return
    if phrase in ("next", "select next"):
        _select_next_object(phrase == "select next")
        return
    if phrase.startswith("add to selection "):
        _select_named_object(phrase[len("add to selection "):], True)
        return
    if phrase.startswith("select ") and phrase != "select tool":
        _select_named_object(phrase[len("select "):], True)
        return
    if phrase not in _recognition_phrases() and any(
            _spoken_object_name(obj.name) == _spoken_object_name(phrase)
            and _spoken_object_name(obj.name)
            for obj in bpy.context.view_layer.objects):
        _select_named_object(phrase, False)
        return
    if phrase.startswith("add "):
        name = phrase[4:]
        if name.startswith("a "):
            name = name[2:]
        elif name.startswith("an "):
            name = name[3:]
        specification = _ADD_OBJECTS.get(name)
        if specification is None:
            _status("I didn't recognize: " + phrase)
            return

        def add_object(_area, override):
            operator_name, options = specification
            category, operator = operator_name.split(".")
            add_operator = getattr(getattr(bpy.ops, category), operator)
            if not add_operator.poll():
                _status("Cannot add " + name + " in the current Blender context")
                return
            result = _call_operator(add_operator, override, **options)
            if 'FINISHED' in result:
                _status("Added " + name)
            else:
                _status("Blender could not add " + name + ": " + str(result))
        _run_in_view3d(add_object)
        return
    if phrase.startswith("switch to "):
        phrase = phrase[10:]
    elif phrase.startswith("use "):
        phrase = phrase[4:]
    if phrase.endswith(" tool"):
        phrase = phrase[:-5]
    elif phrase.endswith(" brush") and phrase[:-6] in _SCULPT_BRUSHES:
        phrase = phrase[:-6]

    mesh_tool = _EDIT_MESH_TOOLS.get(phrase)
    if mesh_tool:
        def set_mesh_tool(_area, override):
            obj = bpy.context.active_object
            if bpy.context.mode != 'EDIT_MESH' or obj is None or obj.type != 'MESH':
                _status("Mesh tools require an active mesh in Edit Mode")
                return
            operator = bpy.ops.wm.tool_set_by_id
            if not operator.poll():
                _status("Cannot select the " + phrase + " tool in the current Blender context")
                return
            result = _call_operator(operator, override, name=mesh_tool)
            if 'FINISHED' in result:
                _status("Selected " + phrase + " tool; use it in the 3D View")
            else:
                _status("Blender could not select the " + phrase + " tool: " + str(result))
        _run_in_view3d(set_mesh_tool)
        return

    brush = _SCULPT_BRUSHES.get(phrase)
    if brush:
        def set_brush(_area, override):
            _call_operator(bpy.ops.wm.tool_set_by_id, override, name=brush)
        if _run_in_view3d(set_brush):
            _status("Selected sculpt brush: " + phrase)
        return

    tool = _TOOLS.get(phrase)
    if tool:
        def set_tool(_area, override):
            _call_operator(bpy.ops.wm.tool_set_by_id, override, name=tool)
        if _run_in_view3d(set_tool):
            _status("Switched to " + phrase)
        return

    command = _COMMANDS.get(phrase)
    if command == "save file":
        def save_file(_area, override):
            saved = bpy.data.is_saved
            if not saved and bpy.app.background:
                _status("Save As requires an interactive Blender window")
                return
            operator = bpy.ops.wm.save_mainfile if saved else bpy.ops.wm.save_as_mainfile
            if not operator.poll():
                _status("Cannot save the file in the current Blender context")
                return
            if saved:
                result = _call_operator(operator, override)
            elif override is None:
                result = operator('INVOKE_DEFAULT')
            else:
                result = operator(override, 'INVOKE_DEFAULT')
            if saved and 'FINISHED' in result:
                _status("Saved file: " + bpy.data.filepath)
            elif not saved and 'RUNNING_MODAL' in result:
                _status("Choose a location and filename in the Save As dialog")
            else:
                _status("Blender could not save the file: " + str(result))
        _run_in_view3d(save_file)
    elif command == "sidebar":
        def toggle_sidebar(area, _override):
            space = area.spaces.active
            space.show_region_ui = not space.show_region_ui
        _run_in_view3d(toggle_sidebar)
    elif command == "toolbar":
        def toggle_toolbar(area, _override):
            space = area.spaces.active
            space.show_region_toolbar = not space.show_region_toolbar
        _run_in_view3d(toggle_toolbar)
    elif command in ("overlays", "overlays on", "overlays off"):
        def set_overlays(area, _override):
            space = area.spaces.active
            space.overlay.show_overlays = (not space.overlay.show_overlays
                                           if command == "overlays" else command.endswith("on"))
        _run_in_view3d(set_overlays)
    elif command in ("gizmos", "gizmos on", "gizmos off"):
        def set_gizmos(area, _override):
            space = area.spaces.active
            space.show_gizmo = (not space.show_gizmo
                                if command == "gizmos" else command.endswith("on"))
        _run_in_view3d(set_gizmos)
    elif command == "see through":
        def toggle_xray(area, override):
            operator = bpy.ops.view3d.toggle_xray
            if not operator.poll():
                _status("Cannot toggle X-Ray in the current Blender context")
                return
            space = area.spaces.active
            settings = ((space.shading, "show_xray"),
                        (space.shading, "show_xray_wireframe"),
                        (space.overlay, "show_xray_bone"))
            before = [getattr(owner, name) for owner, name in settings]
            result = _call_operator(operator, override)
            if 'FINISHED' not in result:
                _status("Blender could not toggle X-Ray: " + str(result))
                return
            changed = [getattr(owner, name) for (owner, name), previous in zip(settings, before)
                       if getattr(owner, name) != previous]
            if changed:
                _status("X-Ray " + ("on" if changed[0] else "off"))
            else:
                _status("X-Ray did not change in the current Blender context")
        _run_in_view3d(toggle_xray)
    elif command == "frame selected":
        _run_in_view3d(lambda _area, override: _call_operator(
            bpy.ops.view3d.view_selected, override))
    elif command == "deselect":
        def deselect(_area, override):
            mode = bpy.context.mode
            if mode == 'OBJECT':
                operator = bpy.ops.object.select_all
                target = "objects"
            elif mode == 'EDIT_MESH':
                operator = bpy.ops.mesh.select_all
                target = "mesh components"
            else:
                _status("Deselect requires Object Mode or Mesh Edit Mode")
                return
            if not operator.poll():
                _status("Cannot deselect " + target + " in the current Blender context")
                return
            if mode == 'OBJECT' and not bpy.context.selected_objects:
                _status("No objects selected")
                return
            result = _call_operator(operator, override, action='DESELECT')
            if 'FINISHED' in result:
                _status("Deselected " + target)
            else:
                _status("Blender could not deselect " + target + ": " + str(result))
        _run_in_view3d(deselect)
    elif command in ("x symmetry", "y symmetry", "z symmetry",
                     "x symmetry on", "y symmetry on", "z symmetry on",
                     "x symmetry off", "y symmetry off", "z symmetry off"):
        def update_sculpt_symmetry(_area, _override):
            obj = bpy.context.active_object
            if obj is None or obj.type != "MESH" or obj.mode != "SCULPT":
                _status("Symmetry commands require an active mesh in Sculpt Mode")
                return
            axis = command[0]
            property_name = "use_mirror_" + axis
            if command.endswith(" on"):
                enabled = True
            elif command.endswith(" off"):
                enabled = False
            else:
                enabled = not getattr(obj.data, property_name)
            setattr(obj.data, property_name, enabled)
            _status(axis.upper() + " symmetry " + ("on" if enabled else "off"))
            for window in bpy.context.window_manager.windows:
                if window.screen:
                    for area in window.screen.areas:
                        if area.type in {'VIEW_3D', 'PROPERTIES', 'TOPBAR'}:
                            area.tag_redraw()
        _run_in_view3d(update_sculpt_symmetry)
    elif command == "invert brush":
        def invert_brush(_area, _override):
            obj = bpy.context.active_object
            if obj is None or obj.type != "MESH" or obj.mode != "SCULPT":
                _status("Brush inversion requires an active mesh in Sculpt Mode")
                return

            brush = bpy.context.scene.tool_settings.sculpt.brush
            if brush is None:
                _status("There is no active sculpt brush to invert")
                return

            brush.direction = "ADD" if brush.direction == "SUBTRACT" else "SUBTRACT"
            _status("Brush direction: " + brush.direction.title())
        _run_in_view3d(invert_brush)
    elif command in ("invert mask", "clear mask"):
        def update_mask(_area, override):
            obj = bpy.context.active_object
            if obj is None or obj.type != "MESH" or obj.mode != "SCULPT":
                _status("Mask commands require an active mesh in Sculpt Mode")
                return

            operator = bpy.ops.paint.mask_flood_fill
            if not operator.poll():
                _status("Blender cannot update the mask in the current context")
                return
            if command == "clear mask":
                result = _call_operator(operator, override, mode="VALUE", value=0)
            else:
                result = _call_operator(operator, override, mode="INVERT")
            if 'FINISHED' in result:
                _status("Sculpt mask cleared" if command == "clear mask"
                        else "Sculpt mask inverted")
            else:
                action = "clear" if command == "clear mask" else "invert"
                _status("Blender could not " + action + " the sculpt mask: " + str(result))
        _run_in_view3d(update_mask)
    elif command == "voxel remesh":
        def voxel_remesh(_area, override):
            obj = bpy.context.active_object
            if obj is None or obj.type != "MESH" or obj.mode != "SCULPT":
                _status("Voxel remesh requires an active mesh in Sculpt Mode")
                return
            if obj.use_dynamic_topology_sculpting:
                _status("Disable Dyntopo before voxel remeshing")
                return
            if bpy.app.background:
                _status("Voxel remesh requires an interactive Blender window")
                return
            operator = bpy.ops.object.voxel_remesh
            if not operator.poll():
                _status("Cannot voxel remesh in the current Blender context")
                return
            result = _call_operator(operator, override)
            if 'FINISHED' in result:
                _status("Voxel remesh completed")
            else:
                _status("Blender could not voxel remesh: " + str(result))
        _run_in_view3d(voxel_remesh)
    elif command in ("dyntopo on", "dyntopo off", "dyntopo detail 6",
                     "dyntopo detail 3", "dyntopo detail 1"):
        def set_dyntopo(_area, override):
            obj = bpy.context.active_object
            if obj is None or obj.type != "MESH" or obj.mode != "SCULPT":
                _status("Dyntopo commands require an active mesh in Sculpt Mode")
                return

            sculpt = bpy.context.scene.tool_settings.sculpt
            if command.startswith("dyntopo detail "):
                detail_size = float(command.rsplit(" ", 1)[1])
                sculpt.detail_type_method = "RELATIVE"
                sculpt.detail_size = detail_size
                if not obj.use_dynamic_topology_sculpting:
                    _call_operator(bpy.ops.sculpt.dynamic_topology_toggle, override)
                if obj.use_dynamic_topology_sculpting:
                    _status("Dyntopo enabled with relative detail size " + str(int(detail_size)) + " pixels")
                else:
                    _status("Detail size set, but Blender could not enable Dyntopo for this mesh")
            else:
                should_enable = command == "dyntopo on"
                if obj.use_dynamic_topology_sculpting != should_enable:
                    _call_operator(bpy.ops.sculpt.dynamic_topology_toggle, override)
                if obj.use_dynamic_topology_sculpting != should_enable:
                    _status("Blender could not " + ("enable" if should_enable else "disable") + " Dyntopo")
                elif should_enable:
                    _status("Dyntopo enabled")
                else:
                    _status("Dyntopo disabled")
        _run_in_view3d(set_dyntopo)
    elif command in ("object mode", "edit mode", "sculpt mode", 
                     "texture paint", "weight paint", "pose mode"):
        mode = {"object mode": "OBJECT", "edit mode": "EDIT",
                "sculpt mode": "SCULPT", "texture paint": "TEXTURE_PAINT",
                "weight paint": "WEIGHT_PAINT", "pose mode": "POSE"}[command]
        if _run_in_view3d(lambda _area, override: _call_operator(
                bpy.ops.object.mode_set, override, mode=mode)):
            _status("Switched to " + command)
    elif command == "undo":
        _run_in_view3d(lambda _area, override: _call_operator(bpy.ops.ed.undo, override))
    elif command == "redo":
        _run_in_view3d(lambda _area, override: _call_operator(bpy.ops.ed.redo, override))
    else:
        _status("I didn't recognize: " + phrase)


def _drain_commands():
    global _timer_registered, _last_heard, _object_names
    if not _listening and _COMMAND_QUEUE.empty():
        _timer_registered = False
        return None
    if _listening and _grammar_queue is not None:
        names = tuple(sorted(obj.name for obj in bpy.context.view_layer.objects))
        if names != _object_names:
            _object_names = names
            _grammar_queue.put(names)
    while True:
        try:
            kind, message = _COMMAND_QUEUE.get_nowait()
        except queue.Empty:
            break
        if kind == "command":
            _last_heard = message
            _status("Heard: " + message)
            _execute_command(message)
        else:
            _status(message)
    return 0.1


def _schedule_command_timer():
    global _timer_registered
    if not _timer_registered:
        _timer_registered = True
        bpy.app.timers.register(_drain_commands, first_interval=0.1)


def _recognition_phrases(model=None, object_names=()):
    phrases = (set(_TOOLS) | set(_EDIT_MESH_TOOLS) | set(_COMMANDS) | set(_OBJECT_ACTIONS)
               | set(_EDIT_MESH_ACTIONS) | set(_ORIENTATIONS))
    phrases.update(("confirm action", "cancel action", "next", "select next", "rename object", "rename to"))
    for name in _ADD_OBJECTS:
        if model is not None and any(model.vosk_model_find_word(word) < 0 for word in name.split()):
            continue
        phrases.update(("add " + name, "add a " + name, "add an " + name))
    for tool in set(_TOOLS) | set(_EDIT_MESH_TOOLS):
        phrases.update(("switch to " + tool, "use " + tool,
                        tool + " tool", "switch to " + tool + " tool",
                        "use " + tool + " tool"))
    for brush in _SCULPT_BRUSHES:
        phrases.add(brush)
        phrases.update(("switch to " + brush, "use " + brush))
        if not brush.endswith(" brush"):
            phrases.update((brush + " brush", "switch to " + brush + " brush",
                            "use " + brush + " brush"))
    for object_name in object_names:
        name = _spoken_object_name(object_name)
        if not name or (model is not None and any(model.vosk_model_find_word(word) < 0 for word in name.split())):
            continue
        phrases.add("add to selection " + name)
        if name != "tool":
            phrases.add("select " + name)
        if name not in phrases and not name.startswith(("select ", "add ")):
            phrases.add(name)
    return sorted(phrases)


def _vosk_worker(stop_event, model_path, object_names, grammar_queue):
    global _listening
    try:
        import sounddevice
        import vosk

        model = vosk.Model(model_path)
        sample_rate = int(sounddevice.query_devices(kind="input")["default_samplerate"])
        recognizer = vosk.KaldiRecognizer(model, sample_rate,
                                          json.dumps(_recognition_phrases(model, object_names)))
        with sounddevice.RawInputStream(samplerate=sample_rate, blocksize=4000,
                                        dtype="int16", channels=1) as stream:
            _COMMAND_QUEUE.put(("status", "Vosk offline speech recognition is ready"))
            while not stop_event.is_set():
                updated_names = None
                while True:
                    try:
                        updated_names = grammar_queue.get_nowait()
                    except queue.Empty:
                        break
                if updated_names is not None:
                    object_names = updated_names
                    recognizer = vosk.KaldiRecognizer(
                        model, sample_rate, json.dumps(_recognition_phrases(model, object_names)))
                audio, overflowed = stream.read(4000)
                if overflowed:
                    _COMMAND_QUEUE.put(("status", "Microphone audio overflowed; please repeat the command"))
                if recognizer.AcceptWaveform(bytes(audio)):
                    phrase = json.loads(recognizer.Result()).get("text", "")
                    if phrase:
                        _COMMAND_QUEUE.put(("command", phrase))
    except Exception as error:
        if stop_event is _stop_event:
            _listening = False
            _COMMAND_QUEUE.put(("status", "Vosk could not start. Check the model folder and install vosk and sounddevice in Blender's Python: " + str(error)))


def _start_listening():
    global _stop_event, _listening, _object_names, _grammar_queue
    if _listening:
        return True
    configured_path = bpy.context.scene.voice_control_model_path.strip()
    if not configured_path:
        _status("Set Model Folder to the extracted Vosk model folder before listening")
        return False
    model_path = os.path.abspath(os.path.expanduser(configured_path))
    if not os.path.isdir(model_path):
        _status("Set Model Folder to the extracted Vosk model folder before listening")
        return False
    _stop_event = threading.Event()
    _object_names = tuple(sorted(obj.name for obj in bpy.context.view_layer.objects))
    _grammar_queue = queue.Queue()
    _listening = True
    worker = threading.Thread(target=_vosk_worker,
                              args=(_stop_event, model_path, _object_names, _grammar_queue), daemon=True)
    worker.start()
    _schedule_command_timer()
    _status("Starting Vosk offline recognition. Say a supported command after it is ready.")
    return True


def _stop_listening():
    global _listening, _pending_object_action, _rename_context, _symmetrize_context
    _listening = False
    _pending_object_action = None
    _rename_context = None
    _symmetrize_context = None
    if _stop_event is not None:
        _stop_event.set()
    _status("Stopped listening")


def _toggle_listening():
    if _listening:
        _stop_listening()
    else:
        _start_listening()


class VOICECONTROL_OT_symmetrize_dialog(bpy.types.Operator):
    bl_idname = "voice_control.symmetrize_dialog"
    bl_label = "Symmetrize"
    bl_description = "Choose the direction for mesh symmetrize"
    bl_options = {'INTERNAL', 'UNDO'}

    request_id: IntProperty(options={'HIDDEN'})
    direction: EnumProperty(
        name="Direction",
        items=(("NEGATIVE_X", "-X to +X", ""), ("POSITIVE_X", "+X to -X", ""),
               ("NEGATIVE_Y", "-Y to +Y", ""), ("POSITIVE_Y", "+Y to -Y", ""),
               ("NEGATIVE_Z", "-Z to +Z", ""), ("POSITIVE_Z", "+Z to -Z", "")),
        default='NEGATIVE_X')

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)

    def draw(self, context):
        self.layout.prop(self, "direction")

    def execute(self, context):
        global _symmetrize_context
        if _symmetrize_context is None or self.request_id != _symmetrize_request_id:
            _status("Symmetrize request is no longer active")
            return {'CANCELLED'}
        expected = _symmetrize_context
        _symmetrize_context = None
        def apply(_area, override):
            if bpy.context.mode != 'EDIT_MESH' or _mesh_selection_context() != expected:
                _status("Selection or scene changed; symmetrize cancelled")
                return False
            operator = bpy.ops.mesh.symmetrize
            if not operator.poll():
                _status("Cannot symmetrize in the current Blender context")
                return False
            result = _call_operator(operator, override, direction=self.direction)
            if 'FINISHED' not in result:
                _status("Blender could not complete symmetrize: " + str(result))
                return False
            _status("Completed: symmetrize (" + self.direction.replace('_', ' ').title() + ")")
            return True
        result = []
        if not _run_in_view3d(lambda area, override: result.append(apply(area, override))):
            return {'CANCELLED'}
        return {'FINISHED'} if result and result[0] else {'CANCELLED'}

    def cancel(self, context):
        global _symmetrize_context
        if _symmetrize_context is not None and self.request_id == _symmetrize_request_id:
            _symmetrize_context = None
            _status("Symmetrize cancelled")


class VOICECONTROL_OT_rename_dialog(bpy.types.Operator):
    bl_idname = "voice_control.rename_dialog"
    bl_label = "Rename Object"
    bl_description = "Enter a new object name"
    bl_options = {'INTERNAL', 'UNDO'}

    request_id: IntProperty()

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)

    def draw(self, context):
        self.layout.label(text="Type the new name, then click OK")
        self.layout.prop(context.window_manager, "voice_control_rename_text", text="Name")

    def execute(self, context):
        if _rename_context is None or self.request_id != _rename_request_id:
            _status("Rename request is no longer active")
            return {'CANCELLED'}
        name = context.window_manager.voice_control_rename_text.strip()
        if not name:
            _cancel_rename("No name entered; rename cancelled")
            return {'CANCELLED'}
        expected = _rename_context
        def rename_object(_area, _override):
            if bpy.context.mode != 'OBJECT' or _object_action_context() != expected:
                _cancel_rename("Selection or scene changed; rename cancelled")
                return False
            obj = bpy.context.view_layer.objects.active
            try:
                obj.name = name
            except (RuntimeError, TypeError) as error:
                _cancel_rename("Could not rename object: " + str(error))
                return False
            _cancel_rename("Renamed object to: " + obj.name)
            return True
        result = []
        if not _run_in_view3d(lambda area, override: result.append(rename_object(area, override))):
            _cancel_rename("Could not rename object: no usable 3D View")
            return {'CANCELLED'}
        return {'FINISHED'} if result and result[0] else {'CANCELLED'}

    def cancel(self, context):
        if _rename_context is not None and self.request_id == _rename_request_id:
            _cancel_rename("Rename cancelled")


class VOICECONTROL_OT_confirm_delete(bpy.types.Operator):
    bl_idname = "voice_control.confirm_delete"
    bl_label = "Confirm Delete"
    bl_description = "Confirm deletion of the selected objects"
    bl_options = {'INTERNAL'}

    request_id: IntProperty()

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)

    def draw(self, context):
        self.layout.label(text="Delete the selected objects?")
        if _pending_object_action and _pending_object_action[3] == self.request_id:
            if _pending_object_action[0] == "delete globally":
                self.layout.label(text="Delete globally from all scenes", icon='ERROR')
            self.layout.label(text="Confirm within 30 seconds.")

    def execute(self, context):
        if _pending_object_action is None or _pending_object_action[3] != self.request_id:
            _status("Delete request is no longer active")
            return {'CANCELLED'}
        _object_action("confirm action")
        return {'FINISHED'}

    def cancel(self, context):
        global _pending_object_action
        if _pending_object_action and _pending_object_action[3] == self.request_id:
            _pending_object_action = None
            _status("Delete cancelled")


class VOICECONTROL_OT_toggle(bpy.types.Operator):
    bl_idname = "voice_control.toggle"
    bl_label = "Start Blender VC"
    bl_description = "Start or stop speech recognition"

    def execute(self, context):
        _toggle_listening()
        return {'FINISHED'}


class VOICECONTROL_OT_command(bpy.types.Operator):
    bl_idname = "voice_control.command"
    bl_label = "Run Voice Command"
    bl_description = "Run a supported command without a microphone"

    command: StringProperty(name="Command", default="move")

    def execute(self, context):
        global _last_heard
        _last_heard = self.command
        _status("Manual command: " + self.command)
        _execute_command(self.command)
        return {'FINISHED'}


class VOICECONTROL_WST_additive_select(bpy.types.WorkSpaceTool):
    bl_space_type = 'VIEW_3D'
    bl_context_mode = 'EDIT_MESH'
    bl_idname = "voice_control.additive_select"
    bl_label = "Voice Multiple Select"
    bl_description = "Click to toggle components or drag to add to the selection"
    bl_icon = "ops.generic.select_box"
    bl_widget = None
    bl_keymap = (
        ("view3d.select", {"type": 'LEFTMOUSE', "value": 'CLICK'},
         {"properties": [("toggle", True), ("deselect_all", False)]}),
        ("view3d.select_box", {"type": 'LEFTMOUSE', "value": 'CLICK_DRAG'},
         {"properties": [("mode", 'ADD')]}),
    )


class VIEW3D_PT_voice_control(bpy.types.Panel):
    bl_label = "Blender VC"
    bl_idname = "VIEW3D_PT_voice_control"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Blender VC"

    def draw(self, context):
        layout = self.layout
        layout.operator(VOICECONTROL_OT_toggle.bl_idname,
                        text="Stop Listening" if _listening else "Start Listening",
                        icon='PAUSE' if _listening else 'PLAY')
        layout.label(text=_last_status)
        layout.prop(context.scene, "voice_control_model_path", text="Vosk Model Folder")
        layout.label(text="Offline recognition: Vosk")
        layout.label(text="Voice commands: move, rotate, scale, toggle sidebar")
        layout.label(text="Save project: say save file")
        layout.label(text="Orientation: global, local, normal")
        layout.label(text="X-Ray: say toggle see through")
        layout.label(text="Add objects: say add cube, add armature, or add camera")
        layout.label(text="Select: cube; add to selection: select camera")
        layout.label(text="Deselect all: say deselect")
        layout.label(text="Rename: say rename to, then type the name")
        layout.label(text="Delete: confirm in popup or say confirm action")
        layout.label(text="Mesh Edit: vertex, edge, face")
        layout.label(text="Mesh Edit: select toggles multiple selection")
        layout.label(text="Mesh tools: extrude, inset, bevel, knife, loop cut")
        layout.label(text="Mesh Edit: separate by selection, make symmetric")
        layout.label(text="Symmetrize: choose direction in popup and confirm")
        layout.label(text="Sculpt: invert brush, invert mask, or clear mask")
        layout.label(text="Sculpt voxel remesh: say re mesh")
        layout.label(text="Sculpt symmetry: X/Y/Z symmetry on or off")
        layout.label(text="Dynamic topology on/off: controls Dyntopo separately")
        layout.label(text="Sculpt Dyntopo: on/off, detail size 6, 3, or 1")
        layout.label(text="Last heard: " + (_last_heard or "(none yet)"))
        layout.separator()
        layout.label(text="Manual command (keyboard):")
        layout.prop(context.scene, "voice_control_command", text="Command")
        operator = layout.operator(VOICECONTROL_OT_command.bl_idname, text="Run Manual Command")
        operator.command = context.scene.voice_control_command


_CLASSES = (
    VOICECONTROL_OT_symmetrize_dialog,
    VOICECONTROL_OT_rename_dialog,
    VOICECONTROL_OT_confirm_delete,
    VOICECONTROL_OT_toggle,
    VOICECONTROL_OT_command,
    VIEW3D_PT_voice_control,
)


def register():
    for cls in _CLASSES:
        bpy.utils.register_class(cls)
    bpy.utils.register_tool(VOICECONTROL_WST_additive_select, after={"builtin.select_box"})
    bpy.types.WindowManager.voice_control_rename_text = StringProperty(name="Name")
    bpy.types.Scene.voice_control_command = StringProperty(name="Command", default="move")
    bpy.types.Scene.voice_control_model_path = StringProperty(
        name="Vosk Model Folder", subtype="DIR_PATH",
        description="Path to the extracted Vosk language model directory")


def unregister():
    _stop_listening()
    bpy.utils.unregister_tool(VOICECONTROL_WST_additive_select)
    del bpy.types.WindowManager.voice_control_rename_text
    del bpy.types.Scene.voice_control_model_path
    del bpy.types.Scene.voice_control_command
    for cls in reversed(_CLASSES):
        bpy.utils.unregister_class(cls)


if __name__ == "__main__":
    register()