# -*- coding: utf-8 -*-
"""本地设置文件。

以前所有偏好都塞进 ``QSettings``（Windows 上就是注册表），出了问题既看不见也
改不了：主题"存不住"、亮色启动闪一下，最后都落在那个不可见的地方。现在统一
落在一个可读的 JSON 文件里：

    <仓库根>/settings.json           源码运行时
    %APPDATA%/PmxEditorModern/settings.json     根目录不可写（打包到 Program Files）时

启动时自动加载，任何一项改动立即写回；文件损坏会被改名成 ``settings.json.bak``
并从默认值重建，不会让程序起不来。想恢复出厂设置，删掉这个文件即可。

键用 ``段/名字`` 的点路径访问（``theme``、``view/bg_brightness``），写进文件时
按 ``/`` 展开成嵌套对象，方便手工编辑。
"""
from __future__ import annotations

import json
import os
import shutil
from pathlib import Path
from typing import Any

from .paths import ROOT

ENV_PATH = "PMXE_CONFIG"
FILENAME = "settings.json"

# 默认值也写进新文件，让用户一眼看到有哪些设置可调。
DEFAULTS = {
    "version": 1,
    "theme": "dark",
    "view": {
        "bg_brightness": 1.0,
        "model_brightness": 1.0,
        "show_grid": True,
        "show_bones": True,
        "show_rigid": True,
        "show_joints": True,
        "show_texture": True,
        "toon": True,
        "outline": True,
        "wireframe": False,
        "show_shadow": True,
    },
    "physics": {"gravity": -9.8, "iterations": 10, "ground": True},
    "paths": {"last_dir": "", "last_vpd_dir": ""},
    "window": {"geometry": "", "splitter": []},
    "editor": {"move_bone_vertices": True},
}

_INSTANCE = None


def default_path() -> Path:
    """配置文件位置：环境变量 > 仓库根（可写）> 用户目录。"""
    env = os.environ.get(ENV_PATH)
    if env:
        return Path(env).expanduser()
    return ROOT / FILENAME


def fallback_path() -> Path:
    base = os.environ.get("APPDATA") or str(Path.home())
    return Path(base) / "PmxEditorModern" / FILENAME


def _overlay(dst: dict, src: dict) -> dict:
    """用 src 覆盖 dst（文件里的值优先，缺失的键保留默认值）。"""
    for key, value in src.items():
        if isinstance(value, dict) and isinstance(dst.get(key), dict):
            _overlay(dst[key], value)
        else:
            dst[key] = value
    return dst


def _deepcopy(obj):
    return json.loads(json.dumps(obj))


_TRUE = {"true", "1", "yes", "on"}
_FALSE = {"false", "0", "no", "off", ""}


def _like(default, value):
    """按默认值的类型纠正手工/迁移来的值（注册表读出来的都是字符串）。"""
    if isinstance(default, bool):
        if isinstance(value, str):
            low = value.strip().lower()
            if low in _TRUE:
                return True
            if low in _FALSE:
                return False
            return bool(low)
        return bool(value)
    if isinstance(default, int) and not isinstance(default, bool):
        try:
            return int(float(value))
        except (TypeError, ValueError):
            return default
    if isinstance(default, float):
        try:
            return float(value)
        except (TypeError, ValueError):
            return default
    if isinstance(default, str):
        return default if value is None else str(value)
    return value


def _normalize(data: dict, defaults: dict) -> dict:
    """让每个已知键都带上默认值的类型；未知键原样保留。"""
    for key, default in defaults.items():
        if isinstance(default, dict):
            node = data.get(key)
            if not isinstance(node, dict):
                node = {}
                data[key] = node
            _normalize(node, default)
        elif key in data:
            data[key] = _like(default, data[key])
    return data


