"""
Reaction Time Bot - Human Benchmark 反应测试自动化工具
使用 Neverlose UI 风格
"""

import sys
import threading
import time
import ctypes
import mss
from ctypes import wintypes
from PySide6.QtCore import Qt, QThread, Signal, QPropertyAnimation, QEasingCurve, Property, QPointF
from PySide6.QtGui import QColor, QPainter, QPen, QPainterPath
from PySide6.QtWidgets import QApplication, QMainWindow, QWidget, QLabel, QVBoxLayout, QHBoxLayout, QFrame, QTextEdit

# ================= 核心配置 =================

GREEN_THRESHOLD = 170

# DPI 适配
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(1)
except:
    ctypes.windll.user32.SetProcessDPIAware()

user32 = ctypes.windll.user32

# Win32 结构体定义
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004

class MOUSEINPUT(ctypes.Structure):
    _fields_ = [("dx", wintypes.LONG), ("dy", wintypes.LONG),
                ("mouseData", wintypes.DWORD), ("dwFlags", wintypes.DWORD),
                ("time", wintypes.DWORD), ("dwExtraInfo", ctypes.POINTER(wintypes.ULONG))]

class INPUT(ctypes.Structure):
    class _INPUT(ctypes.Union):
        _fields_ = [("mi", MOUSEINPUT)]
    _fields_ = [("type", wintypes.DWORD), ("i", _INPUT)]

# 预编译点击指令
p_down = INPUT()
p_down.type = 0
p_down.i.mi.dwFlags = MOUSEEVENTF_LEFTDOWN

p_up = INPUT()
p_up.type = 0
p_up.i.mi.dwFlags = MOUSEEVENTF_LEFTUP

InputArray2 = INPUT * 2
click_command = InputArray2(p_down, p_up)

def fast_click():
    user32.SendInput(2, click_command, ctypes.sizeof(INPUT))

def move_mouse_to(x, y):
    user32.SetCursorPos(x, y)


# ================= 后台工作线程 =================

class BotWorker(QThread):
    log_signal = Signal(str)
    finished_signal = Signal()

    def __init__(self):
        super().__init__()
        self.running = False
        self.active = False

    def run(self):
        self.running = True
        self.log_signal.emit("Engine Ready. Waiting...")

        while self.running:
            if self.active:
                self.log_signal.emit("Starting in 3 seconds...")
                time.sleep(3)

                if not self.active:
                    continue

                with mss.mss() as sct:
                    monitor_info = sct.monitors[1]
                    center_x = monitor_info["left"] + int(monitor_info["width"] / 2)
                    center_y = monitor_info["top"] + int(monitor_info["height"] / 2)

                    move_mouse_to(center_x, center_y)
                    monitor = {"top": center_y, "left": center_x, "width": 1, "height": 1}

                    self.log_signal.emit(f"Locked: ({center_x}, {center_y})")
                    self.log_signal.emit(">>> Monitoring <<<")

                    while self.active and self.running:
                        sct_img = sct.grab(monitor)

                        if sct_img.raw[1] > GREEN_THRESHOLD:
                            fast_click()
                            self.log_signal.emit(f"CLICK! (G: {sct_img.raw[1]})")

                            time.sleep(0.5)

                            # 等待颜色恢复
                            while self.active and self.running:
                                temp = sct.grab(monitor)
                                if temp.raw[1] < 100:
                                    break
                                time.sleep(0.01)

                        time.sleep(0.001)

                self.log_signal.emit("Monitoring stopped.")
                self.active = False
                self.finished_signal.emit()

            time.sleep(0.1)

    def set_status(self, status):
        self.active = status
        if status:
            self.log_signal.emit("TRIGGERBOT ENGAGED.")

    def stop(self):
        self.running = False
        self.active = False
        self.wait()


# ================= UI 组件 =================

class LivelySwitch(QWidget):
    toggled = Signal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(50, 28)
        self.setCursor(Qt.PointingHandCursor)
        self._on = False
        self._start_x = 16
        self._end_x = 34
        self._circle_center_x = self._start_x
        self.anim = QPropertyAnimation(self, b"circle_center_x", self)
        self.anim.setDuration(300)

    @Property(float)
    def circle_center_x(self):
        return self._circle_center_x

    @circle_center_x.setter
    def circle_center_x(self, pos):
        self._circle_center_x = pos
        self.update()

    def set_state(self, state):
        if self._on != state:
            self._on = state
            self.toggled.emit(self._on)
            self.animate()

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.LeftButton:
            self._on = not self._on
            self.toggled.emit(self._on)
            self.animate()

    def animate(self):
        if self._on:
            self.anim.setEndValue(self._end_x)
            self.anim.setEasingCurve(QEasingCurve.OutBack)
        else:
            self.anim.setEndValue(self._start_x)
            self.anim.setEasingCurve(QEasingCurve.OutQuad)
        self.anim.start()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        progress = (self._circle_center_x - self._start_x) / (self._end_x - self._start_x)
        r = int(51 + (0 - 51) * progress)
        g = int(51 + (229 - 51) * progress)
        b = int(51 + (255 - 51) * progress)
        track_color = QColor(r, g, b)
        if not self._on and progress < 0.2:
            track_color.setAlpha(100)
        else:
            track_color.setAlpha(255)

        path = QPainterPath()
        path.addRoundedRect(0, 0, self.width(), self.height(), 14, 14)
        p.fillPath(path, track_color)
        p.setBrush(QColor(0, 0, 0, 40))
        p.setPen(Qt.NoPen)
        p.drawEllipse(QPointF(self._circle_center_x + 1, 15), 11, 11)
        p.setBrush(QColor("white"))
        p.drawEllipse(QPointF(self._circle_center_x, 14), 11, 11)


