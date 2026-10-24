"""模型信息页。"""
from __future__ import annotations

# -*- coding: utf-8 -*-
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (QGridLayout, QHBoxLayout, QLabel, QLineEdit, QPlainTextEdit, QVBoxLayout, QWidget)
from ..gl_names import bone_zh, material_zh, morph_zh
from ..pmx import model_stats, validate_model
from ..theme import BORDER, FIELD_BG, OK, TEXT, TEXT_FAINT, WARN, ui_font
from ..ui_widgets import Card, Form, label, text_button
from .base import PageBase

# ================================================================= 模型信息

class InfoPage(PageBase):
    def __init__(self, doc, parent=None):
        super().__init__(doc, "模型信息", "概览与描述", parent)
        self.tiles = {}
        grid = QGridLayout()
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(6)
        specs = [("vertices", "顶点"), ("faces", "三角面"), ("bones", "骨骼"),
                 ("materials", "材质"), ("morphs", "形态"), ("textures", "贴图"),
                 ("rigid", "刚体"), ("joints", "关节"), ("soft", "柔体")]
        for i, (key, cap) in enumerate(specs):
            tile = Card()
            tl = QVBoxLayout(tile)
            tl.setContentsMargins(10, 7, 10, 7)
            tl.setSpacing(0)
            vl = QLabel("0")
            vl.setFont(ui_font(12.5, 600))
            vl.setStyleSheet("color:%s;" % TEXT)
            cl = QLabel(cap)
            cl.setObjectName("Faint")
            tl.addWidget(vl)
            tl.addWidget(cl)
            self.tiles[key] = vl
            grid.addWidget(tile, i // 3, i % 3)
        self.root.addLayout(grid)

        scroll = self.scroll(QWidget())
        body = scroll.widget()
        bl = QVBoxLayout(body)
        bl.setContentsMargins(0, 0, 2, 4)
        bl.setSpacing(8)

        card, sec = self._card("显示名称", "写入 PMX 模型信息")
        form = Form(64)
        self.name_edit = QLineEdit()
        self.name_en_edit = QLineEdit()
        form.add("日文名", self.name_edit)
        form.add("英文名", self.name_en_edit)
        self.name_edit.editingFinished.connect(self._name_changed)
        self.name_en_edit.editingFinished.connect(self._name_en_changed)
        sec.add(form)
        bl.addWidget(card)

        card, sec = self._card("中文对照", "根据日文原名自动匹配")
        self.zh_label = label("—", "Value", True)
        sec.add(self.zh_label)
        bl.addWidget(card)

        card, sec = self._card("描述", "PMX 注释字段")
        self.comment = QPlainTextEdit()
        self.comment.setFixedHeight(96)
        self.comment.setStyleSheet(
            "QPlainTextEdit{background:%s;border:1px solid %s;border-radius:6px;"
            "padding:6px;color:%s;font-size:8.8pt;}" % (FIELD_BG, BORDER, TEXT))
        sec.add(self.comment)
        row = QHBoxLayout()
        row.addStretch(1)
        self.comment_btn = text_button("应用描述", "Ghost")
        self.comment_btn.clicked.connect(self._comment_changed)
        row.addWidget(self.comment_btn)
        sec.add_layout(row)
        bl.addWidget(card)

        card, sec = self._card("文件信息")
        self.info_form = Form(64)
        self.file_labels = {}
        for key, cap in (("path", "路径"), ("version", "版本"), ("encoding", "编码"),
                         ("index", "索引宽度"), ("uv", "附加 UV")):
            lb = label("—", "Faint", True)
            if key == "path":
                lb.setTextInteractionFlags(Qt.TextSelectableByMouse)
            self.file_labels[key] = lb
            self.info_form.add(cap, lb)
        sec.add(self.info_form)
        bl.addWidget(card)

        card, sec = self._card("模型校验")
        self.issues = label("尚未载入模型", "Faint", True)
        sec.add(self.issues)
        bl.addWidget(card)
        bl.addStretch(1)
        self.root.addWidget(scroll, 1)

    def _name_changed(self):
        m = self.doc.model
        if not m or self.loading:
            return
        v = self.name_edit.text()
        if v != m.name:
            self.edit("修改模型名", lambda mm: setattr(mm, "name", v), "model", "model.name")

    def _name_en_changed(self):
        m = self.doc.model
        if not m or self.loading:
            return
        v = self.name_en_edit.text()
        if v != m.name_en:
            self.edit("修改英文名", lambda mm: setattr(mm, "name_en", v), "model",
                      "model.name_en")

    def _comment_changed(self):
        m = self.doc.model
        if not m or self.loading:
            return
        v = self.comment.toPlainText()
        if v != m.comment:
            self.edit("修改描述", lambda mm: setattr(mm, "comment", v), "model")

    def refresh(self):
        m = self.doc.model
        self.loading = True
        try:
            if not m:
                for vl in self.tiles.values():
                    vl.setText("0")
                self.name_edit.setText("")
                self.name_en_edit.setText("")
                self.zh_label.setText("—")
                self.comment.setPlainText("")
                self.issues.setText("尚未载入模型")
                for lb in self.file_labels.values():
                    lb.setText("—")
                return
            st = model_stats(m)
            for k, vl in self.tiles.items():
                vl.setText(str(st.get(k, 0)))
            self.name_edit.setText(m.name)
            self.name_en_edit.setText(m.name_en)
            zh = ""
            for fn in (bone_zh, morph_zh, material_zh):
                hit = fn(m.name)
                if hit and hit != m.name:
                    zh = hit
                    break
            self.zh_label.setText(zh or "（无对照，保留原名）")
            self.zh_label.setStyleSheet("color:%s;" % (TEXT if zh else TEXT_FAINT))
            self.comment.setPlainText(m.comment)
            self.file_labels["path"].setText(m.path or "—")
            self.file_labels["version"].setText("%.1f" % m.version)
            self.file_labels["encoding"].setText(
                "UTF-16LE" if m.encoding == 0 else "UTF-8")
            self.file_labels["index"].setText(
                "V%d T%d M%d B%d Mo%d R%d" % (m.vsz, m.tsz, m.msz, m.bsz, m.mosz, m.rsz))
            self.file_labels["uv"].setText(str(m.add_uv))
            issues = validate_model(m)
            if issues:
                self.issues.setObjectName("WarnText")
                self.issues.setStyleSheet("color:%s;" % WARN)
                self.issues.setText("\n".join("· " + s for s in issues))
            else:
                self.issues.setStyleSheet("color:%s;" % OK)
                self.issues.setText("未发现结构问题")
        finally:
            self.loading = False
