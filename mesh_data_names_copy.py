bl_info = {
    "name": "Collection HP LP Tools",
    "author": "ChatGPT",
    "version": (2, 0, 0),
    "blender": (5, 1, 0),
    "location": "View3D > Sidebar",
    "description": "HP LP workflow tools with GLB export",
    "category": "Object",
}

import os
import traceback

import bpy
from bpy.props import EnumProperty
from bpy_extras.io_utils import ExportHelper

# =========================================================
# UTILS
# =========================================================


def log_info(message):
    print(f"[HP-LP][INFO] {message}")


def log_warning(message):
    print(f"[HP-LP][WARN] {message}")


def log_error(message):
    print(f"[HP-LP][ERROR] {message}")


def log_exception(context_message, exc):
    log_error(f"{context_message}: {exc}")
    traceback.print_exc()


def safe_report(operator, level, message):
    try:
        operator.report({level}, message)
    except Exception as exc:
        log_exception("Failed to report operator message", exc)


def get_active_root_collection(context):

    active_layer_collection = context.view_layer.active_layer_collection

    if not active_layer_collection:
        return None

    return active_layer_collection.collection


def get_polycount(obj):
    return len(obj.data.polygons)


def duplicate_object(obj, collection):

    new_obj = obj.copy()

    # FULL MESH COPY
    new_obj.data = obj.data.copy()

    collection.objects.link(new_obj)

    return new_obj


def get_all_mesh_objects_recursive(collection):

    objects = []

    def recurse(col):

        for obj in col.objects:
            if obj.type == "MESH":
                objects.append(obj)

        for child in col.children:
            recurse(child)

    recurse(collection)

    return objects


def get_glb_presets():

    preset_dir = bpy.utils.user_resource(
        "SCRIPTS", path="presets/operator/export_scene.gltf"
    )

    items = [("__NONE__", "No Preset", "Use Blender defaults", 0)]

    if os.path.exists(preset_dir):
        preset_files = [f for f in os.listdir(preset_dir) if f.endswith(".py")]

        for i, file in enumerate(preset_files, start=1):
            name = os.path.splitext(file)[0]

            items.append((name, name, "", i))

    return items


# =========================================================
# RENAME LOGIC
# =========================================================


def process_collection(collection):

    mesh_objects = [obj for obj in collection.objects if obj.type == "MESH"]

    # -----------------------------------------------------
    # SKIP IF ALREADY HAS _hp AND _lp
    # -----------------------------------------------------

    has_hp = any(obj.name.lower().endswith("_hp") for obj in mesh_objects)

    has_lp = any(obj.name.lower().endswith("_lp") for obj in mesh_objects)

    if has_hp and has_lp:
        return 0

    # -----------------------------------------------------
    # 1 OBJECT -> CREATE HP COPY
    # -----------------------------------------------------

    if len(mesh_objects) == 1:
        lp_obj = mesh_objects[0]

        hp_obj = duplicate_object(lp_obj, collection)

        base_name = collection.name

        hp_name = f"{base_name}_hp"
        lp_name = f"{base_name}_lp"

        # LP
        lp_obj.name = lp_name
        lp_obj.data.name = lp_name

        # HP
        hp_obj.name = hp_name
        hp_obj.data.name = hp_name

        return 2

    # -----------------------------------------------------
    # 2 OBJECTS -> DETECT HP/LP
    # -----------------------------------------------------

    elif len(mesh_objects) == 2:
        obj_a = mesh_objects[0]
        obj_b = mesh_objects[1]

        poly_a = get_polycount(obj_a)
        poly_b = get_polycount(obj_b)

        if poly_a >= poly_b:
            hp_obj = obj_a
            lp_obj = obj_b
        else:
            hp_obj = obj_b
            lp_obj = obj_a

        base_name = collection.name

        hp_name = f"{base_name}_hp"
        lp_name = f"{base_name}_lp"

        hp_obj.name = hp_name
        lp_obj.name = lp_name

        hp_obj.data.name = hp_name
        lp_obj.data.name = lp_name

        return 2

    return 0


def recursive_process(collection):

    processed = 0

    for child in collection.children:
        processed += process_collection(child)

        processed += recursive_process(child)

    return processed


# =========================================================
# SELECT
# =========================================================


def select_by_suffix_in_collection(collection, suffix):

    bpy.ops.object.select_all(action="DESELECT")

    count = 0

    objects = get_all_mesh_objects_recursive(collection)

    for obj in objects:
        if obj.name.lower().endswith(suffix):
            obj.select_set(True)

            count += 1

    return count


# =========================================================
# HIDE / SHOW
# =========================================================


def hide_by_suffix_in_collection(collection, suffix, hide=True):

    count = 0

    objects = get_all_mesh_objects_recursive(collection)

    for obj in objects:
        if obj.name.lower().endswith(suffix):
            obj.hide_set(hide)

            count += 1

    return count


# =========================================================
# OPERATORS
# =========================================================


