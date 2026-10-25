"""Viewport：渲染、叠加层、拾取、姿态与物理预览。"""
from __future__ import annotations

import ctypes
import math
import os
import threading
import time
from typing import Dict, Optional, Set
import numpy as np
from OpenGL import GL
from PyQt5.QtCore import (QElapsedTimer, QPoint, QRectF, Qt, QTimer, pyqtSignal)
from PyQt5.QtGui import (QColor, QFont, QFontMetrics, QImage, QImageReader, QOpenGLContext, QPainter, QPen, QSurfaceFormat)
from PyQt5.QtWidgets import QOpenGLWidget, QSizePolicy
from .. import gl_names
from ..physics import MMDPhysics
from ..pmx import (BF_ENABLED, BF_ROTATABLE, BF_TRANSLATABLE, BF_VISIBLE,
                   MF_DOUBLE_SIDED, MF_EDGE, SHAPE_NAMES)
from ..skinning import (Pose, SkinDeformer, apply_vertex_morphs, active_ik_indices,
                        material_morph_colors, resolve_morph_weights,
                        transform_to_mat4, mat4_inverse)
from ..theme import (ACCENT, BONE_RGB, GRID_MAJOR_RGB, GRID_MINOR_RGB, GRID_X_RGB, GRID_Z_RGB, GROUP_COLORS, RIGID_STATIC_RGB, TEX_MISS_BG, TEX_MISS_CELL, TEXT, TEXT_DIM, TEXT_FAINT, VIEW_BG_RGB, mono_font, ui_font)
from .camera import OrbitCamera
from .shaders import LINE_FS, LINE_VS, MESH_FS, MESH_VS, _compile
from .geom import _deg_quat, _line_geom, _point_segment_dist
from .hud import _HudOverlay


# ---------------------------------------------------------------- 视口