class Config:
    def __init__(self, path: Path, data: dict | None = None):
        self.path = Path(path)
        self._data = data if data is not None else _deepcopy(DEFAULTS)
        self.error = ""          # 最近一次读写失败的原因（设置页会显示）
        self.migrated = False    # 是否刚从旧 QSettings 迁移过

    # ------------------------------------------------------------ 读写
    def get(self, key: str, default: Any = None) -> Any:
        node: Any = self._data
        for part in str(key).replace("\\", "/").split("/"):
            if not isinstance(node, dict) or part not in node:
                return default
            node = node[part]
        return node

    def set(self, key: str, value: Any, save: bool = True) -> None:
        parts = str(key).replace("\\", "/").split("/")
        node = self._data
        for part in parts[:-1]:
            nxt = node.get(part)
            if not isinstance(nxt, dict):
                nxt = {}
                node[part] = nxt
            node = nxt
        node[parts[-1]] = value
        if save:
            self.save()

    def update(self, values: dict, save: bool = True) -> None:
        for key, value in values.items():
            self.set(key, value, save=False)
        if save:
            self.save()

    # ------------------------------------------------------------ 落盘
    def save(self) -> bool:
        """原子写入：先写临时文件再替换，中途断电不会留下半个 JSON。"""
        for path in self._candidates():
            try:
                path.parent.mkdir(parents=True, exist_ok=True)
                tmp = path.with_suffix(path.suffix + ".tmp")
                with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
                    json.dump(self._data, fh, ensure_ascii=False, indent=2)
                    fh.write("\n")
                os.replace(tmp, path)
                self.path = path
                self.error = ""
                return True
            except OSError as exc:
                self.error = "%s: %s" % (path, exc)
                continue
        return False

    def _candidates(self):
        """首选目标写失败时退回用户目录（打包安装到只读目录的情况）。"""
        yield self.path
        alt = fallback_path()
        if alt != self.path:
            yield alt

    # ------------------------------------------------------------ 载入
    @classmethod
    def load(cls, path: Path | None = None, force: bool = False) -> "Config":
        """读取配置；同一进程内复用同一个实例（main() 与主窗口共享）。"""
        global _INSTANCE
        if _INSTANCE is not None and not force and path is None:
            return _INSTANCE
        target = Path(path) if path is not None else default_path()
        cfg = cls(target)
        if target.exists():
            try:
                with open(target, encoding="utf-8") as fh:
                    raw = json.load(fh)
                if not isinstance(raw, dict):
                    raise ValueError("顶层不是对象")
                _overlay(cfg._data, raw)
                _normalize(cfg._data, DEFAULTS)
                cfg._data["version"] = int(cfg._data.get("version", 1))
            except Exception as exc:
                message = "配置损坏，已重建：%s" % exc
                try:
                    shutil.copyfile(target, target.with_suffix(".json.bak"))
                except OSError:
                    pass
                cfg._data = _deepcopy(DEFAULTS)
                cfg.save()
                cfg.error = message
        else:
            cfg._migrate_legacy()
            _normalize(cfg._data, DEFAULTS)
            cfg.save()
        if path is None:
            _INSTANCE = cfg
        return cfg

    def _migrate_legacy(self) -> None:
        """首次运行：把 QSettings 里的旧值搬过来，然后不再读注册表。"""
        try:
            from PyQt5.QtCore import QSettings, QByteArray
        except Exception:
            return
        try:
            old = QSettings("PmxEditorModern", "editor")
            if old.allKeys() == []:
                return
            mapping = {
                "theme": "theme",
                "last_dir": "paths/last_dir",
                "last_vpd_dir": "paths/last_vpd_dir",
                "view/bg_brightness": "view/bg_brightness",
                "view/model_brightness": "view/model_brightness",
                "editor/move_bone_vertices": "editor/move_bone_vertices",
            }
            for src, dst in mapping.items():
                value = old.value(src)
                if value is not None:
                    self.set(dst, value, save=False)
            geo = old.value("geometry")
            if isinstance(geo, QByteArray) and not geo.isEmpty():
                self.set("window/geometry",
                         bytes(geo.toBase64()).decode("ascii"), save=False)
            sizes = old.value("splitter")
            if sizes:
                self.set("window/splitter", [int(s) for s in sizes], save=False)
            self.migrated = True
        except Exception as exc:
            self.error = "迁移旧设置失败：%s" % exc
        finally:
            self.save()

    # ------------------------------------------------------------ 诊断
    def describe(self) -> str:
        return "%s（主题 %s）" % (self.path, self.get("theme", "dark"))


def reset_for_tests(path: Path | None = None) -> Config:
    """丢弃进程内缓存，重新按给定路径载入（回归场景用）。"""
    global _INSTANCE
    _INSTANCE = None
    return Config.load(path, force=True)