class ControlRow(QFrame):
    def __init__(self, title, switch_widget):
        super().__init__()
        self.setStyleSheet("""
            QFrame { background-color: #0f1012; border-radius: 12px; border: 1px solid #1a1a1a; }
            QFrame:hover { border: 1px solid #333; background-color: #141518; }
        """)
        self.setFixedHeight(70)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(20, 0, 20, 0)
        lbl = QLabel(title)
        lbl.setStyleSheet("color: white; font-family: 'Segoe UI'; font-weight: bold; font-size: 14px; border: none; background: transparent;")
        self.status_lbl = QLabel("OFF")
        self.status_lbl.setStyleSheet("color: #666; font-family: 'Consolas'; font-size: 12px; font-weight: bold; border: none; background: transparent;")
        layout.addWidget(lbl)
        layout.addStretch()
        layout.addWidget(self.status_lbl)
        layout.addSpacing(15)
        layout.addWidget(switch_widget)
        switch_widget.toggled.connect(self.update_status)

    def update_status(self, checked):
        self.status_lbl.setText("ON" if checked else "OFF")
        color = "#00E5FF" if checked else "#666"
        self.status_lbl.setStyleSheet(f"color: {color}; font-family: 'Consolas'; font-size: 12px; font-weight: bold; border: none; background: transparent;")


# ================= 主窗口 =================

class MainWindow(QMainWindow):
    reset_switch_signal = Signal()

    def __init__(self):
        super().__init__()
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.resize(340, 400)

        self.worker = BotWorker()
        self.worker.start()

        self.central = QWidget()
        self.setCentralWidget(self.central)
        layout = QVBoxLayout(self.central)
        layout.setContentsMargins(20, 20, 20, 15)
        layout.setSpacing(10)

        # 顶部栏
        top = QHBoxLayout()
        top.addStretch()
        btn_close = QLabel()
        btn_close.setFixedSize(12, 12)
        btn_close.setStyleSheet("background-color: #ff5f56; border-radius: 6px;")
        btn_close.setCursor(Qt.PointingHandCursor)
        btn_close.mousePressEvent = lambda e: self.close()
        top.addWidget(btn_close)
        layout.addLayout(top)

        # 标题
        title = QLabel("NEVERLOSE")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("color: white; font-family: 'Segoe UI'; font-size: 32px; font-weight: 900;")
        layout.addWidget(title)

        # 徽章
        badge_layout = QHBoxLayout()
        badge_layout.addStretch()
        badge = QLabel("By Fan1337")
        badge.setStyleSheet("background: rgba(0,229,255,0.1); color: #00E5FF; font-family: 'Consolas'; font-weight: bold; font-size: 11px; padding: 4px 8px; border-radius: 4px;")
        badge_layout.addWidget(badge)
        badge_layout.addStretch()
        layout.addLayout(badge_layout)

        layout.addSpacing(25)

        # 功能区
        self.switch = LivelySwitch()
        self.switch.toggled.connect(self.worker.set_status)
        self.control_row = ControlRow("TRIGGERBOT", self.switch)
        layout.addWidget(self.control_row)

        layout.addSpacing(10)

        # 日志
        self.log_box = QTextEdit()
        self.log_box.setReadOnly(True)
        self.log_box.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.log_box.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.log_box.setStyleSheet("background-color: #000; color: #666; font-family: 'Consolas'; font-size: 11px; border-radius: 12px; border: 1px solid #1a1a1a; padding: 12px;")
        self.log_box.setFixedHeight(120)
        layout.addWidget(self.log_box)

        self.worker.log_signal.connect(self.append_log)
        self.worker.finished_signal.connect(lambda: self.switch.set_state(False))
        self.reset_switch_signal.connect(lambda: self.switch.set_state(False))

        # 底部
        layout.addStretch()
        footer = QLabel("1337 Hackers at Work")
        footer.setAlignment(Qt.AlignCenter)
        footer.setStyleSheet("color: #333; font-family: 'Consolas'; font-size: 10px; font-weight: bold;")
        layout.addWidget(footer)

    def append_log(self, text):
        self.log_box.append(f"> {text}")
        self.log_box.verticalScrollBar().setValue(self.log_box.verticalScrollBar().maximum())

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setBrush(QColor("#050505"))
        p.setPen(QColor("black"))
        p.drawRoundedRect(self.rect().adjusted(1, 1, -1, -1), 32, 32)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.LeftButton:
            self.move(event.globalPosition().toPoint() - self.drag_pos)

    def closeEvent(self, event):
        self.worker.stop()
        event.accept()


# ================= 入口 =================

if __name__ == "__main__":
    app = QApplication(sys.argv)
    win = MainWindow()
    win.show()
    sys.exit(app.exec())