class Viewport(QOpenGLWidget):
    boneClicked = pyqtSignal(int)
    rigidClicked = pyqtSignal(int)
    jointClicked = pyqtSignal(int)
    selectionCleared = pyqtSignal()
    editStarted = pyqtSignal(str)
    # 即将重置姿态：主窗口借此压一条轻量撤销记录（姿态不影响 PMX 数据）
    poseAboutToReset = pyqtSignal()
    statusChanged = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        fmt = QSurfaceFormat()
        fmt.setDepthBufferSize(24)
        fmt.setStencilBufferSize(8)
        fmt.setSamples(4)
        fmt.setVersion(2, 1)
        self.setFormat(fmt)
        self.setObjectName("Viewport")
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.StrongFocus)

        self.model = None
        self.pose: Optional[Pose] = None
        self.deformer: Optional[SkinDeformer] = None
        self.physics = MMDPhysics()
        self.physics_settings = {"gravity": -9.8, "iterations": 10, "ground": True}
        self.camera = OrbitCamera()
        # 单一视图：姿态编辑随时可用，物理是独立开关（见 set_physics），
        # 两者可以同时生效（物理+姿态）。这里只记录"当前按住的骨骼"，
        # 供双击选中后的连续拖动作业。
        self._armed_bone = -1
        self.selection_kind = ""
        self.selection_index = -1
        self._pick_cycle = None
        self.show_grid = True
        # 亮度倍率（1.0 = 原始）：背景只影响清屏色，模型亮度乘到材质漫反射/环境色上
        self.bg_brightness = 1.0
        self.model_brightness = 1.0
        # 背景被提亮到浅色时，网格线与 HUD 文字要翻成深色才看得清
        self._grid_dark = False
        self.show_bones = False
        self.show_rigid = False
        self.show_joints = False
        self.show_texture = True
        self.toon = True
        self.outline = True
        self.wireframe = False
        self.morph_weights: Dict[int, float] = {}
        self._mesh = {}
        # 网格缓冲 id 单独存放：set_model 会重置 self._mesh，而缓冲对象要在
        # 多次重建之间复用，否则显存随编辑次数累积（旧实现只新建不释放）。
        self._mesh_ids: Dict[str, int] = {}
        self._tex_cache = {}
        # 结构快照：用来判断一次 structure 编辑到底动了什么，
        # 从而只重建受影响的部分（见 rebuild_structure）。
        self._struct_state = None
        # 静止姿态签名：骨骼位置/父级/付与/IK 改了要重建 Pose 与蒙皮静止位置
        self._pose_state = None
        # 静止位置与物理绑定的细分签名：用来避免"追加骨骼"时的过度重建
        self._rest_sig = None
        self._phys_state = None
        self._skin_sig = None
        # 物理世界惰性构建：浏览/编辑模式不演算，没必要每次结构编辑都 build
        self._phys_pending = False
        # 与对象身份无关的网格指纹（撤销会整对象替换，id 比较会全部失效）
        self._mesh_sig = None
        # 解码后的像素（CPU 侧），供后台预热线程与 _texture 共用
        self._tex_pixels: Dict[str, Optional[tuple]] = {}
        self._tex_lock = threading.Lock()
        self._tex_warm: Optional[threading.Thread] = None
        self._prog_mesh = 0
        self._prog_line = 0
        self._stencil_bits = 0
        self._loc = {}
        self._line = {}
        self._grid = None
        self._bone_geom = (np.zeros((0, 3), np.float32), np.zeros((0, 3), np.float32))
        self._bone_geom_r = None
        self._bone_static = None
        self._rb_geom = (np.zeros((0, 3), np.float32), np.zeros((0, 3), np.float32))
        self._joint_geom = (np.zeros((0, 3), np.float32), np.zeros((0, 3), np.float32))
        self._vbo_lines = {}
        self._line_counts = {"bone": 0, "rigid": 0, "joint": 0}
        self._line_sizes = {
            name: [0, 0] for name in ("bone", "rigid", "joint")
        }
        self._rb_world = []
        self._skin_pos = None
        self._skin_nrm = None
        self._skin_force_full = True
        self._skin_dirty_bones = set()
        self._dirty = True
        self._pose_dirty = True
        self._rb_dirty = True
        self._joint_dirty = True
        self._perf_enabled = os.environ.get("PMX_PERF") == "1"
        self._perf_check = os.environ.get("PMX_PERF_CHECK") == "1"
        self._perf_stats = {
            "refresh_geometry": 0,
            "bone_lines": 0,
            "rigid_lines": 0,
            "joint_lines": 0,
            "line_uploads": 0,
            "line_upload_bytes": 0,
            "deform_calls": 0,
            "deform_ms": 0.0,
            "solve_ik_calls": 0,
            "solve_ik_ms": 0.0,
        }
        self._fps_timer = QElapsedTimer()
        self._fps_timer.start()
        self._frames = 0
        self._fps = 0.0
        self._fps_skip = False
        # 空闲不重绘时 FPS 不会刷新，会一直显示最后一次统计值；用定时器衰减归零
        self._fps_idle = QTimer(self)
        self._fps_idle.setInterval(1000)
        self._fps_idle.timeout.connect(self._decay_fps)
        self._fps_idle.start()
        self._dragging = None
        self._last_mouse = QPoint()
        self._press_pos = QPoint()
        self._pending_pick = ("", -1)
        self._drag_bone = -1
        self._edit_pushed = False
        self._pose_moved = False
        self._hover = ""
        self._hover_pos = None
        self._hover_tick = 0.0
        self._status = "就绪"
        self._tick = QTimer(self)
        self._tick.setInterval(16)
        self._tick.timeout.connect(self._on_tick)
        self._pose_flush_timer = QTimer(self)
        self._pose_flush_timer.setTimerType(Qt.PreciseTimer)
        self._pose_flush_timer.setInterval(16)
        self._pose_flush_timer.timeout.connect(self._flush_pose_updates)
        self._pending_pose_deltas = []
        self._phys_last = QElapsedTimer()
        self._hud = _HudOverlay(self)
        self._hud.setGeometry(self.rect())

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._hud.setGeometry(self.rect())
        self._hud.raise_()

    # ------------------------------------------------------------ 生命周期
    def initializeGL(self):
        GL.glClearColor(*self._bg_color(), 1.0)
        GL.glEnable(GL.GL_DEPTH_TEST)
        GL.glEnable(GL.GL_BLEND)
        GL.glBlendFunc(GL.GL_SRC_ALPHA, GL.GL_ONE_MINUS_SRC_ALPHA)
        GL.glEnable(GL.GL_LINE_SMOOTH)
        GL.glHint(GL.GL_LINE_SMOOTH_HINT, GL.GL_NICEST)
        GL.glEnable(GL.GL_MULTISAMPLE)
        try:
            self._prog_mesh = _compile(MESH_VS, MESH_FS,
                                       {"aPos": 0, "aNrm": 1, "aUV": 2})
            self._prog_line = _compile(LINE_VS, LINE_FS,
                                       {"aPos": 0, "aColor": 1})
            self._loc = {
                "mesh": {k: GL.glGetUniformLocation(self._prog_mesh, k) for k in
                         ("uMVP", "uExpand", "uTex", "uUseTex", "uDiffuse", "uAmbient",
                          "uSpecular", "uSpecCoef", "uToon", "uOutline", "uOutlineColor",
                          "uLightDir", "uSphereTex", "uUseSphere", "uSphereMode")},
                "line": {k: GL.glGetUniformLocation(self._prog_line, k)
                         for k in ("uMVP", "uAlpha")},
            }
        except Exception as e:
            self._status = "渲染初始化失败：%s" % e
            raise
        # 新上下文里的纹理 id 全部失效，缓存必须清空（键为路径，重绘时会重新上传）
        self._tex_cache.clear()
        self._build_grid()
        self._ensure_line_vbos()
        self._upload_mesh()
        self._stencil_bits = int(GL.glGetIntegerv(GL.GL_STENCIL_BITS) or 0)
        self._invalidate_all_geometry()
        self._prewarm_textures()

    def resizeGL(self, w, h):
        GL.glViewport(0, 0, max(1, int(w * self.devicePixelRatioF())),
                      max(1, int(h * self.devicePixelRatioF())))

    def paintGL(self):
        if not self._prog_mesh:
            return
        if self.model and not self._mesh:
            self._upload_mesh()
        w, h = self.width(), self.height()
        # QPainter 绘制 HUD 会改动深度/混合等状态，每帧开场显式恢复
        GL.glEnable(GL.GL_DEPTH_TEST)
        GL.glDepthFunc(GL.GL_LESS)
        GL.glDepthMask(GL.GL_TRUE)
        # 清屏色每帧按当前亮度设置：只在 initializeGL/refresh_theme 里设会漏掉亮度调整
        GL.glClearColor(*self._bg_color(), 1.0)
        GL.glClear(GL.GL_COLOR_BUFFER_BIT | GL.GL_DEPTH_BUFFER_BIT)
        if self._dirty:
            self._invalidate_all_geometry()
        if self._pose_dirty or self._rb_dirty or self._joint_dirty:
            self._refresh_geometry(skin=True)
        cam = self.camera
        view = cam.view()
        proj = cam.projection(max(0.01, w / max(1, h)))
        mvp = proj @ view
        if self.show_grid:
            self._draw_grid(mvp)
        if self.model and self._mesh:
            self._draw_mesh(mvp)
        overlays = self.show_bones or self.show_rigid or self.show_joints
        if overlays:
            GL.glDisable(GL.GL_DEPTH_TEST)
            if self.show_bones and self._bone_geom[0].size:
                self._draw_lines("bone", mvp, 0.5, width=1.1)
            if self.show_rigid and self._rb_geom[0].size:
                self._draw_lines("rigid", mvp, 0.6, width=1.2)
            if self.show_joints and self._joint_geom[0].size:
                self._draw_lines("joint", mvp, 0.7, width=1.2)
            GL.glEnable(GL.GL_DEPTH_TEST)
        self._paint_hud_done()
        if self._fps_skip:
            # 这一次重绘是 _decay_fps 为了刷新 HUD 才触发的，不能当成真实帧率样本，
            # 否则空闲时会被算成 "1 FPS"（每秒被自己唤起一次）
            self._fps_skip = False
            self._frames = 0
            self._fps_timer.restart()
        else:
            self._frames += 1
            if self._fps_timer.elapsed() > 500:
                self._fps = self._frames * 1000.0 / max(1, self._fps_timer.elapsed())
                self._frames = 0
                self._fps_timer.restart()

    def _decay_fps(self):
        # 空闲超过 1.2 秒没有重绘时把 HUD 的 FPS 归零，避免长期显示陈旧数值
        if self._fps > 0.0 and self._fps_timer.elapsed() > 1200:
            self._fps = 0.0
            self._frames = 0
            self._fps_skip = True
            self.update()

    # ------------------------------------------------------------ 模型
    def set_model(self, model):
        self._discard_pending_pose_updates()
        self.model = model
        self._prepare_bone_cache()
        self.pose = Pose(model)
        self.deformer = SkinDeformer(model)
        self.selection_kind = ""
        self.selection_index = -1
        self.morph_weights = {}
        # 纹理缓存以（路径, 球面）为键，换模型或换贴图都不会命中错项，
        # 因此这里不再清空；否则每次结构性编辑都要重新解码并上传全部贴图。
        self._rb_world = []
        self._mesh = {}
        # 上下文尚未创建时跳过上传，initializeGL 会按当前模型补传
        if self.model and self.isValid():
            had = QOpenGLContext.currentContext() is not None
            if not had:
                self.makeCurrent()
            try:
                self._upload_mesh()
            finally:
                if not had:
                    self.doneCurrent()
        self._fit_camera()
        self.physics.release()
        self.physics = MMDPhysics()
        self.physics.gravity = self.physics_settings["gravity"]
        self.physics.iterations = self.physics_settings["iterations"]
        self.physics.ground = self.physics_settings["ground"]
        self.physics.enabled = False
        # 惰性构建：开模型时不 build 物理世界，省掉约 19 ms（米娅 183 刚体）
        self._phys_pending = True
        self._armed_bone = -1
        self._invalidate_all_geometry()
        self.update()
        self._prewarm_textures()
        self._struct_state = self.structure_state()
        self._mesh_sig = self._mesh_signature(model)
        self._pose_state = self.pose_state()
        self._rest_sig = self.rest_pos_state()
        self._phys_state = self.phys_state()
        self._skin_sig = (id(self.model.v_bones), id(self.model.v_weights))
        # 状态栏文案统一由 MainWindow 负责，这里不再覆盖（结构编辑会冲掉其它提示）

    def clear_model(self):
        self._discard_pending_pose_updates()
        self.model = None
        self._bone_static = None
        self.pose = None
        self.deformer = None
        self.selection_kind = ""
        self.selection_index = -1
        self.morph_weights = {}
        self._mesh = {}
        self._bone_geom = (np.zeros((0, 3), np.float32),
                           np.zeros((0, 3), np.float32))
        self._bone_geom_r = None
        self._rb_geom = (np.zeros((0, 3), np.float32),
                         np.zeros((0, 3), np.float32))
        self._joint_geom = (np.zeros((0, 3), np.float32),
                            np.zeros((0, 3), np.float32))
        self._rb_world = []
        self._tex_cache.clear()
        self._tick.stop()
        try:
            self.physics.release()
        except Exception:
            pass
        self._armed_bone = -1
        self._skin_pos = None
        self._skin_nrm = None
        self._struct_state = None
        self._pose_state = None
        self._rest_sig = None
        self._phys_state = None
        self._skin_sig = None
        # 物理世界惰性构建：浏览/编辑模式不演算，没必要每次结构编辑都 build
        self._phys_pending = False
        # 与对象身份无关的网格指纹（撤销会整对象替换，id 比较会全部失效）
        self._mesh_sig = None
        self._invalidate_all_geometry()
        self.update()

    STRUCT_FIELDS = ("verts", "pos", "idx", "uv", "vb", "vw",
                     "bones", "mats", "morphs", "rigid", "joints")

    def structure_state(self):
        """几何/拓扑指纹。

        只取"改动后必须重建什么"能区分的维度：顶点位置、索引、UV、
        蒙皮数组的对象身份（被重写则 id 变化）、骨骼/材质/形态/刚体/关节数量。
        """
        m = self.model
        if m is None:
            return None
        return (m.n_vertices, id(m.v_pos), id(m.indices), id(m.v_uv),
                id(m.v_bones), id(m.v_weights),
                len(m.bones), len(m.materials), len(m.morphs),
                len(m.rigid), len(m.joints))

    def pose_state(self):
        """静止姿态签名：这些字段变了就必须重建 Pose 与蒙皮静止位置。

        Pose / SkinDeformer 构造时会把骨骼位置、父级、付与参数、IK 链快照成
        numpy 数组，之后只改 model.bones 不会生效，所以这里做显式比对。
        """
        m = self.model
        if m is None:
            return None
        out = []
        for b in m.bones:
            ik = b.ik
            links = tuple((l.bone, bool(l.limited)) for l in ik.links) if ik else ()
            out.append((float(b.pos[0]), float(b.pos[1]), float(b.pos[2]),
                        int(b.parent), int(b.flags), int(b.append_parent),
                        float(b.append_ratio), int(ik.target) if ik else -1,
                        int(ik.loop) if ik else 0, links))
        return tuple(out)

    def rest_pos_state(self):
        """骨骼静止位置指纹：只有它变了才需要重建蒙皮静止数组。"""
        m = self.model
        if m is None:
            return None
        return tuple((float(b.pos[0]), float(b.pos[1]), float(b.pos[2]))
                     for b in m.bones)

    def _rest_prefix_changed(self, sig) -> bool:
        """静止位置是否有变化（按较短长度做前缀比较）。

        追加骨骼只会在尾部多出一项，旧骨骼的静止位置并没变，
        旧 SkinDeformer 的 rest_pos 仍然有效，不必重建。
        """
        old = self._rest_sig
        if old is None or sig is None:
            return True
        n = min(len(old), len(sig))
        return sig[:n] != old[:n]

    def phys_state(self):
        """物理绑定指纹：刚体/关节数量以及它们引用的骨骼索引。

        追加骨骼不会改变已有刚体的骨骼索引，所以不必重建物理世界；
        删骨骼会重映射索引，指纹随之变化。
        """
        m = self.model
        if m is None:
            return None
        return (len(m.rigid), len(m.joints),
                tuple(int(r.bone) for r in m.rigid),
                tuple((int(j.rigid_a), int(j.rigid_b)) for j in m.joints))

    def ensure_pose_current(self) -> bool:
        """骨骼位置/父级/付与/IK 等字段被改过时重建 Pose 与 SkinDeformer。"""
        m = self.model
        if m is None or self.pose is None:
            return False
        sig = self.pose_state()
        if sig == self._pose_state:
            return False
        base_rot = self.pose.base_rot.copy()
        base_trans = self.pose.base_trans.copy()
        self.pose = Pose(m)
        if base_rot.shape == self.pose.base_rot.shape:
            self.pose.base_rot = base_rot
            self.pose.base_trans = base_trans
        self.pose.apply(self.morph_weights, m.morphs)
        self.pose.world_update()
        rest = self.rest_pos_state()
        skin_sig = (id(m.v_bones), id(m.v_weights))
        if (self.deformer is None or skin_sig != self._skin_sig
                or self.deformer.rest_pos.shape[0] > len(m.bones)
                or self._rest_prefix_changed(rest)):
            self.deformer = SkinDeformer(m)
            self._skin_sig = skin_sig
        self._rest_sig = rest
        self._pose_state = sig
        self._prepare_bone_cache()
        return True

    @staticmethod
    def _mesh_signature(model):
        """与对象身份无关的网格指纹。

        structure_state() 用 id() 判断数组是否被重写，但撤销/重做会整体替换
        Document.model，id 全部变化而内容其实一致，所以另用一份内容指纹。
        """
        if model is None:
            return None
        try:
            return (int(model.n_vertices), int(model.indices.size),
                    int(model.v_uv.shape[0]), len(model.materials))
        except Exception:
            return None

    def ensure_physics(self) -> bool:
        """按需构建物理世界（惰性构建的唯一入口），返回是否可用。"""
        if not self.model:
            return False
        if self.physics is not None and self.physics._ready and not self._phys_pending:
            return True
        if self.physics is None:
            self.physics = MMDPhysics()
        self.physics.gravity = self.physics_settings["gravity"]
        self.physics.iterations = self.physics_settings["iterations"]
        self.physics.ground = self.physics_settings["ground"]
        try:
            self.physics.build(self.model)
        except Exception as e:
            self.physics.error = str(e)
        self._phys_pending = False
        self._rb_dirty = True
        return bool(self.physics._ready)

    def adopt_model(self, model) -> bool:
        """接管结构等价的另一个模型对象，返回 False 表示必须整次 set_model。

        撤销/重做会把 Document.model 换成快照副本：网格与材质布局没变时，
        只需要重建 Pose/SkinDeformer 与缓存，不必重传网格、重置相机或重建
        物理世界。网格布局变了则交回调用方处理。
        """
        if model is None or self.model is None or self.pose is None:
            return False
        if self._mesh_signature(model) != self._mesh_sig:
            return False
        self.model = model
        self._prepare_bone_cache()
        if any(i >= len(model.morphs) for i in self.morph_weights):
            self.morph_weights = {}
        base = (self.pose.base_rot.copy(), self.pose.base_trans.copy())
        self.pose = Pose(model)
        if base[0].shape == self.pose.base_rot.shape:
            self.pose.base_rot = base[0]
            self.pose.base_trans = base[1]
        self.pose.apply(self.morph_weights, model.morphs)
        self.pose.world_update()
        self.deformer = SkinDeformer(model)
        self._struct_state = self.structure_state()
        self._mesh_sig = self._mesh_signature(model)
        self._pose_state = self.pose_state()
        self._rest_sig = self.rest_pos_state()
        self._skin_sig = (id(model.v_bones), id(model.v_weights))
        if self.phys_state() != self._phys_state:
            self.rebuild_physics()
        self._phys_state = self.phys_state()
        if self.selection_index >= len(model.bones):
            self.selection_kind = ""
            self.selection_index = -1
        self._invalidate_all_geometry()
        self.update()
        return True

    def rebuild_structure(self) -> bool:
        """结构编辑后的就地最小重建。

        返回 True 表示已处理；False 表示改动涉及顶点/索引/UV/材质区间，
        调用方应当走完整的 set_model()（会重新上传网格并重置相机）。
        """
        model = self.model
        old = self._struct_state
        new = self.structure_state()
        if model is None or old is None or new is None or self.pose is None:
            return False
        o = dict(zip(self.STRUCT_FIELDS, old))
        n = dict(zip(self.STRUCT_FIELDS, new))
        if (n["verts"], n["pos"], n["idx"], n["uv"], n["mats"]) != (
                o["verts"], o["pos"], o["idx"], o["uv"], o["mats"]):
            return False                      # 网格本体变了，只能全量重建
        bones_changed = n["bones"] != o["bones"]
        rest_changed = self.pose_state() != self._pose_state
        skin_changed = n["vb"] != o["vb"] or n["vw"] != o["vw"]
        # 物理世界只在刚体/关节本身或被引用的骨骼索引变化时才需要重建。
        # 单纯追加骨骼不影响已有刚体的索引，之前一律重建白白花掉约 19 ms。
        phys_changed = self.phys_state() != self._phys_state
        pose = self.pose
        base = (pose.base_rot.copy(), pose.base_trans.copy())
        self._prepare_bone_cache()
        if bones_changed or skin_changed or rest_changed:
            self.pose = Pose(model)
            if base[0].shape == self.pose.base_rot.shape:
                self.pose.base_rot = base[0]
                self.pose.base_trans = base[1]
            self.pose.apply(self.morph_weights, model.morphs)
            self.pose.world_update()
            rest = self.rest_pos_state()
            skin_sig = (id(model.v_bones), id(model.v_weights))
            # 追加骨骼时没有任何顶点引用新骨骼，旧 Deformer 仍然安全：
            # 它的 offsets 少一行只影响不存在的骨骼索引，省掉约 7.5 ms。
            if (self.deformer is None or skin_sig != self._skin_sig
                    or self.deformer.rest_pos.shape[0] > len(model.bones)
                    or self._rest_prefix_changed(rest)):
                self.deformer = SkinDeformer(model)
                self._skin_sig = skin_sig
            self._rest_sig = rest
        if phys_changed:
            self.rebuild_physics()
        self._struct_state = new
        self._mesh_sig = self._mesh_signature(model)
        self._pose_state = self.pose_state()
        self._phys_state = self.phys_state()
        self._invalidate_all_geometry()
        self.update()
        return True

    def mark_dirty(self, physics: bool = False):
        if physics:
            self.rebuild_physics()
            return
        self.ensure_pose_current()
        self._prepare_bone_cache()
        self._invalidate_all_geometry()
        self.update()

    def refresh_textures(self):
        # 缓存以（路径, 球面）为键：换贴图只是换键，无需清空。
        # 清空会让下一次重绘重新解码全部贴图（真机 12 张约 290 ms/次）。
        self.update()

    def _invalidate_all_geometry(self):
        self._dirty = False
        self._pose_dirty = True
        self._rb_dirty = True
        self._joint_dirty = True
        self._mark_full_skin_dirty()

    def _mark_full_skin_dirty(self):
        self._skin_force_full = True
        self._skin_dirty_bones.clear()

    def _mark_incremental_skin_dirty(self, bones):
        if not self.pose or not self.model:
            self._mark_full_skin_dirty()
            return
        self._skin_dirty_bones.update(self.pose.changed_subtrees(bones))
        if len(self._skin_dirty_bones) > len(self.model.bones) * 0.3:
            self._mark_full_skin_dirty()

    def _mark_selection_geometry_dirty(self, *kinds):
        for kind in kinds:
            if kind == "bone":
                self._pose_dirty = True
            elif kind == "rigid":
                self._rb_dirty = True
            elif kind == "joint":
                self._joint_dirty = True

    def _prepare_bone_cache(self):
        model = self.model
        if not model or not model.bones:
            self._bone_static = None
            return
        visible = [
            i for i, bone in enumerate(model.bones)
            if bone.flags & 0x0008
        ]
        indices = np.asarray(visible, dtype=np.int32)
        tail_bones = np.full(len(visible), -1, dtype=np.int32)
        tail_offsets = np.zeros((len(visible), 3), dtype=np.float32)
        after_physics = np.zeros(len(visible), dtype=bool)
        ik = np.zeros(len(visible), dtype=bool)
        not_operable = np.zeros(len(visible), dtype=bool)
        for row, bone_index in enumerate(visible):
            bone = model.bones[bone_index]
            if bone.flags & 0x0001 and 0 <= bone.tail_bone < len(model.bones):
                tail_bones[row] = bone.tail_bone
            else:
                tail_offsets[row] = bone.tail_offset
            after_physics[row] = bool(bone.flags & 0x1000)
            ik[row] = bool(bone.flags & 0x0020)
            not_operable[row] = (bone.flags & 0x0010) == 0
        self._bone_static = {
            "indices": indices,
            "tail_bones": tail_bones,
            "tail_offsets": tail_offsets,
            "after_physics": after_physics,
            "ik": ik,
            "not_operable": not_operable,
        }

    def _buffer(self, key: str) -> int:
        """按名字取持久 VBO id，没有则创建一次。"""
        vbo = self._mesh_ids.get(key)
        if vbo is None:
            vbo = GL.glGenBuffers(1)
            self._mesh_ids[key] = vbo
        return vbo

    def _upload_mesh(self):
        if not self._prog_mesh:
            return
        m = self.model
        self._mesh = {}
        if not m or m.n_vertices == 0:
            return
        # 复用缓冲对象；尺寸变化时 glBufferData 会自行重新分配显存。
        vbo_pos = self._buffer("mesh.pos")
        vbo_nrm = self._buffer("mesh.nrm")
        vbo_uv = self._buffer("mesh.uv")
        vbo_idx = self._buffer("mesh.idx")
        GL.glBindBuffer(GL.GL_ARRAY_BUFFER, vbo_pos)
        GL.glBufferData(GL.GL_ARRAY_BUFFER, m.v_pos.nbytes,
                        np.ascontiguousarray(m.v_pos, np.float32), GL.GL_DYNAMIC_DRAW)
        GL.glBindBuffer(GL.GL_ARRAY_BUFFER, vbo_nrm)
        GL.glBufferData(GL.GL_ARRAY_BUFFER, m.v_nrm.nbytes,
                        np.ascontiguousarray(m.v_nrm, np.float32), GL.GL_DYNAMIC_DRAW)
        GL.glBindBuffer(GL.GL_ARRAY_BUFFER, vbo_uv)
        GL.glBufferData(GL.GL_ARRAY_BUFFER, m.v_uv.nbytes,
                        np.ascontiguousarray(m.v_uv, np.float32), GL.GL_STATIC_DRAW)
        GL.glBindBuffer(GL.GL_ELEMENT_ARRAY_BUFFER, vbo_idx)
        idx = np.ascontiguousarray(m.indices, np.int32)
        GL.glBufferData(GL.GL_ELEMENT_ARRAY_BUFFER, idx.nbytes, idx, GL.GL_STATIC_DRAW)
        GL.glBindBuffer(GL.GL_ELEMENT_ARRAY_BUFFER, 0)
        GL.glBindBuffer(GL.GL_ARRAY_BUFFER, 0)
        ranges = []
        for mt, start, count in m.material_ranges():
            ranges.append((mt, start * 4, count))  # 字节偏移
        self._mesh = {"pos": vbo_pos, "nrm": vbo_nrm, "uv": vbo_uv, "idx": vbo_idx,
                      "ranges": ranges, "count": int(idx.size)}
        self._skin_pos = m.v_pos
        self._skin_nrm = m.v_nrm
        self._invalidate_all_geometry()

    def _fit_camera(self):
        m = self.model
        if not m or not m.n_vertices:
            self.camera = OrbitCamera()
            return
        v = m.v_pos
        mask = np.isfinite(v).all(axis=1)
        if not mask.any():
            return
        lo = v[mask].min(axis=0)
        hi = v[mask].max(axis=0)
        self.camera.fit(lo, hi)

    # ------------------------------------------------------------ 更新
    def set_physics(self, on: bool):
        """物理开关；与姿态编辑互不排斥（物理演算的同时仍可摆姿）。"""
        if on:
            self.ensure_physics()
            if self.physics._ready:
                self.physics.reset(self.pose, self.morph_weights,
                                   self.model.morphs if self.model else None)
                self.physics.enabled = True
                self._phys_last.restart()
                self._tick.start()
                self.statusChanged.emit("物理演算已开启")
            else:
                self.statusChanged.emit("物理不可用：%s" % (self.physics.error or "未知原因"))
        else:
            self.physics.enabled = False
            self._tick.stop()
            if self.pose:
                self.pose.clear_overrides()
                self.pose.apply(self.morph_weights, self.model.morphs if self.model else None)
            self.statusChanged.emit("物理演算已停止")
        self._pose_dirty = True
        self._rb_dirty = True
        self._mark_full_skin_dirty()
        self.update()

    def apply_physics_settings(self, gravity=None, iterations=None, ground=None):
        if gravity is not None:
            self.physics_settings["gravity"] = float(gravity)
            self.physics.gravity = float(gravity)
        if iterations is not None:
            self.physics_settings["iterations"] = int(iterations)
            self.physics.iterations = int(iterations)
        if ground is not None:
            self.physics_settings["ground"] = bool(ground)
            self.physics.ground = bool(ground)
        if self.model and self.physics._ready:
            # 重力/迭代次数直接改现有世界（保留当前姿态）；地面开关要增删
            # 刚体，只能重建。
            if ground is None:
                self.physics.set_params(self.physics.gravity,
                                        self.physics.iterations)
            else:
                was = self.physics.enabled
                self.physics.build(self.model)
                if was:
                    self.physics.reset(self.pose, self.morph_weights,
                                       self.model.morphs if self.model else None)
                    self.physics.enabled = True
        self._pose_dirty = True
        self._rb_dirty = True
        self._mark_full_skin_dirty()
        self.update()

    def apply_rigid_params(self, index: int) -> bool:
        """把单个刚体的质量/摩擦力热更新进现有 Bullet 世界。

        返回 False 表示这个世界里没有对应刚体，或该刚体是静态/运动学类型
        （质量改动无意义，由物理模块跳过）。
        """
        if not self.model or not (0 <= index < len(self.model.rigid)):
            return False
        if self.physics is None or not self.ensure_physics():
            return False
        rb = self.model.rigid[index]
        ok = self.physics.set_body_params(index, mass=float(rb.mass),
                                          friction=float(rb.friction))
        self._rb_dirty = True
        self.update()
        return ok

    def rebuild_physics(self):
        """结构或参数变化后重建物理世界，保持开关状态。

        默认惰性：只作废旧世界并置待建标记，真正演算时再由 ensure_physics()
        构建；若此刻正在演算（was=True）则立刻重建，避免物理停摆。
        """
        was = self.physics.enabled if self.physics else False
        self.physics.release()
        self.physics = MMDPhysics()
        self.physics.gravity = self.physics_settings["gravity"]
        self.physics.iterations = self.physics_settings["iterations"]
        self.physics.ground = self.physics_settings["ground"]
        self._phys_pending = True
        if was:
            self.ensure_physics()
        if was and self.physics._ready:
            self.physics.reset(self.pose, self.morph_weights,
                               self.model.morphs if self.model else None)
            self.physics.enabled = True
            self._phys_last.restart()
        else:
            self._tick.stop()
        self._pose_dirty = True
        self._rb_dirty = True
        self._joint_dirty = True
        self._mark_full_skin_dirty()
        self.update()

    def _on_tick(self):
        if not (self.model and self.pose):
            return
        if not self.ensure_physics():
            return
        dt = max(0.0, min(0.05, self._phys_last.elapsed() / 1000.0))
        self._phys_last.restart()
        self.pose.apply(self.morph_weights, self.model.morphs)
        self.physics.step(self.pose, dt if dt > 0 else 1 / 60.0,
                          self.morph_weights, self.model.morphs)
        self._pose_dirty = True
        self._rb_dirty = True
        self._mark_full_skin_dirty()
        self.update()

    def reset_pose(self):
        self._discard_pending_pose_updates()
        if self.pose:
            self.poseAboutToReset.emit()
            self.pose.reset()
            self.physics.reset(self.pose, self.morph_weights,
                               self.model.morphs if self.model else None)
            self._pose_dirty = True
            self._mark_full_skin_dirty()
            if self.physics.enabled:
                self._rb_dirty = True
            self.update()
            self.statusChanged.emit("姿态已重置")

    def set_morph_weights(self, weights: Dict[int, float]):
        # 组形态/翻转形态先展开成实际子形态权重，之后顶点/UV/骨骼/材质
        # 四类形态都能按普通权重生效（面板上的滑杆仍只对应被拖的那个形态）。
        self.morph_weights = dict(weights)
        if self.model:
            try:
                self.morph_weights = resolve_morph_weights(self.model, self.morph_weights)
            except Exception:
                pass
        if self.pose:
            self.pose.apply(self.morph_weights, self.model.morphs if self.model else None)
        self._pose_dirty = True
        self._mark_full_skin_dirty()
        self.update()

    def set_selection(self, kind: str, index: int):
        old_kind = self.selection_kind
        self.selection_kind = kind
        self.selection_index = int(index)
        self._mark_selection_geometry_dirty(old_kind, kind)
        self.update()

    def _bg_color(self):
        """清屏色按背景亮度换算：<100% 向黑压缩，>100% 向白插值。

        纯乘法在深色底上几乎看不出差别（0.08*1.6 仍是深灰），所以提亮改成
        「向白色插值」，拖到 200% 能得到明显的浅灰底，方便看轮廓。
        """
        b = max(0.0, min(3.0, float(self.bg_brightness)))
        out = []
        for c in VIEW_BG_RGB:
            if b >= 1.0:
                k = min(1.0, (b - 1.0) * 0.6)
                v = c + (1.0 - c) * k
            else:
                v = c * b
            out.append(min(1.0, max(0.0, v)))
        return tuple(out)

    def _bg_luma(self):
        r, g, b = self._bg_color()
        return 0.2126 * r + 0.7152 * g + 0.0722 * b

    def _grid_needs_dark(self):
        """背景够亮时网格线要用深色，否则浅线铺在浅底上几乎看不见。"""
        return self._bg_luma() > 0.55

    def set_brightness(self, bg=None, model=None):
        """设置背景/模型亮度倍率（1.0 = 原始），只影响显示不影响数据。"""
        if bg is not None:
            self.bg_brightness = max(0.0, min(3.0, float(bg)))
        if model is not None:
            self.model_brightness = max(0.1, min(3.0, float(model)))
        want_dark = self._grid_needs_dark()
        if want_dark != self._grid_dark:
            self._grid_dark = want_dark
            if self.isValid():
                self.makeCurrent()
                try:
                    self._build_grid()
                finally:
                    self.doneCurrent()
        self.update()

    def set_display(self, **kwargs):
        for k, v in kwargs.items():
            if hasattr(self, k):
                setattr(self, k, bool(v))
                if v and k == "show_rigid":
                    self._rb_dirty = True
                elif v and k == "show_joints":
                    self._joint_dirty = True
        self.update()

    def frame_all(self):
        self._fit_camera()
        self.update()

    def refresh_theme(self):
        """配色切换后重建视口配色相关资源（清屏色、地面网格）。

        需要当前上下文有效才能重建 VBO，故先在方法内 makeCurrent；
        窗口尚未首次绘制时直接跳过，initializeGL 会按新色板初始化。"""
        self._invalidate_all_geometry()
        if not self.isValid():
            self.update()
            return
        had = QOpenGLContext.currentContext() is not None
        self.makeCurrent()
        try:
            GL.glClearColor(*self._bg_color(), 1.0)
            self._build_grid()
            # 缺失贴图的棋盘占位图随配色变化，清缓存让其重新生成
            tex_ids = [int(t) for t in self._tex_cache.values()]
            if tex_ids:
                GL.glDeleteTextures(tex_ids)
                self._tex_cache.clear()
        finally:
            if not had:
                self.doneCurrent()
        self.update()

    def frame_selected(self):
        if not self.model:
            return
        p = None
        if self.selection_kind == "bone" and 0 <= self.selection_index < len(self.model.bones):
            p = self.model.bones[self.selection_index].pos
        elif self.selection_kind == "rigid" and 0 <= self.selection_index < len(self.model.rigid):
            p = self.model.rigid[self.selection_index].pos
        elif self.selection_kind == "joint" and 0 <= self.selection_index < len(self.model.joints):
            p = self.model.joints[self.selection_index].pos
        if p:
            self.camera.target = np.array(p, dtype=np.float32)
            self.camera.distance = max(4.0, min(self.camera.distance, 30.0))
            self.update()

    # ------------------------------------------------------------ 蒙皮与叠加
    def _refresh_geometry(self, skin: bool):
        if self._perf_enabled:
            self._perf_stats["refresh_geometry"] += 1
        if self._dirty:
            self._invalidate_all_geometry()
        if self._pose_dirty:
            self._refresh_pose_geometry(skin)
        self._refresh_static_overlays()

    def _refresh_pose_geometry(self, skin: bool = True):
        m = self.model
        if not m or not self.pose:
            self._pose_dirty = False
            return
        morphs = m.morphs
        base_pos, base_uv = apply_vertex_morphs(
            m, self.morph_weights, self.deformer)
        self.pose.apply(self.morph_weights, morphs)
        world = self.pose.world()
        skin_changed = False
        needs_skin = (self._skin_force_full or bool(self._skin_dirty_bones)
                      or self._skin_pos is None or self._skin_nrm is None)
        if skin and self.deformer and needs_skin:
            started = time.perf_counter() if self._perf_enabled else None
            try:
                if self._skin_force_full or self._skin_pos is None or self._skin_nrm is None:
                    pos, nrm = self.deformer.deform(base_pos, m.v_nrm, world)
                else:
                    pos, nrm = self.deformer.deform_subset(
                        base_pos, m.v_nrm, world, self._skin_dirty_bones,
                        self._skin_pos, self._skin_nrm)
                    if self._perf_check:
                        reference_pos, reference_nrm = self.deformer.deform(
                            base_pos, m.v_nrm, world)
                        pos_error = (float(np.max(np.abs(pos - reference_pos)))
                                     if pos.size else 0.0)
                        nrm_error = (float(np.max(np.abs(nrm - reference_nrm)))
                                     if nrm.size else 0.0)
                        if max(pos_error, nrm_error) > 1e-4:
                            raise AssertionError(
                                "增量蒙皮对拍失败：位置误差 %.8g，法线误差 %.8g"
                                % (pos_error, nrm_error))
            finally:
                if self._perf_enabled:
                    self._perf_stats["deform_calls"] += 1
                    self._perf_stats["deform_ms"] += (time.perf_counter() - started) * 1000.0
            self._skin_pos, self._skin_nrm = pos, nrm
            skin_changed = True
            if self._mesh:
                GL.glBindBuffer(GL.GL_ARRAY_BUFFER, self._mesh["pos"])
                GL.glBufferSubData(GL.GL_ARRAY_BUFFER, 0, pos.nbytes,
                                   np.ascontiguousarray(pos, np.float32))
                GL.glBindBuffer(GL.GL_ARRAY_BUFFER, self._mesh["nrm"])
                GL.glBufferSubData(GL.GL_ARRAY_BUFFER, 0, nrm.nbytes,
                                   np.ascontiguousarray(nrm, np.float32))
                GL.glBindBuffer(GL.GL_ARRAY_BUFFER, 0)
        self._build_bone_lines(world)
        self._upload_line_geom("bone", self._bone_geom)
        if skin_changed:
            self._skin_force_full = False
            self._skin_dirty_bones.clear()
        self._pose_dirty = False
        # 刚体/关节叠加层挂在骨骼上，摆姿后要按新姿态重建；
        # 隐藏时先记脏，等用户打开显示开关再建。
        if self.show_rigid:
            self._rb_dirty = True
        if self.show_joints:
            self._joint_dirty = True

    def _refresh_static_overlays(self):
        if self._rb_dirty:
            self._build_rigid_lines()
            self._upload_line_geom("rigid", self._rb_geom)
            self._rb_dirty = False
        if self._joint_dirty:
            self._build_joint_lines()
            self._upload_line_geom("joint", self._joint_geom)
            self._joint_dirty = False

    def _solve_ik(self, max_loops: int = 0, only: Optional[Set[int]] = None):
        if not self.pose:
            return 0
        if not self._perf_enabled:
            return self.pose.solve_ik(max_loops=max_loops, only=only)
        started = time.perf_counter()
        try:
            return self.pose.solve_ik(max_loops=max_loops, only=only)
        finally:
            self._perf_stats["solve_ik_calls"] += 1
            self._perf_stats["solve_ik_ms"] += (time.perf_counter() - started) * 1000.0

    def _build_bone_lines(self, world):
        if self._perf_enabled:
            self._perf_stats["bone_lines"] += 1
        m = self.model
        static = self._bone_static
        if not m or not static or static["indices"].size == 0:
            self._bone_geom = (np.zeros((0, 3), np.float32), np.zeros((0, 3), np.float32))
            return
        indices = static["indices"]
        heads = world[indices, :3, 3].copy()
        tails = heads + static["tail_offsets"]
        use_bone_tail = static["tail_bones"] >= 0
        if use_bone_tail.any():
            tails[use_bone_tail] = world[static["tail_bones"][use_bone_tail], :3, 3]
        directions = tails - heads
        lengths = np.linalg.norm(directions, axis=1)
        degenerate = lengths < 1e-5
        if degenerate.any():
            tails[degenerate] = heads[degenerate] + np.array(
                [0.0, 0.4, 0.0], dtype=np.float32)
            directions[degenerate] = tails[degenerate] - heads[degenerate]
            lengths[degenerate] = np.linalg.norm(directions[degenerate], axis=1)
        directions /= np.maximum(1e-6, lengths)[:, None]

        ups = np.zeros_like(directions)
        ups[:, 1] = 1.0
        use_z_up = np.abs(directions[:, 1]) > 0.98
        ups[use_z_up] = (0.0, 0.0, 1.0)
        sides = np.cross(directions, ups)
        side_lengths = np.linalg.norm(sides, axis=1)
        sides /= np.maximum(1e-6, side_lengths)[:, None]
        up2 = np.cross(sides, directions)
        widths = np.maximum(0.012, lengths * 0.055)[:, None]
        mids = heads + directions * (lengths * 0.18)[:, None]
        ring = np.stack((
            mids + sides * widths,
            mids + up2 * widths,
            mids - sides * widths,
            mids - up2 * widths,
        ), axis=1)

        colors = np.broadcast_to(
            np.asarray(BONE_RGB, dtype=np.float32), heads.shape).copy()
        colors[static["after_physics"]] = (0.35, 0.85, 0.78)
        colors[static["ik"]] = (0.98, 0.75, 0.35)
        selected = ((indices == self.selection_index)
                    & (self.selection_kind == "bone"))
        colors[selected] = (0.31, 0.72, 1.0)
        colors[static["not_operable"]] *= 0.5

        n = len(indices)
        starts = np.zeros((n, 11, 3), dtype=np.float32)
        ends = np.zeros_like(starts)
        segment_colors = np.broadcast_to(colors[:, None, :], starts.shape).copy()
        starts[:, 0] = heads
        ends[:, 0] = np.where(selected[:, None], ring[:, 0], tails)
        segment_colors[:, 0] *= np.where(selected, 1.0, 0.85)[:, None]
        for i in range(3):
            starts[:, 1 + i] = np.where(selected[:, None], heads, ring[:, i])
            ends[:, 1 + i] = ring[:, i + 1]
        starts[:, 4] = np.where(selected[:, None], ring[:, 0], ring[:, 3])
        ends[:, 4] = np.where(selected[:, None], tails, ring[:, 0])
        for i in range(3):
            starts[:, 5 + i] = ring[:, i + 1]
            ends[:, 5 + i] = tails
        axis_colors = np.asarray(
            ((0.93, 0.35, 0.35), (0.4, 0.9, 0.5), (0.35, 0.6, 1.0)),
            dtype=np.float32)
        for i in range(3):
            starts[:, 8 + i] = heads
            ends[:, 8 + i] = heads
            ends[:, 8 + i, i] += 2.0
            segment_colors[:, 8 + i] = axis_colors[i]
        valid = np.arange(11)[None, :] < np.where(selected, 11, 5)[:, None]
        vertices = np.stack((starts, ends), axis=2)[valid].reshape(-1, 3)
        line_colors = np.repeat(segment_colors[valid], 2, axis=0)
        self._bone_geom = (vertices, line_colors)

    def _build_bone_lines_reference(self, world):
        m = self.model
        if not m or not m.bones:
            self._bone_geom = (np.zeros((0, 3), np.float32), np.zeros((0, 3), np.float32))
            return
        segs = []
        has_ik = np.zeros(len(m.bones), bool)
        for i, b in enumerate(m.bones):
            if not (b.flags & 0x0008):  # 非表示
                continue
            if b.flags & 0x0020:
                has_ik[i] = True
            head = world[i][:3, 3]
            if b.flags & 0x0001 and 0 <= b.tail_bone < len(m.bones):
                tail = world[b.tail_bone][:3, 3]
            else:
                tail = head + np.array(b.tail_offset, dtype=np.float32)
            d = tail - head
            ln = float(np.linalg.norm(d))
            if ln < 1e-5:
                tail = head + np.array([0.0, max(0.4, 0.0), 0.0], np.float32)
                d = tail - head
                ln = float(np.linalg.norm(d))
            col = np.array(BONE_RGB, np.float32)
            if b.flags & 0x1000:
                col = np.array([0.35, 0.85, 0.78], np.float32)
            if b.flags & 0x0020:
                col = np.array([0.98, 0.75, 0.35], np.float32)
            if i == self.selection_index and self.selection_kind == "bone":
                col = np.array([0.31, 0.72, 1.0], np.float32)
            if (b.flags & 0x0010) == 0:
                col = col * 0.5
            # 细长八面体轮廓
            d /= max(1e-6, ln)
            up = np.array([0.0, 1.0, 0.0], np.float32)
            if abs(float(np.dot(d, up))) > 0.98:
                up = np.array([0.0, 0.0, 1.0], np.float32)
            side = np.cross(d, up)
            side /= max(1e-6, np.linalg.norm(side))
            up2 = np.cross(side, d)
            w = max(0.012, ln * 0.055)
            mid = head + d * (ln * 0.18)
            sel = i == self.selection_index and self.selection_kind == "bone"
            if not sel:
                # 未选中：中心细线 + 小菱形，避免大量骨骼遮挡模型
                segs.append((head, tail, col * 0.85))
                ring = [mid + side * w, mid + up2 * w, mid - side * w, mid - up2 * w]
                segs.append((ring[0], ring[1], col))
                segs.append((ring[1], ring[2], col))
                segs.append((ring[2], ring[3], col))
                segs.append((ring[3], ring[0], col))
                continue
            ring = [mid + side * w, mid + up2 * w, mid - side * w, mid - up2 * w]
            segs.append((head, ring[0], col))
            segs.append((head, ring[1], col))
            segs.append((head, ring[2], col))
            segs.append((head, ring[3], col))
            segs.append((ring[0], tail, col))
            segs.append((ring[1], tail, col))
            segs.append((ring[2], tail, col))
            segs.append((ring[3], tail, col))
            if sel:
                segs.append((head, head + np.array([2.0, 0, 0], np.float32),
                             np.array([0.93, 0.35, 0.35], np.float32)))
                segs.append((head, head + np.array([0, 2.0, 0], np.float32),
                             np.array([0.4, 0.9, 0.5], np.float32)))
                segs.append((head, head + np.array([0, 0, 2.0], np.float32),
                             np.array([0.35, 0.6, 1.0], np.float32)))
        self._bone_geom = _line_geom(segs)

    def _pose_delta_matrix(self, bone: int):
        """骨骼从静止位置到当前姿态的 4×4 变换；无姿态或索引无效时返回 None。

        刚体/关节在 PMX 里存的是静止世界坐标，但 MMD 语义上它们挂在骨骼上；
        摆姿或整体位移后叠加层必须乘上同一个骨骼增量，否则会像"漂"在原地。
        """
        if self.pose is None or not self.model:
            return None
        if not (0 <= bone < len(self.model.bones)):
            return None
        world = self.pose.world()
        if not (0 <= bone < len(world)):
            return None
        R = world[bone][:3, :3]
        rest = np.asarray(self.model.bones[bone].pos, np.float32)
        M = np.eye(4, dtype=np.float32)
        M[:3, :3] = R
        M[:3, 3] = world[bone][:3, 3] - R @ rest
        return M

    def _rigid_rest_matrix(self, index: int):
        rb = self.model.rigid[index]
        return transform_to_mat4(rb.pos, _deg_quat(rb.rot))

    def _global_pose_delta(self):
        """模型的整体姿态增量：取子树最大的根骨骼（通常是「全ての親」）。

        没有关联骨骼的刚体（bone = -1，例如本模型的胸部物理体）在 MMD 里
        不跟骨骼走；但编辑视口里整体平移/旋转模型时，它们也应当跟着模型走，
        否则会像截图中那样留在原地。
        """
        if self.pose is None or not self.model or not self.model.bones:
            return None
        best, best_n = -1, 0
        n = len(self.model.bones)
        for i, b in enumerate(self.model.bones):
            p = b.parent
            if p < 0 or p >= n or p == i:
                count = len(self.pose.subtrees[i])
                if count > best_n:
                    best, best_n = i, count
        return self._pose_delta_matrix(best) if best >= 0 else None

    def _rigid_current_matrix(self, index: int):
        """刚体叠加层当前矩阵：物理演算中取模拟变换，否则跟随所属骨骼姿态。"""
        index = int(index)
        if self.physics.enabled and self.physics._ready \
                and index < len(self.physics.body_map):
            bi = self.physics.body_map[index]
            if (bi >= 0 and index < len(self.physics._body_positions)
                    and index < len(self.physics._body_rotations)):
                return transform_to_mat4(
                    self.physics._body_positions[index],
                    self.physics._body_rotations[index])
        M = self._rigid_rest_matrix(index)
        rb = self.model.rigid[index]
        if 0 <= rb.bone < len(self.model.bones):
            D = self._pose_delta_matrix(rb.bone)
        else:
            # 无骨骼刚体：只跟随模型的整体变换（根骨骼增量）
            D = self._global_pose_delta()
        return M if D is None else D @ M

    def _joint_current_matrix(self, index: int):
        """关节跟随它引用的第一个刚体（无骨骼引用时退回第二个）。"""
        j = self.model.joints[int(index)]
        M = transform_to_mat4(j.pos, _deg_quat(j.rot))
        for ri in (j.rigid_a, j.rigid_b):
            if 0 <= ri < len(self.model.rigid):
                D = (self._rigid_current_matrix(ri)
                     @ mat4_inverse(self._rigid_rest_matrix(ri)))
                return D @ M
        return M

    def _build_rigid_lines(self):
        if self._perf_enabled:
            self._perf_stats["rigid_lines"] += 1
        m = self.model
        if not m or not m.rigid:
            self._rb_geom = (np.zeros((0, 3), np.float32), np.zeros((0, 3), np.float32))
            return
        segs = []
        self._rb_world = []
        for i, rb in enumerate(m.rigid):
            M = self._rigid_current_matrix(i)
            self._rb_world.append(M)
            color = QColor(GROUP_COLORS[rb.group % len(GROUP_COLORS)])
            col = np.array([color.redF(), color.greenF(), color.blueF()], np.float32)
            sel = i == self.selection_index and self.selection_kind == "rigid"
            if sel:
                col = np.array([0.31, 0.72, 1.0], np.float32)
            elif rb.mode == 0:
                col = np.array(RIGID_STATIC_RGB, np.float32)
            if sel:
                segs.extend(self._rigid_shape_segments(rb, M, col))
            else:
                t = M[:3, 3]
                R = M[:3, :3]
                d = 0.22
                for k in range(3):
                    v = np.eye(3, dtype=np.float32)[k] * d
                    segs.append((tuple(t - R @ v), tuple(t + R @ v), col))
        self._rb_geom = _line_geom(segs)

    @staticmethod
    def _rigid_shape_segments(rb, M, col):
        segs = []
        sx, sy, sz = rb.size
        R = M[:3, :3]
        t = M[:3, 3]

        def pt(x, y, z):
            return tuple(t + R @ np.array([x, y, z], np.float32))

        if rb.shape == 0:
            r = abs(sx)
            for axis in (0, 1, 2):
                ring = []
                for k in range(17):
                    a = k * math.pi * 2 / 16
                    if axis == 0:
                        ring.append(pt(0, math.cos(a) * r, math.sin(a) * r))
                    elif axis == 1:
                        ring.append(pt(math.cos(a) * r, 0, math.sin(a) * r))
                    else:
                        ring.append(pt(math.cos(a) * r, math.sin(a) * r, 0))
                for k in range(16):
                    segs.append((ring[k], ring[k + 1], col))
        elif rb.shape == 1:
            hx, hy, hz = abs(sx), abs(sy), abs(sz)
            corners = [pt(x, y, z) for x in (-hx, hx) for y in (-hy, hy) for z in (-hz, hz)]
            edges = [(0, 1), (0, 2), (0, 4), (1, 3), (1, 5), (2, 3),
                     (2, 6), (3, 7), (4, 5), (4, 6), (5, 7), (6, 7)]
            for a, b in edges:
                segs.append((corners[a], corners[b], col))
        else:
            r = abs(sx)
            total = abs(sy)
            hh = max(0.0, total * 0.5 - r)
            for yy in (-hh, hh):
                ring = []
                for k in range(17):
                    a = k * math.pi * 2 / 16
                    ring.append(pt(math.cos(a) * r, yy, math.sin(a) * r))
                for k in range(16):
                    segs.append((ring[k], ring[k + 1], col))
            for k in (0, 4, 8, 12):
                a = k * math.pi * 2 / 16
                x, z = math.cos(a) * r, math.sin(a) * r
                segs.append((pt(x, -hh, z), pt(x, hh, z), col))
        return segs

    def _build_joint_lines(self):
        if self._perf_enabled:
            self._perf_stats["joint_lines"] += 1
        m = self.model
        if not m or not m.joints:
            self._joint_geom = (np.zeros((0, 3), np.float32), np.zeros((0, 3), np.float32))
            return
        segs = []
        for i, j in enumerate(m.joints):
            M = self._joint_current_matrix(i)
            R = M[:3, :3]
            t = M[:3, 3]
            sel = (i == self.selection_index and self.selection_kind == "joint")
            base = np.array([0.95, 0.72, 0.33], np.float32)
            if j.type == 1:
                base = np.array([0.62, 0.72, 0.95], np.float32)
            if sel:
                base = np.array([0.31, 0.72, 1.0], np.float32)
            length = 0.9 if sel else 0.24
            if not sel:
                for ax in range(3):
                    v = np.eye(3, dtype=np.float32)[ax] * length
                    segs.append((tuple(t), tuple(t + R @ v), base))
                continue
            for ax, c in ((0, (0.92, 0.34, 0.34)), (1, (0.4, 0.88, 0.5)), (2, (0.35, 0.6, 1.0))):
                v = np.eye(3, dtype=np.float32)[ax] * length
                col = np.array(c, np.float32) if sel else base
                segs.append((tuple(t), tuple(t + R @ v), col))
                segs.append((tuple(t), tuple(t - R @ v), col))
            box = 0.16
            corners = [(x, y, z) for x in (-1, 1) for y in (-1, 1) for z in (-1, 1)]
            for a in range(8):
                for b in range(a + 1, 8):
                    ca, cb = corners[a], corners[b]
                    if sum(1 for k in range(3) if ca[k] != cb[k]) == 1:
                        pa = tuple(t + R @ (np.array(ca, np.float32) * box))
                        pb = tuple(t + R @ (np.array(cb, np.float32) * box))
                        segs.append((pa, pb, base * 0.8))
        self._joint_geom = _line_geom(segs)

    # ------------------------------------------------------------ 绘制
    def _draw_grid(self, mvp):
        if self._grid is None:
            self._build_grid()
        if not self._grid:
            return
        GL.glUseProgram(self._prog_line)
        GL.glUniformMatrix4fv(self._loc["line"]["uMVP"], 1, GL.GL_FALSE,
                              np.ascontiguousarray(mvp.T, np.float32))
        GL.glUniform1f(self._loc["line"]["uAlpha"], 0.75)
        verts, colors = self._grid
        vbo_p, vbo_c = self._grid_vbo
        GL.glEnableVertexAttribArray(0)
        GL.glBindBuffer(GL.GL_ARRAY_BUFFER, vbo_p)
        GL.glVertexAttribPointer(0, 3, GL.GL_FLOAT, GL.GL_FALSE, 0, None)
        GL.glEnableVertexAttribArray(1)
        GL.glBindBuffer(GL.GL_ARRAY_BUFFER, vbo_c)
        GL.glVertexAttribPointer(1, 3, GL.GL_FLOAT, GL.GL_FALSE, 0, None)
        GL.glLineWidth(1.0)
        # Intel 驱动在 4x MSAA 下画细线会出现彩色噪点（亮色主题尤其明显），
        # 线条这类 1px 图元关闭 MSAA 绘制更稳。
        GL.glDisable(GL.GL_MULTISAMPLE)
        try:
            GL.glDrawArrays(GL.GL_LINES, 0, len(verts))
        finally:
            GL.glEnable(GL.GL_MULTISAMPLE)
        GL.glDisableVertexAttribArray(0)
        GL.glDisableVertexAttribArray(1)
        GL.glBindBuffer(GL.GL_ARRAY_BUFFER, 0)

    def _build_grid(self):
        segs = []
        n = 30
        tint = 0.32 if self._grid_dark else 1.0
        minor = np.array(GRID_MINOR_RGB, np.float32) * tint
        major = np.array(GRID_MAJOR_RGB, np.float32) * tint
        for i in range(-n, n + 1):
            if i == 0:
                continue
            c = major if i % 5 == 0 else minor
            segs.append(((i, 0, -n), (i, 0, n), c))
            segs.append(((-n, 0, i), (n, 0, i), c))
        segs.append(((-n, 0, 0), (n, 0, 0), np.array(GRID_X_RGB, np.float32) * tint))
        segs.append(((0, 0, -n), (0, 0, n), np.array(GRID_Z_RGB, np.float32) * tint))
        verts, colors = _line_geom(segs)
        self._grid = (verts, colors)
        old = getattr(self, "_grid_vbo", None)
        if old:
            GL.glDeleteBuffers(1, [old[0]])
            GL.glDeleteBuffers(1, [old[1]])
        p = GL.glGenBuffers(1)
        c = GL.glGenBuffers(1)
        GL.glBindBuffer(GL.GL_ARRAY_BUFFER, p)
        GL.glBufferData(GL.GL_ARRAY_BUFFER, verts.nbytes, verts, GL.GL_STATIC_DRAW)
        GL.glBindBuffer(GL.GL_ARRAY_BUFFER, c)
        GL.glBufferData(GL.GL_ARRAY_BUFFER, colors.nbytes, colors, GL.GL_STATIC_DRAW)
        GL.glBindBuffer(GL.GL_ARRAY_BUFFER, 0)
        self._grid_vbo = (p, c)

    # ------------------------------------------------------------ 贴图
    def _decode_texture(self, path):
        """解码贴图为 (宽, 高, RGBA 字节)；失败返回 None。只读文件，可在子线程调用。"""
        if not path or not os.path.exists(path):
            return None
        reader = QImageReader(path)
        reader.setAutoTransform(True)
        img = reader.read()
        if img.isNull():
            return None
        img = img.convertToFormat(QImage.Format_RGBA8888)
        return (img.width(), img.height(),
                img.constBits().asstring(img.byteCount()))

    def _missing_texture_pixels(self):
        """缺失贴图的 64x64 棋盘占位图。"""
        img = QImage(64, 64, QImage.Format_RGBA8888)
        img.fill(QColor(TEX_MISS_BG))
        painter = QPainter(img)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(TEX_MISS_CELL))
        for y in range(0, 64, 16):
            for x in range(0, 64, 16):
                if (x // 16 + y // 16) % 2 == 0:
                    painter.drawRect(x, y, 16, 16)
        painter.end()
        return (64, 64, img.constBits().asstring(img.byteCount()))

    def _prewarm_textures(self):
        """后台线程预解码贴图，避免首次绘制时在主线程串行解码（真机 12 张约 290 ms）。"""
        m = self.model
        if not m or not m.textures:
            return
        paths = []
        for index in range(len(m.textures)):
            path = m.resolve_texture(index)
            if path and path not in self._tex_pixels and path not in paths:
                paths.append(path)
        if not paths:
            return

        def work():
            for path in paths:
                try:
                    data = self._decode_texture(path)
                except Exception:
                    data = None
                with self._tex_lock:
                    self._tex_pixels[path] = data

        thread = threading.Thread(target=work, name="tex-prewarm", daemon=True)
        self._tex_warm = thread
        thread.start()

    def release_gpu_resources(self):
        """释放本视口持有的 GL 缓冲与纹理（关窗时调用）。"""
        if not self.isValid():
            return
        had = QOpenGLContext.currentContext() is not None
        if not had:
            self.makeCurrent()
        try:
            buffers = list(self._mesh_ids.values())
            for pair in self._vbo_lines.values():
                buffers.extend(pair)
            grid = getattr(self, "_grid_vbo", None)
            if grid:
                buffers.extend(grid)
            if buffers:
                GL.glDeleteBuffers(len(buffers), np.asarray(buffers, dtype=np.uint32))
            textures = [v for v in self._tex_cache.values() if isinstance(v, int)]
            if textures:
                GL.glDeleteTextures(np.asarray(textures, dtype=np.uint32))
        except Exception:
            pass
        finally:
            self._mesh_ids.clear()
            self._vbo_lines.clear()
            self._grid_vbo = None
            self._tex_cache.clear()
            if not had:
                self.doneCurrent()

    def _texture(self, index, sphere=False):
        m = self.model
        path = m.resolve_texture(index) if (m and 0 <= index < len(m.textures)) else ""
        key = (path, sphere)
        if key in self._tex_cache:
            return self._tex_cache[key]
        if path in self._tex_pixels:
            data = self._tex_pixels[path]
        else:
            # 预热线程还没解到这张时退回同步解码，并把结果留作下次复用
            data = self._decode_texture(path)
            self._tex_pixels[path] = data
        if data is None:
            data = self._missing_texture_pixels()
        width, height, pixels = data
        tex = GL.glGenTextures(1)
        GL.glBindTexture(GL.GL_TEXTURE_2D, tex)
        GL.glPixelStorei(GL.GL_UNPACK_ALIGNMENT, 1)
        GL.glTexImage2D(GL.GL_TEXTURE_2D, 0, GL.GL_RGBA, width, height, 0,
                        GL.GL_RGBA, GL.GL_UNSIGNED_BYTE, pixels)
        GL.glTexParameteri(GL.GL_TEXTURE_2D, GL.GL_TEXTURE_MIN_FILTER, GL.GL_LINEAR_MIPMAP_LINEAR)
        GL.glTexParameteri(GL.GL_TEXTURE_2D, GL.GL_TEXTURE_MAG_FILTER, GL.GL_LINEAR)
        GL.glTexParameteri(GL.GL_TEXTURE_2D, GL.GL_TEXTURE_WRAP_S, GL.GL_REPEAT)
        GL.glTexParameteri(GL.GL_TEXTURE_2D, GL.GL_TEXTURE_WRAP_T, GL.GL_REPEAT)
        GL.glGenerateMipmap(GL.GL_TEXTURE_2D)
        GL.glBindTexture(GL.GL_TEXTURE_2D, 0)
        self._tex_cache[key] = tex
        return tex

    def _draw_mesh(self, mvp):
        mesh = self._mesh
        m = self.model
        L = self._loc["mesh"]
        GL.glUseProgram(self._prog_mesh)
        GL.glEnable(GL.GL_DEPTH_TEST)
        GL.glDepthFunc(GL.GL_LESS)
        GL.glDepthMask(GL.GL_TRUE)
        GL.glUniformMatrix4fv(L["uMVP"], 1, GL.GL_FALSE,
                              np.ascontiguousarray(mvp.T, np.float32))
        GL.glUniform3f(L["uLightDir"], 0.36, 0.72, 0.58)
        GL.glUniform1f(L["uToon"], 1.0 if self.toon else 0.0)
        GL.glUniform1i(L["uOutline"], 0)
        GL.glUniform1f(L["uExpand"], 0.0)

        GL.glEnableVertexAttribArray(0)
        GL.glBindBuffer(GL.GL_ARRAY_BUFFER, mesh["pos"])
        GL.glVertexAttribPointer(0, 3, GL.GL_FLOAT, GL.GL_FALSE, 0, None)
        GL.glEnableVertexAttribArray(1)
        GL.glBindBuffer(GL.GL_ARRAY_BUFFER, mesh["nrm"])
        GL.glVertexAttribPointer(1, 3, GL.GL_FLOAT, GL.GL_FALSE, 0, None)
        GL.glEnableVertexAttribArray(2)
        GL.glBindBuffer(GL.GL_ARRAY_BUFFER, mesh["uv"])
        GL.glVertexAttribPointer(2, 2, GL.GL_FLOAT, GL.GL_FALSE, 0, None)
        GL.glBindBuffer(GL.GL_ELEMENT_ARRAY_BUFFER, mesh["idx"])

        overrides = material_morph_colors(m, self.morph_weights)
        mat_by_id = {id(mt): i for i, mt in enumerate(m.materials)}
        ranges = mesh["ranges"]
        # 与 MMD 一致：按材质顺序单遍绘制，混合常开、深度始终写入。
        # 按贴图 alpha 整体判定「透明材质」并关闭深度写入会让贴图含少量透明像素
        # 的皮肤/服装材质互相穿透，出现大片浅色斑块。
        items = [(mt, off, count) for mt, off, count in ranges if count > 0]

        def draw_item(mt, off, count):
            if mt is None:
                mb = float(self.model_brightness)
                GL.glDisable(GL.GL_TEXTURE_2D)
                GL.glUniform1i(L["uUseTex"], 0)
                GL.glUniform4f(L["uDiffuse"], mb, mb, mb, 1)
                GL.glUniform3f(L["uAmbient"], 0.55 * mb, 0.56 * mb, 0.6 * mb)
                GL.glUniform3f(L["uSpecular"], 0, 0, 0)
                GL.glUniform1f(L["uSpecCoef"], 0)
                GL.glUniform1i(L["uUseSphere"], 0)
                GL.glUniform1f(L["uToon"], 0.0)
                GL.glDisable(GL.GL_CULL_FACE)
                GL.glDrawElements(GL.GL_TRIANGLES, count, GL.GL_UNSIGNED_INT,
                                  ctypes.c_void_p(off))
                return
            diff = list(mt.diffuse)
            amb = list(mt.ambient)
            ov = overrides.get(mat_by_id.get(id(mt), -1))
            if ov is not None:
                diff = (np.array(diff[:3]) * ov["mul"][:3]).tolist() + [diff[3] * ov["mul"][3]]
                amb = (np.array(amb[:3]) + ov["add"][:3]).tolist()
            mb = float(self.model_brightness)
            if mb != 1.0:
                diff = [float(v) * mb for v in list(diff)[:3]] + list(diff)[3:]
                amb = [float(v) * mb for v in list(amb)[:3]] + list(amb)[3:]
            GL.glUniform4f(L["uDiffuse"],
                           *([float(v) for v in list(diff)[:4]] + [1.0])[:4])
            GL.glUniform3f(L["uAmbient"],
                           *([float(v) for v in list(amb)[:3]] + [0.0, 0.0])[:3])
            GL.glUniform3f(L["uSpecular"],
                           *([float(v) for v in list(mt.specular)[:3]] + [0.0, 0.0])[:3])
            GL.glUniform1f(L["uSpecCoef"], float(mt.specular_coef))
            # 未指定 toon 的材质在 MMD 中按平滑光照着色，只有带 toon 的材质才走阶梯色阶
            has_toon = mt.toon_shared == 1 or mt.toon >= 0
            GL.glUniform1f(L["uToon"], 1.0 if (self.toon and has_toon) else 0.0)
            use_tex = 1 if (self.show_texture and mt.texture >= 0) else 0
            GL.glUniform1i(L["uUseTex"], use_tex)
            if use_tex:
                GL.glActiveTexture(GL.GL_TEXTURE0)
                GL.glBindTexture(GL.GL_TEXTURE_2D, self._texture(mt.texture))
                GL.glUniform1i(L["uTex"], 0)
            use_sph = 1 if (self.show_texture and mt.sphere >= 0 and mt.sphere_mode > 0) else 0
            GL.glUniform1i(L["uUseSphere"], use_sph)
            if use_sph:
                GL.glActiveTexture(GL.GL_TEXTURE1)
                GL.glBindTexture(GL.GL_TEXTURE_2D, self._texture(mt.sphere, True))
                GL.glUniform1i(L["uSphereTex"], 1)
                GL.glUniform1i(L["uSphereMode"], int(mt.sphere_mode))
            if mt.draw_flags & MF_DOUBLE_SIDED:
                GL.glDisable(GL.GL_CULL_FACE)
            else:
                GL.glEnable(GL.GL_CULL_FACE)
                GL.glCullFace(GL.GL_BACK)
            GL.glDepthMask(GL.GL_TRUE)
            GL.glDrawElements(GL.GL_TRIANGLES, count, GL.GL_UNSIGNED_INT,
                              ctypes.c_void_p(off))
            if use_sph:
                GL.glActiveTexture(GL.GL_TEXTURE1)
                GL.glBindTexture(GL.GL_TEXTURE_2D, 0)
            if use_tex:
                GL.glActiveTexture(GL.GL_TEXTURE0)
                GL.glBindTexture(GL.GL_TEXTURE_2D, 0)

        GL.glEnable(GL.GL_BLEND)
        GL.glBlendFunc(GL.GL_SRC_ALPHA, GL.GL_ONE_MINUS_SRC_ALPHA)
        for item in items:
            draw_item(*item)
        GL.glDisable(GL.GL_BLEND)

        if self.outline:
            self._draw_outline(items)

        if self.wireframe:
            GL.glDisable(GL.GL_TEXTURE_2D)
            GL.glUniform1i(L["uUseTex"], 0)
            GL.glUniform1i(L["uUseSphere"], 0)
            GL.glUniform4f(L["uDiffuse"], 0.35, 0.55, 0.8, 1.0)
            GL.glUniform3f(L["uAmbient"], 1.0, 1.0, 1.0)
            GL.glUniform3f(L["uSpecular"], 0, 0, 0)
            GL.glUniform1f(L["uSpecCoef"], 0)
            GL.glDisable(GL.GL_CULL_FACE)
            GL.glPolygonMode(GL.GL_FRONT_AND_BACK, GL.GL_LINE)
            GL.glLineWidth(1.0)
            GL.glDrawElements(GL.GL_TRIANGLES, mesh["count"], GL.GL_UNSIGNED_INT, None)
            GL.glPolygonMode(GL.GL_FRONT_AND_BACK, GL.GL_FILL)

        GL.glDisableVertexAttribArray(0)
        GL.glDisableVertexAttribArray(1)
        GL.glDisableVertexAttribArray(2)
        GL.glBindBuffer(GL.GL_ARRAY_BUFFER, 0)
        GL.glBindBuffer(GL.GL_ELEMENT_ARRAY_BUFFER, 0)

    def _draw_outline(self, items):
        """倒置壳描边。

        用模板缓冲记录当前材质自身覆盖的区域，只在材质轮廓外侧绘制外壳，
        避免双面/开放薄壳（脸皮、眼部贴片等）被外壳整面填充成边线色。
        """
        L = self._loc["mesh"]
        GL.glUniform1i(L["uOutline"], 1)
        GL.glUniform1i(L["uUseTex"], 0)
        GL.glUniform1i(L["uUseSphere"], 0)
        GL.glUniform1f(L["uExpand"], 0.0)
        GL.glEnable(GL.GL_CULL_FACE)
        GL.glCullFace(GL.GL_FRONT)
        GL.glDepthMask(GL.GL_FALSE)
        GL.glEnable(GL.GL_BLEND)
        stencil = self._stencil_bits > 0
        if stencil:
            GL.glEnable(GL.GL_STENCIL_TEST)
            GL.glStencilMask(0xFF)
        for mt, off, count in items:
            if mt is None or not (mt.draw_flags & MF_EDGE) or mt.edge_size <= 0:
                continue
            if stencil:
                # 只写模板、不写颜色：材质已绘制，深度相等即视为覆盖
                GL.glClear(GL.GL_STENCIL_BUFFER_BIT)
                GL.glDisable(GL.GL_CULL_FACE)
                GL.glColorMask(GL.GL_FALSE, GL.GL_FALSE, GL.GL_FALSE, GL.GL_FALSE)
                GL.glDepthFunc(GL.GL_LEQUAL)
                GL.glStencilFunc(GL.GL_ALWAYS, 1, 0xFF)
                GL.glStencilOp(GL.GL_KEEP, GL.GL_KEEP, GL.GL_REPLACE)
                GL.glUniform1i(L["uOutline"], 0)
                GL.glDrawElements(GL.GL_TRIANGLES, count, GL.GL_UNSIGNED_INT,
                                  ctypes.c_void_p(off))
                GL.glColorMask(GL.GL_TRUE, GL.GL_TRUE, GL.GL_TRUE, GL.GL_TRUE)
                GL.glDepthFunc(GL.GL_LESS)
                GL.glStencilFunc(GL.GL_NOTEQUAL, 1, 0xFF)
                GL.glStencilOp(GL.GL_KEEP, GL.GL_KEEP, GL.GL_KEEP)
                GL.glEnable(GL.GL_CULL_FACE)
                GL.glCullFace(GL.GL_FRONT)
                GL.glUniform1i(L["uOutline"], 1)
            ec = [float(v) for v in list(mt.edge_color)[:4]] + [0.0, 0.0, 0.0, 1.0]
            GL.glUniform4f(L["uOutlineColor"], ec[0], ec[1], ec[2],
                           min(1.0, ec[3] * 0.9))
            GL.glUniform1f(L["uExpand"], 0.0015 + float(mt.edge_size) * 0.0006)
            GL.glDrawElements(GL.GL_TRIANGLES, count, GL.GL_UNSIGNED_INT,
                              ctypes.c_void_p(off))
        GL.glDisable(GL.GL_STENCIL_TEST)
        GL.glDepthMask(GL.GL_TRUE)
        GL.glDisable(GL.GL_BLEND)
        GL.glCullFace(GL.GL_BACK)
        GL.glUniform1i(L["uOutline"], 0)
        GL.glUniform1f(L["uExpand"], 0.0)

    def _draw_lines(self, name, mvp, alpha, width=1.5):
        count = self._line_counts[name]
        if not count:
            return
        L = self._loc["line"]
        GL.glUseProgram(self._prog_line)
        GL.glUniformMatrix4fv(L["uMVP"], 1, GL.GL_FALSE,
                              np.ascontiguousarray(mvp.T, np.float32))
        GL.glUniform1f(L["uAlpha"], alpha)
        GL.glEnableVertexAttribArray(0)
        vbo_pos, vbo_color = self._vbo_lines[name]
        GL.glBindBuffer(GL.GL_ARRAY_BUFFER, vbo_pos)
        GL.glVertexAttribPointer(0, 3, GL.GL_FLOAT, GL.GL_FALSE, 0, None)
        GL.glEnableVertexAttribArray(1)
        GL.glBindBuffer(GL.GL_ARRAY_BUFFER, vbo_color)
        GL.glVertexAttribPointer(1, 3, GL.GL_FLOAT, GL.GL_FALSE, 0, None)
        GL.glLineWidth(width)
        GL.glDisable(GL.GL_MULTISAMPLE)   # 同上：避免 MSAA 下的细线彩色噪点
        try:
            GL.glDrawArrays(GL.GL_LINES, 0, count)
        finally:
            GL.glEnable(GL.GL_MULTISAMPLE)
        GL.glDisableVertexAttribArray(0)
        GL.glDisableVertexAttribArray(1)
        GL.glBindBuffer(GL.GL_ARRAY_BUFFER, 0)

    def _upload_line_geom(self, name, geom):
        verts, colors = geom
        self._ensure_line_vbos()
        self._line_counts[name] = len(verts)
        if not len(verts):
            return
        for index, data in enumerate((verts, colors)):
            data = np.ascontiguousarray(data, dtype=np.float32)
            vbo = self._vbo_lines[name][index]
            GL.glBindBuffer(GL.GL_ARRAY_BUFFER, vbo)
            if self._line_sizes[name][index] == data.nbytes:
                GL.glBufferSubData(GL.GL_ARRAY_BUFFER, 0, data.nbytes, data)
            else:
                usage = GL.GL_DYNAMIC_DRAW if name == "bone" else GL.GL_STATIC_DRAW
                GL.glBufferData(GL.GL_ARRAY_BUFFER, data.nbytes, data, usage)
                self._line_sizes[name][index] = data.nbytes
            if self._perf_enabled:
                self._perf_stats["line_upload_bytes"] += data.nbytes
        GL.glBindBuffer(GL.GL_ARRAY_BUFFER, 0)
        if self._perf_enabled:
            self._perf_stats["line_uploads"] += 1

    def _ensure_line_vbos(self):
        for name in ("bone", "rigid", "joint"):
            if name not in self._vbo_lines:
                self._vbo_lines[name] = (
                    GL.glGenBuffers(1), GL.glGenBuffers(1)
                )

    def _paint_hud_done(self):
        """GL 场景绘制结束后刷新文字层（文字由子控件用 raster 引擎绘制）。"""
        self._hud.update()

    # ------------------------------------------------------------ HUD
    def _paint_hud(self, p):
        w, h = self.width(), self.height()
        # 背景提亮到浅色时文字翻深，否则白字压在浅底上看不见
        if self._grid_needs_dark():
            c_title, c_dim, c_faint = (QColor("#1c222b"), QColor("#3c475a"),
                                       QColor("#5a6474"))
        else:
            c_title, c_dim, c_faint = (QColor(TEXT), QColor(TEXT_DIM),
                                       QColor(TEXT_FAINT))
        # 顶部信息
        if self.model:
            name = self.model.name or "未命名模型"
            p.setFont(ui_font(11, QFont.DemiBold))
            p.setPen(c_title)
            p.drawText(18, 26, name)
            p.setFont(ui_font(8.2))
            p.setPen(c_faint)
            stats = "顶点 %s · 面 %s · 骨骼 %s · 材质 %s · 形态 %s" % (
                f"{self.model.n_vertices:,}", f"{self.model.n_faces:,}",
                self.model.n_bones, len(self.model.materials), self.model.n_morphs)
            p.drawText(18, 43, stats)
        # 模式徽标：单一视图，只显示物理开关状态
        mode_text = "物理演算" if self.physics.enabled else "摆姿"
        p.setFont(ui_font(8.5, QFont.DemiBold))
        fm = p.fontMetrics()
        tw = fm.horizontalAdvance(mode_text) + 20
        badge = QRectF(w - tw - 18, 16, tw, 22)
        p.setPen(QPen(QColor(ACCENT), 1))
        fill = QColor(ACCENT)
        fill.setAlpha(32)
        p.setBrush(fill)
        p.drawRoundedRect(badge, 11, 11)
        p.setPen(QColor(ACCENT))
        p.drawText(badge, Qt.AlignCenter, mode_text)
        # 选中信息
        info = self._selection_text()
        if info:
            p.setFont(ui_font(8.6))
            p.setPen(c_dim)
            p.drawText(18, 63, info)
        # 右下角坐标轴
        self._draw_axis_gizmo(p, w - 58, h - 58, 34)
        # 底部提示
        p.setFont(ui_font(8.2))
        p.setPen(c_faint)
        hint = "左键拖动骨骼 位移 · 右键拖动骨骼 旋转 · 中键拖动 旋转视角（Shift 平移）· 滚轮缩放 · 双击选中 · F 聚焦 · R 重置"
        p.drawText(18, h - 16, hint)
        # 空闲不重绘时没有真实帧率可言，显示"空闲"而不是误导性的 0/1 FPS
        fps_txt = "空闲" if self._fps <= 0.0 else "%.0f FPS" % self._fps
        if self.physics.enabled:
            fps_txt = "物理演算中 · " + fps_txt
        p.setFont(mono_font(8.2))
        p.setPen(c_faint)
        p.drawText(QRectF(w - 260, h - 28, 240, 16), Qt.AlignRight | Qt.AlignVCenter, fps_txt)
        self._draw_hover_tip(p, c_title)

    def _draw_hover_tip(self, p, c_title):
        """光标下对象的浮动名称牌（骨骼拾取太难看清时靠它确认目标）。"""
        if not self._hover or self._dragging or self._hover_pos is None:
            return
        text = self._hover_text()
        if not text:
            return
        fm = QFontMetrics(ui_font(8.6))
        tw = fm.horizontalAdvance(text)
        x = min(max(6, self._hover_pos.x() + 14), self.width() - tw - 16)
        y = min(max(6, self._hover_pos.y() - 26), self.height() - 24)
        rect = QRectF(x, y, tw + 12, 19)
        p.setPen(Qt.NoPen)
        bg = QColor(28, 34, 43, 225) if not self._grid_needs_dark() else QColor(250, 251, 253, 235)
        p.setBrush(bg)
        p.drawRoundedRect(rect, 4, 4)
        p.setFont(ui_font(8.6))
        p.setPen(c_title)
        p.drawText(rect.adjusted(6, 0, -6, 0), Qt.AlignVCenter | Qt.AlignLeft, text)

    def _hover_text(self):
        m = self.model
        if not m or not self._hover:
            return ""
        kind, _, idx = self._hover.partition(":")
        try:
            i = int(idx)
        except ValueError:
            return ""
        if kind == "bone" and 0 <= i < len(m.bones):
            b = m.bones[i]
            zh = gl_names.bone_zh(b.name)
            return "#%d %s%s" % (i, b.name, ("  " + zh) if zh and zh != b.name else "")
        if kind == "rigid" and 0 <= i < len(m.rigid):
            return "#%d %s" % (i, m.rigid[i].name)
        if kind == "joint" and 0 <= i < len(m.joints):
            return "#%d %s" % (i, m.joints[i].name)
        return ""

    def _selection_text(self):
        if not self.model:
            return ""
        if self.selection_kind == "bone" and 0 <= self.selection_index < len(self.model.bones):
            b = self.model.bones[self.selection_index]
            hint = gl_names.bone_zh(b.name)
            return "骨骼  #%d  %s%s" % (self.selection_index, b.name,
                                        ("  ·  " + hint) if hint and hint != b.name else "")
        if self.selection_kind == "rigid" and 0 <= self.selection_index < len(self.model.rigid):
            rb = self.model.rigid[self.selection_index]
            return "刚体  #%d  %s  ·  %s" % (self.selection_index, rb.name,
                                            SHAPE_NAMES.get(rb.shape, "?"))
        if self.selection_kind == "joint" and 0 <= self.selection_index < len(self.model.joints):
            j = self.model.joints[self.selection_index]
            return "关节  #%d  %s" % (self.selection_index, j.name)
        return ""

    def _draw_axis_gizmo(self, p, cx, cy, r):
        cam = self.camera
        yaw, pitch = cam.yaw, cam.pitch
        # 世界轴在屏幕上的方向（近似正交投影）
        import math as _m
        axes = [
            ("X", np.array([1.0, 0, 0]), QColor("#ef6b6b")),
            ("Y", np.array([0, 1.0, 0]), QColor("#5ec98a")),
            ("Z", np.array([0, 0, 1.0]), QColor("#4f9dff")),
        ]
        for name, v, col in axes:
            sx = _m.cos(yaw) * v[0] + _m.sin(yaw) * v[2]
            sy = (-_m.sin(pitch) * _m.sin(yaw) * v[0] + _m.cos(pitch) * v[1]
                  - _m.sin(pitch) * _m.cos(yaw) * v[2])
            ex, ey = cx + sx * r, cy - sy * r
            p.setPen(QPen(col, 1.6))
            p.drawLine(QPoint(cx, cy), QPoint(int(ex), int(ey)))
            p.setFont(ui_font(7.6, QFont.DemiBold))
            p.drawText(int(ex) - 4, int(ey) + (4 if sy >= 0 else -2), name)

    # ------------------------------------------------------------ 交互
    def _discard_pending_pose_updates(self):
        self._pose_flush_timer.stop()
        self._pending_pose_deltas.clear()

    def _flush_pose_updates(self):
        if not self._pending_pose_deltas:
            self._pose_flush_timer.stop()
            return
        pending = self._pending_pose_deltas
        self._pending_pose_deltas = []
        self._pose_flush_timer.stop()
        if not self.pose:
            return
        changed_bones = set()
        for mode, bone, dx, dy in pending:
            if self.bone_drag_block(bone, mode):
                # 拖动途中标志被改（或撤销恢复到旧标志）：丢弃这条增量
                continue
            changed_bones.add(bone)
            if mode == "rotate":
                self.pose.rotate_world(bone, (0.0, 1.0, 0.0), dx * 0.012)
                self.pose.rotate_world(bone, tuple(self.camera.right()), dy * 0.012)
            elif mode == "move":
                scale = self.camera.distance * 0.0016
                delta = (self.camera.right() * dx * scale
                         - self.camera.up_vec() * dy * scale)
                self.pose.translate_world(bone, delta)
        self.pose.world_update()
        active = set()
        for bone in changed_bones:
            active.update(active_ik_indices(self.pose, bone))
        self._solve_ik(max_loops=3, only=active or None)
        if active:
            changed = set(changed_bones)
            for index in active:
                changed.add(index)
                changed.update(link.bone for link in self.model.bones[index].ik.links)
            self._mark_incremental_skin_dirty(changed)
        else:
            self._mark_full_skin_dirty()
        self._pose_dirty = True
        self.update()

    def _bone_flags(self, index: int) -> int:
        m = self.model
        if not m or not (0 <= index < len(m.bones)):
            return 0
        return int(m.bones[index].flags)

    def bone_drag_block(self, index: int, mode: str) -> str:
        """返回阻止拖动骨骼的原因（空串表示可拖动）。

        对应 PMX 骨骼标志：可操作（否则视口里不能选）、可移动、可旋转。
        """
        flags = self._bone_flags(index)
        if not (flags & BF_ENABLED):
            return "不可操作"
        if mode == "move" and not (flags & BF_TRANSLATABLE):
            return "不可移动"
        if mode == "rotate" and not (flags & BF_ROTATABLE):
            return "不可旋转"
        return ""

    def _begin_bone_drag(self, index: int, mode: str):
        """按下骨骼：先选中，再按左键/右键进入位移/旋转拖动。"""
        old_kind = self.selection_kind
        self.selection_kind, self.selection_index = "bone", index
        self.boneClicked.emit(index)
        self._mark_selection_geometry_dirty(old_kind, "bone")
        self.update()
        # 撤销记录推迟到真正拖动时：单击不拖动不该压入撤销栈
        self._edit_pushed = False
        self._pose_moved = False
        self._dragging = None
        self._armed_bone = index
        blocked = self.bone_drag_block(index, mode)
        if blocked:
            # 选中仍然生效（方便看是哪个骨骼被挡住），只是不进入拖动
            self._drag_bone = -1
            name = ""
            if self.model and 0 <= index < len(self.model.bones):
                name = self.model.bones[index].name or ""
            self.statusChanged.emit(
                "「%s」%s · 左键拖动位移 / 右键拖动旋转" % (name or "骨骼", blocked))
            self.setCursor(Qt.ArrowCursor)
            return
        self._drag_bone = index
        self._dragging = mode
        self._last_mouse = self._press_pos
        self.setCursor(Qt.SizeAllCursor if mode == "move" else Qt.CrossCursor)

    def mousePressEvent(self, e):
        self.setFocus()
        self._press_pos = e.pos()
        if e.button() == Qt.MiddleButton:
            self._dragging = "pan" if (e.modifiers() & Qt.ShiftModifier) else "orbit"
            self._last_mouse = e.pos()
            self.setCursor(Qt.ClosedHandCursor)
            return
        if e.button() == Qt.LeftButton:
            kind, index = self.pick(e.x(), e.y(),
                                    cycle=bool(e.modifiers() & Qt.AltModifier))
            self._pending_pick = (kind, index)
            if kind == "bone":
                # 左键 = 位移（IK 控制器、Shift 修饰同样走位移）
                self._begin_bone_drag(index, "move")
                return
            self._dragging = "select"
            self._last_mouse = e.pos()
            self.setCursor(Qt.PointingHandCursor if kind else Qt.ArrowCursor)
            return
        if e.button() == Qt.RightButton:
            kind, index = self.pick(e.x(), e.y(),
                                    cycle=bool(e.modifiers() & Qt.AltModifier))
            if kind == "bone":
                # 右键 = 旋转；右键落在空白处仍是视角平移
                self._pending_pick = (kind, index)
                self._begin_bone_drag(index, "rotate")
                return
            self._dragging = "pan"
            self._last_mouse = e.pos()
            self.setCursor(Qt.ClosedHandCursor)
            return
        super().mousePressEvent(e)

    def mouseDoubleClickEvent(self, e):
        """双击选中骨骼：之后左键拖动位移、右键拖动旋转。"""
        if e.button() == Qt.LeftButton:
            kind, index = self.pick(e.x(), e.y(),
                                    cycle=bool(e.modifiers() & Qt.AltModifier))
            if kind == "bone":
                old_kind = self.selection_kind
                self.selection_kind, self.selection_index = "bone", index
                self.boneClicked.emit(index)
                self._mark_selection_geometry_dirty(old_kind, "bone")
                self._armed_bone = index
                self._dragging = None
                self.setCursor(Qt.ArrowCursor)
                self.update()
                name = ""
                if self.model and 0 <= index < len(self.model.bones):
                    name = self.model.bones[index].name or ""
                self.statusChanged.emit(
                    "已选中「%s」：左键拖动位移 · 右键拖动旋转" % (name or "骨骼"))
                return
        super().mouseDoubleClickEvent(e)

    def mouseMoveEvent(self, e):
        if self._dragging == "select" and (e.buttons() & Qt.LeftButton):
            # 左键拖动改为旋转视角；位移不超过阈值仍算单击选择
            if (e.pos() - self._press_pos).manhattanLength() <= 3:
                return
            self._dragging = "orbit"
            self._last_mouse = self._press_pos
            self.setCursor(Qt.ClosedHandCursor)
        if self._dragging in ("orbit", "pan"):
            d = e.pos() - self._last_mouse
            self._last_mouse = e.pos()
            if self._dragging == "orbit":
                self.camera.yaw -= d.x() * 0.0075
                self.camera.pitch = max(-1.52, min(1.52, self.camera.pitch + d.y() * 0.0065))
            else:
                k = self.camera.distance * 0.0018
                self.camera.target -= self.camera.right() * d.x() * k
                self.camera.target += self.camera.up_vec() * d.y() * k
            self.update()
            return
        if self._dragging in ("rotate", "move") and self._drag_bone >= 0 and self.pose:
            d = e.pos() - self._last_mouse
            self._last_mouse = e.pos()
            if d.x() or d.y():
                if not self._edit_pushed:
                    self._edit_pushed = True
                    self.editStarted.emit(
                        "旋转骨骼" if self._dragging == "rotate" else "移动骨骼")
                self._pose_moved = True
                self._pending_pose_deltas.append(
                    (self._dragging, self._drag_bone, d.x(), d.y()))
                if not self._pose_flush_timer.isActive():
                    self._pose_flush_timer.start()
            return
        # 悬停高亮：拾取要遍历全部骨骼，按时间节流避免拖动鼠标时爆 CPU
        if e.buttons() == Qt.NoButton:
            now = time.perf_counter()
            if now - self._hover_tick < 0.05:
                return
            self._hover_tick = now
            kind, index = self.pick(e.x(), e.y(),
                                    cycle=bool(e.modifiers() & Qt.AltModifier))
            hover = "%s:%s" % (kind, index) if kind else ""
            self._hover_pos = e.pos()
            self.setCursor(Qt.PointingHandCursor if kind else Qt.ArrowCursor)
            if hover != self._hover:
                self._hover = hover
                self.update()

    def mouseReleaseEvent(self, e):
        was = self._dragging
        if was in ("rotate", "move") and self.pose:
            d = e.pos() - self._last_mouse
            if d.x() or d.y():
                self._pending_pose_deltas.append(
                    (was, self._drag_bone, d.x(), d.y()))
                self._last_mouse = e.pos()
            self._flush_pose_updates()
        self._dragging = None
        self.setCursor(Qt.ArrowCursor)
        if was == "select":
            d = e.pos() - self._press_pos
            if d.manhattanLength() <= 3:
                kind, index = self._pending_pick
                if kind:
                    old_kind = self.selection_kind
                    self.selection_kind, self.selection_index = kind, index
                    if kind == "bone":
                        self.boneClicked.emit(index)
                    elif kind == "rigid":
                        self.rigidClicked.emit(index)
                    elif kind == "joint":
                        self.jointClicked.emit(index)
                    self._mark_selection_geometry_dirty(old_kind, kind)
                    self.update()
                else:
                    # 点击空白处取消选择
                    old_kind = self.selection_kind
                    self.selection_kind, self.selection_index = "", -1
                    self._mark_selection_geometry_dirty(old_kind, "")
                    self.selectionCleared.emit()
                    self.update()
        self._pending_pick = ("", -1)
        if was in ("rotate", "move") and self.pose and self._pose_moved:
            # 松手时用完整迭代次数再收敛一次，保证姿态精确
            self.pose.world_update()
            before_rot = self.pose.base_rot.copy()
            before_trans = self.pose.base_trans.copy()
            self._solve_ik()
            changed = np.flatnonzero(
                np.any(before_rot != self.pose.base_rot, axis=1)
                | np.any(before_trans != self.pose.base_trans, axis=1)
            )
            if changed.size:
                self._mark_incremental_skin_dirty(changed)
            self._pose_dirty = True
            self.update()
            self.statusChanged.emit("姿态已更新")
        self._pose_moved = False
        self._edit_pushed = False
        super().mouseReleaseEvent(e)

    def wheelEvent(self, e):
        delta = e.angleDelta().y() / 120.0
        self.camera.distance = max(0.6, min(2000.0, self.camera.distance * (0.88 ** delta)))
        self.update()

    def _is_ik_bone(self, index: int) -> bool:
        m = self.model
        if not m or not (0 <= index < len(m.bones)):
            return False
        b = m.bones[index]
        return bool(b.flags & 0x0020) and b.ik is not None

    def _pick_candidates(self, x, y):
        """收集光标附近的候选对象：(score, depth, kind, index)。

        score 越小越可能是用户想点的目标；depth 是候选点到相机的距离，
        供 Alt 循环选择时按"由近到远"排序（密集骨骼区域用得上）。
        """
        m = self.model
        if not m:
            return []
        eye = self.camera.eye()
        out = []

        def depth_of(p):
            return float(np.linalg.norm(np.array(p, np.float64) - eye))

        # 单一视图：骨骼手柄优先（摆姿是主操作），没有命中骨骼时才让
        # 显示中的刚体/关节参与拾取；Alt 循环在同类候选内轮换。
        bones = []
        others = []
        if self.show_rigid:
            for i, rb in enumerate(m.rigid):
                p = self.camera.project(rb.pos, self.width(), self.height())
                if not p:
                    continue
                d = math.hypot(p[0] - x, p[1] - y)
                if d < 13.0:
                    others.append((d, depth_of(rb.pos), "rigid", i))
        if self.show_joints:
            for i, j in enumerate(m.joints):
                p = self.camera.project(j.pos, self.width(), self.height())
                if not p:
                    continue
                d = math.hypot(p[0] - x, p[1] - y)
                if d < 13.0:
                    others.append((d, depth_of(j.pos), "joint", i))
        world = self.pose.world() if self.pose else None
        if world is None:
            return others
        out = bones
        for i, b in enumerate(m.bones):
            # 骨骼标志：不可见 / 不可操作的骨骼不参与视口拾取
            # （不可操作的骨骼仍可在骨骼列表里选中查看，但视口里点不到）
            if not (b.flags & BF_VISIBLE) or not (b.flags & BF_ENABLED):
                continue
            head = world[i][:3, 3]
            if b.flags & 0x0001 and 0 <= b.tail_bone < len(m.bones):
                tail = world[b.tail_bone][:3, 3]
            else:
                tail = head + np.array(b.tail_offset, dtype=np.float32)
            ph = self.camera.project(head, self.width(), self.height())
            pt = self.camera.project(tail, self.width(), self.height())
            if not ph:
                continue
            if pt:
                d = _point_segment_dist(x, y, ph, pt)
                # 命中半径按投影长度缩放：远处骨骼投影只有几个像素，
                # 固定 13px 会把整片密集区域都算成候选；近处长骨骼则放宽。
                seg_px = math.hypot(pt[0] - ph[0], pt[1] - ph[1])
                radius = min(16.0, max(6.0, 0.4 * seg_px))
            else:
                d = math.hypot(ph[0] - x, ph[1] - y) + 4
                radius = 13.0
            # 骨骼端点常常与其他骨骼线段重合（例如足 IK 与膝-踝段），
            # 命中端点与 IK 控制器时给更高优先级，否则 IK 控制器无法点选。
            dh = math.hypot(ph[0] - x, ph[1] - y)
            if dh < max(6.0, radius * 0.7):
                d = min(d, dh * 0.4)
            if b.flags & 0x0020:
                d -= 5.0
            if d < radius:
                out.append((d, depth_of(head), "bone", i))
        return out if out else others

    def pick(self, x, y, cycle=False):
        """返回光标下最可能的对象；cycle=True 时按由近到远轮换候选。"""
        cands = self._pick_candidates(x, y)
        if not cands:
            self._pick_cycle = None
            return ("", -1)
        if not cycle:
            self._pick_cycle = None
            best = min(cands, key=lambda c: (c[0], c[1]))
            return (best[2], best[3])
        order = sorted(cands, key=lambda c: (c[1], c[0]))
        key = (int(x), int(y), order[0][2])
        if self._pick_cycle and self._pick_cycle[0] == key:
            idx = (self._pick_cycle[1] + 1) % len(order)
        else:
            idx = 0
        self._pick_cycle = (key, idx)
        sel = order[idx]
        return (sel[2], sel[3])

    def keyPressEvent(self, e):
        if e.key() == Qt.Key_F:
            self.frame_all()
        elif e.key() == Qt.Key_R:
            self.reset_pose()
        else:
            super().keyPressEvent(e)