class OBJECT_OT_auto_hp_lp_rename(bpy.types.Operator):
    bl_idname = "object.auto_hp_lp_rename"
    bl_label = "Auto HP LP Rename"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):

        root_collection = get_active_root_collection(context)

        if not root_collection:
            self.report({"ERROR"}, "No active collection")
            return {"CANCELLED"}

        processed_count = recursive_process(root_collection)

        self.report({"INFO"}, f"Processed {processed_count} objects")

        return {"FINISHED"}


# =========================================================
# EXPORT LP GLB
# =========================================================


class EXPORT_OT_export_lp_glb(bpy.types.Operator, ExportHelper):
    bl_idname = "export_scene.export_lp_glb"
    bl_label = "Export LP GLB"

    filename_ext = ".glb"

    filter_glob: bpy.props.StringProperty(default="*.glb", options={"HIDDEN"})

    preset: EnumProperty(
        name="GLTF Preset", items=lambda self, context: get_glb_presets()
    )

    def invoke(self, context, event):
        try:
            presets = get_glb_presets()
            self.preset = presets[0][0]
            self.filepath = "//"
            context.window_manager.fileselect_add(self)
            return {"RUNNING_MODAL"}
        except Exception as exc:
            log_exception("Failed to invoke export dialog", exc)
            safe_report(self, "ERROR", f"Invoke failed: {exc}")
            return {"CANCELLED"}

    def draw(self, context):
        layout = self.layout
        layout.prop(self, "preset")

    def execute(self, context):
        try:
            root_collection = get_active_root_collection(context)
            if not root_collection:
                safe_report(self, "ERROR", "No active collection")
                return {"CANCELLED"}

            export_dir = os.path.dirname(bpy.path.abspath(self.filepath))
            if not export_dir or not os.path.exists(export_dir):
                safe_report(self, "ERROR", f"Folder does not exist: {export_dir}")
                return {"CANCELLED"}

            log_info(f"Active root collection: {root_collection.name}")
            log_info(f"Export directory: {export_dir}")
            log_info(f"Selected preset: {self.preset}")

            preset_values = {}
            if self.preset != "__NONE__":
                preset_path = os.path.join(
                    bpy.utils.user_resource(
                        "SCRIPTS", path="presets/operator/export_scene.gltf"
                    ),
                    self.preset + ".py",
                )
                log_info(f"Preset path: {preset_path}")
                if os.path.exists(preset_path):
                    with open(preset_path, "r", encoding="utf-8") as file:
                        for line in file.readlines():
                            line = line.strip()
                            if not line.startswith("op."):
                                continue
                            try:
                                left, right = line.split("=", 1)
                                prop_name = left.replace("op.", "").strip()
                                value = eval(right.strip())
                                preset_values[prop_name] = value
                            except Exception as exc:
                                log_exception(f"Preset line parse failed for: {line}", exc)
                else:
                    log_warning("Preset file does not exist; using Blender defaults")

            lp_objects = []
            for obj in get_all_mesh_objects_recursive(root_collection):
                try:
                    if obj.type == "MESH" and obj.name.lower().endswith("_lp"):
                        lp_objects.append(obj)
                except Exception as exc:
                    log_exception("Failed to inspect object for LP suffix", exc)

            log_info(f"Found LP objects: {[obj.name for obj in lp_objects]}")

            if not lp_objects:
                safe_report(self, "WARNING", "No _lp objects found in active root collection")
                return {"CANCELLED"}

            exported_count = 0
            failed_count = 0

            for obj in lp_objects:
                export_name = obj.name[:-3]
                export_path = os.path.join(export_dir, export_name + ".glb")
                log_info(f"Start export for {obj.name} -> {export_path}")

                prev_hidden = None
                try:
                    prev_hidden = obj.hide_get()
                    if prev_hidden:
                        obj.hide_set(False)

                    bpy.ops.object.select_all(action="DESELECT")
                    obj.select_set(True)
                    context.view_layer.objects.active = obj

                    if not obj.select_get():
                        raise RuntimeError("Object selection failed (possibly excluded in view layer)")
                    if context.view_layer.objects.active != obj:
                        raise RuntimeError("Failed to set object as active")

                    kwargs = {
                        "filepath": export_path,
                        "use_selection": True,
                        "export_format": "GLB",
                    }
                    kwargs.update(preset_values)

                    result = bpy.ops.export_scene.gltf(**kwargs)
                    log_info(f"Exporter result for {obj.name}: {result}")

                    if "FINISHED" in result and os.path.exists(export_path):
                        exported_count += 1
                        log_info(f"File exported OK: {export_path}")
                    else:
                        failed_count += 1
                        log_error(
                            f"Export failed for {obj.name}. Result={result}, file_exists={os.path.exists(export_path)}"
                        )
                except Exception as exc:
                    failed_count += 1
                    log_exception(f"Exception while exporting object {obj.name}", exc)
                finally:
                    try:
                        if prev_hidden:
                            obj.hide_set(True)
                    except Exception as exc:
                        log_exception(f"Failed to restore hidden state for {obj.name}", exc)

            safe_report(
                self,
                "INFO",
                f"Export finished. Success: {exported_count}, Failed: {failed_count}, Total: {len(lp_objects)}",
            )
            return {"FINISHED"}
        except Exception as exc:
            log_exception("Critical export failure", exc)
            safe_report(self, "ERROR", f"Export failed: {exc}")
            return {"CANCELLED"}


