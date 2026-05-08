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

import bpy
from bpy.props import EnumProperty
from bpy_extras.io_utils import ExportHelper

# =========================================================
# UTILS
# =========================================================


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
        presets = get_glb_presets()

        self.preset = presets[0][0]

        self.filepath = "//"

        context.window_manager.fileselect_add(self)

        return {"RUNNING_MODAL"}

    def draw(self, context):

        layout = self.layout

        layout.prop(self, "preset")

    def execute(self, context):

        root_collection = get_active_root_collection(context)

        if not root_collection:
            self.report({"ERROR"}, "No active collection")
            return {"CANCELLED"}

        # Берем только папку
        export_dir = os.path.dirname(bpy.path.abspath(self.filepath))

        if not os.path.exists(export_dir):
            self.report({"ERROR"}, f"Folder does not exist: {export_dir}")

            return {"CANCELLED"}

        # ---------------------------------------------
        # READ PRESET
        # ---------------------------------------------

        preset_path = ""
        if self.preset != "__NONE__":
            preset_path = os.path.join(
                bpy.utils.user_resource(
                    "SCRIPTS", path="presets/operator/export_scene.gltf"
                ),
                self.preset + ".py",
            )

        preset_values = {}

        if os.path.exists(preset_path):
            with open(preset_path, "r", encoding="utf-8") as file:
                for line in file.readlines():
                    line = line.strip()

                    if line.startswith("op."):
                        try:
                            left, right = line.split("=", 1)

                            prop_name = left.replace("op.", "").strip()

                            value = eval(right.strip())

                            preset_values[prop_name] = value

                        except:
                            pass

        exported_count = 0

        # ---------------------------------------------
        # EXPORT
        # ---------------------------------------------

        lp_objects = [
            obj
            for obj in get_all_mesh_objects_recursive(root_collection)
            if obj.name.lower().endswith("_lp")
        ]

        for obj in lp_objects:

            export_name = obj.name[:-3]

            export_path = os.path.join(export_dir, export_name + ".glb")

            bpy.ops.object.select_all(action="DESELECT")

            obj.select_set(True)

            context.view_layer.objects.active = obj

            kwargs = {
                "filepath": export_path,
                "use_selection": True,
                "export_format": "GLB",
            }

            kwargs.update(preset_values)

            print("\n==============================")
            print("START EXPORT")
            print("==============================")

            print(f"OBJECT: {obj.name}")
            print(f"EXPORT PATH: {export_path}")

            print("KWARGS:")
            for k, v in kwargs.items():
                print(f"  {k} = {v}")

            try:
                result = bpy.ops.export_scene.gltf(**kwargs)

                print(f"EXPORT RESULT: {result}")

                # Blender operators return {'FINISHED'} or {'CANCELLED'}
                if "FINISHED" in result:
                    # проверяем реально ли файл создался
                    if os.path.exists(export_path):
                        print("FILE EXISTS OK")

                        exported_count += 1

                    else:
                        print("EXPORTER SAID FINISHED BUT FILE MISSING")

                else:
                    print("EXPORT CANCELLED")

            except Exception as e:
                print("EXCEPTION OCCURRED")
                print(str(e))

            print("==============================\n")

        self.report({"INFO"}, f"Exported {exported_count} GLB files")

        return {"FINISHED"}


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
