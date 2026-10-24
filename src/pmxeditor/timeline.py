"""VMD 时间轴控件。

只做「播放/暂停 + 拖动帧号 + 显示当前帧」，动作应用由 MainWindow 负责。
"""

from __future__ import annotations

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import QCheckBox, QHBoxLayout, QLabel, QSlider, QWidget

from .theme import BAR_BG, BORDER_SOFT, mono_font
from .ui_widgets import label, text_button


class TimelineBar(QWidget):
    frameChanged = pyqtSignal(int)
    playToggled = pyqtSignal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(38)
        self.setStyleSheet("background:%s; border-top:1px solid %s;"
                           % (BAR_BG, BORDER_SOFT))
        lay = QHBoxLayout(self)
        lay.setContentsMargins(10, 4, 12, 4)
        lay.setSpacing(10)

        self.btn_play = text_button("播放", "Ghost", "play")
        self.btn_play.setCheckable(True)
        self.btn_play.setFixedWidth(72)
        self.btn_play.setToolTip("播放 / 暂停动作  空格")
        self.btn_play.toggled.connect(self._on_play)
        lay.addWidget(self.btn_play)

        self.slider = QSlider(Qt.Horizontal)
        self.slider.setRange(0, 0)
        self.slider.setSingleStep(1)
        self.slider.setPageStep(10)
        self.slider.valueChanged.connect(self._on_slider)
        lay.addWidget(self.slider, 1)

        self.frame_label = label("0 / 0", "Faint")
        self.frame_label.setFont(mono_font(8.6))
        self.frame_label.setMinimumWidth(78)
        self.frame_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        lay.addWidget(self.frame_label)

        self.loop_box = QCheckBox("循环")
        self.loop_box.setChecked(True)
        lay.addWidget(self.loop_box)

        self.name_label = label("", "Faint")
        self.name_label.setMinimumWidth(120)
        self.name_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        lay.addWidget(self.name_label)
        self._applying = False

    @property
    def looping(self) -> bool:
        return self.loop_box.isChecked()

    def configure(self, max_frame: int, name: str = ""):
        self._applying = True
        self.slider.setRange(0, max(0, int(max_frame)))
        self.slider.setValue(0)
        self._applying = False
        self.frame_label.setText("0 / %d" % max(0, int(max_frame)))
        self.name_label.setText(name)
        self.btn_play.setChecked(False)
        self.btn_play.setText("播放")

    def set_frame(self, frame: int, max_frame: int = -1):
        self._applying = True
        if max_frame >= 0:
            self.slider.setRange(0, max(0, int(max_frame)))
        self.slider.setValue(int(frame))
        self._applying = False
        self.frame_label.setText("%d / %d" % (int(frame), self.slider.maximum()))

    def _on_slider(self, value: int):
        self.frame_label.setText("%d / %d" % (int(value), self.slider.maximum()))
        if not self._applying:
            self.frameChanged.emit(int(value))

    def _on_play(self, on: bool):
        self.btn_play.setText("暂停" if on else "播放")
        self.playToggled.emit(bool(on))