# =========================================================
# SELECT HP
# =========================================================


class OBJECT_OT_select_hp(bpy.types.Operator):
    bl_idname = "object.select_hp_objects"
    bl_label = "Select HP Objects"

    def execute(self, context):

        root_collection = get_active_root_collection(context)

        if not root_collection:
            return {"CANCELLED"}

        count = select_by_suffix_in_collection(root_collection, "_hp")

        self.report({"INFO"}, f"Selected {count} HP objects")

        return {"FINISHED"}


# =========================================================
# SELECT LP
# =========================================================


class OBJECT_OT_select_lp(bpy.types.Operator):
    bl_idname = "object.select_lp_objects"
    bl_label = "Select LP Objects"

    def execute(self, context):

        root_collection = get_active_root_collection(context)

        if not root_collection:
            return {"CANCELLED"}

        count = select_by_suffix_in_collection(root_collection, "_lp")

        self.report({"INFO"}, f"Selected {count} LP objects")

        return {"FINISHED"}


# =========================================================
# HIDE / SHOW HP
# =========================================================


class OBJECT_OT_hide_hp(bpy.types.Operator):
    bl_idname = "object.hide_hp_objects"
    bl_label = "Hide HP Objects"

    def execute(self, context):

        root_collection = get_active_root_collection(context)

        if not root_collection:
            return {"CANCELLED"}

        count = hide_by_suffix_in_collection(root_collection, "_hp", True)

        self.report({"INFO"}, f"Hidden {count} HP objects")

        return {"FINISHED"}


class OBJECT_OT_show_hp(bpy.types.Operator):
    bl_idname = "object.show_hp_objects"
    bl_label = "Show HP Objects"

    def execute(self, context):

        root_collection = get_active_root_collection(context)

        if not root_collection:
            return {"CANCELLED"}

        count = hide_by_suffix_in_collection(root_collection, "_hp", False)

        self.report({"INFO"}, f"Shown {count} HP objects")

        return {"FINISHED"}


# =========================================================
# HIDE / SHOW LP
# =========================================================


class OBJECT_OT_hide_lp(bpy.types.Operator):
    bl_idname = "object.hide_lp_objects"
    bl_label = "Hide LP Objects"

    def execute(self, context):

        root_collection = get_active_root_collection(context)

        if not root_collection:
            return {"CANCELLED"}

        count = hide_by_suffix_in_collection(root_collection, "_lp", True)

        self.report({"INFO"}, f"Hidden {count} LP objects")

        return {"FINISHED"}


class OBJECT_OT_show_lp(bpy.types.Operator):
    bl_idname = "object.show_lp_objects"
    bl_label = "Show LP Objects"

    def execute(self, context):

        root_collection = get_active_root_collection(context)

        if not root_collection:
            return {"CANCELLED"}

        count = hide_by_suffix_in_collection(root_collection, "_lp", False)

        self.report({"INFO"}, f"Shown {count} LP objects")

        return {"FINISHED"}


# =========================================================
# UI
# =========================================================


class VIEW3D_PT_hp_lp_tools(bpy.types.Panel):
    bl_label = "HP LP Tools"
    bl_idname = "VIEW3D_PT_hp_lp_tools"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "HP LP"

    def draw(self, context):

        layout = self.layout

        layout.operator("object.auto_hp_lp_rename", icon="OUTLINER_COLLECTION")

        layout.operator("export_scene.export_lp_glb", icon="EXPORT")

        layout.separator()

        layout.label(text="Selection:")

        layout.operator("object.select_hp_objects", icon="RESTRICT_SELECT_OFF")

        layout.operator("object.select_lp_objects", icon="RESTRICT_SELECT_OFF")

        layout.separator()

        layout.label(text="HP Visibility:")

        row = layout.row(align=True)

        row.operator("object.hide_hp_objects", icon="HIDE_ON")

        row.operator("object.show_hp_objects", icon="HIDE_OFF")

        layout.separator()

        layout.label(text="LP Visibility:")

        row = layout.row(align=True)

        row.operator("object.hide_lp_objects", icon="HIDE_ON")

        row.operator("object.show_lp_objects", icon="HIDE_OFF")


# =========================================================
# REGISTER
# =========================================================

classes = (
    OBJECT_OT_auto_hp_lp_rename,
    EXPORT_OT_export_lp_glb,
    OBJECT_OT_select_hp,
    OBJECT_OT_select_lp,
    OBJECT_OT_hide_hp,
    OBJECT_OT_show_hp,
    OBJECT_OT_hide_lp,
    OBJECT_OT_show_lp,
    VIEW3D_PT_hp_lp_tools,
)


def register():

    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():

    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)


if __name__ == "__main__":
    register()
