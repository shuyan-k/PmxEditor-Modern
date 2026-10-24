# -*- coding: utf-8 -*-
import sys
import numpy as np
import bpy


def dump_props(op):
    try:
        props = op.get_rna_type().properties
        print("PROPS", sorted(p.identifier for p in props))
    except Exception as exc:
        print("PROPS-ERR", exc)


def main():
    argv = sys.argv[sys.argv.index("--") + 1:]
    pmx, vmd, out, frames = argv[0], argv[1], argv[2], argv[3]
    want = [int(x) for x in frames.split(",") if x.strip()]

    bpy.ops.preferences.addon_enable(module="bl_ext.blender_org.mmd_tools")
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.preferences.addon_enable(module="bl_ext.blender_org.mmd_tools")
    dump_props(bpy.ops.mmd_tools.import_model)
    dump_props(bpy.ops.mmd_tools.import_vmd)

    bpy.ops.mmd_tools.import_model(filepath=pmx, scale=1.0,
                                   types={'MESH', 'ARMATURE', 'DISPLAY', 'MORPHS'},
                                   clean_model=True, rename_bones=False)
    arm = [o for o in bpy.context.scene.objects if o.type == "ARMATURE"][0]
    bpy.ops.mmd_tools.import_vmd(filepath=vmd, scale=1.0, margin=0, use_pose_mode=False, create_new_action=True, rename_bones=False)
    meshes = [o for o in bpy.context.scene.objects if o.type == "MESH"]
    print("MESHES", [(o.name, len(o.data.vertices)) for o in meshes])
    print("BONES", len(arm.data.bones))

    deps = bpy.context.evaluated_depsgraph_get()
    all_pos, all_bones, all_quat, all_loc = [], [], [], []
    for f in want:
        bpy.context.scene.frame_set(f)
        deps.update()
        chunk = []
        for o in sorted(meshes, key=lambda x: x.name):
            ev = o.evaluated_get(deps)
            me = ev.to_mesh()
            mw = ev.matrix_world
            co = np.empty(len(me.vertices) * 3, dtype=np.float64)
            me.vertices.foreach_get("co", co)
            co = co.reshape(-1, 3)
            co = co @ np.array(mw.to_3x3()).T + np.array(mw.translation)
            chunk.append(co)
            ev.to_mesh_clear()
        all_pos.append(np.concatenate(chunk, axis=0))
        all_bones.append(np.stack([np.array(pb.matrix) for pb in arm.pose.bones]))
        all_quat.append(np.array([list(pb.rotation_quaternion) for pb in arm.pose.bones]))
        all_loc.append(np.array([list(pb.location) for pb in arm.pose.bones]))
        print("FRAME", f, all_pos[-1].shape, all_bones[-1].shape)

    np.savez(out, frames=np.array(want), pos=np.stack(all_pos),
             bones=np.stack(all_bones), quats=np.stack(all_quat),
             locs=np.stack(all_loc),
             names=np.array([pb.name for pb in arm.pose.bones]))
    print("SAVED", out)


main()



