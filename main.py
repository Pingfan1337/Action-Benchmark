"""
Action Assist - generic screen color trigger helper.

The app stays an assistive auto-click tool: it watches one locked screen pixel
and clicks that point when the pixel turns green. It does not embed or require
any browser engine.
"""

import ctypes
import sys
import time
from ctypes import wintypes

import dxcam
from PySide6.QtCore import QEasingCurve, QPointF, QPropertyAnimation, Property, QThread, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPainterPath
from PySide6.QtWidgets import QApplication, QFrame, QHBoxLayout, QLabel, QMainWindow, QTextEdit, QVBoxLayout, QWidget


GREEN_THRESHOLD = 170
GREEN_DOMINANCE = 45
RESET_THRESHOLD = 100
POST_CLICK_GUARD_SECONDS = 0.0
LOCK_DELAY_SECONDS = 3
CAPTURE_RADIUS = 0
DXGI_SPIN_YIELD_EVERY = 4096
REPOSITION_BEFORE_CLICK = False


try:
    ctypes.windll.shcore.SetProcessDpiAwareness(1)
except Exception:
    ctypes.windll.user32.SetProcessDPIAware()

user32 = ctypes.windll.user32
gdi32 = ctypes.windll.gdi32
kernel32 = ctypes.windll.kernel32
winmm = ctypes.windll.winmm

MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
MOUSEEVENTF_MOVE = 0x0001
MOUSEEVENTF_ABSOLUTE = 0x8000
MOUSEEVENTF_VIRTUALDESK = 0x4000
THREAD_PRIORITY_HIGHEST = 2


class POINT(ctypes.Structure):
    _fields_ = [("x", wintypes.LONG), ("y", wintypes.LONG)]


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", wintypes.LONG),
        ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.POINTER(wintypes.ULONG)),
    ]


class INPUT(ctypes.Structure):
    class _INPUT(ctypes.Union):
        _fields_ = [("mi", MOUSEINPUT)]

    _fields_ = [("type", wintypes.DWORD), ("i", _INPUT)]


p_down = INPUT()
p_down.type = 0
p_down.i.mi.dwFlags = MOUSEEVENTF_LEFTDOWN

p_up = INPUT()
p_up.type = 0
p_up.i.mi.dwFlags = MOUSEEVENTF_LEFTUP

InputArray2 = INPUT * 2
click_command = InputArray2(p_down, p_up)


def make_move_click_command(x, y):
    virtual_left = user32.GetSystemMetrics(76)
    virtual_top = user32.GetSystemMetrics(77)
    virtual_width = user32.GetSystemMetrics(78)
    virtual_height = user32.GetSystemMetrics(79)

    absolute_x = int((x - virtual_left) * 65535 / max(1, virtual_width - 1))
    absolute_y = int((y - virtual_top) * 65535 / max(1, virtual_height - 1))

    p_move = INPUT()
    p_move.type = 0
    p_move.i.mi.dx = absolute_x
    p_move.i.mi.dy = absolute_y
    p_move.i.mi.dwFlags = MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE | MOUSEEVENTF_VIRTUALDESK

    InputArray3 = INPUT * 3
    return InputArray3(p_move, p_down, p_up)


user32.GetDC.argtypes = [wintypes.HWND]
user32.GetDC.restype = wintypes.HDC
user32.ReleaseDC.argtypes = [wintypes.HWND, wintypes.HDC]
user32.ReleaseDC.restype = ctypes.c_int
gdi32.GetPixel.argtypes = [wintypes.HDC, ctypes.c_int, ctypes.c_int]
gdi32.GetPixel.restype = wintypes.COLORREF
kernel32.GetCurrentThread.restype = wintypes.HANDLE
kernel32.SetThreadPriority.argtypes = [wintypes.HANDLE, ctypes.c_int]
kernel32.SetThreadPriority.restype = wintypes.BOOL
winmm.timeBeginPeriod.argtypes = [wintypes.UINT]
winmm.timeBeginPeriod.restype = wintypes.UINT
winmm.timeEndPeriod.argtypes = [wintypes.UINT]
winmm.timeEndPeriod.restype = wintypes.UINT


def fast_click_at(x, y):
    if REPOSITION_BEFORE_CLICK:
        command = make_move_click_command(x, y)
        user32.SendInput(3, command, ctypes.sizeof(INPUT))
    else:
        user32.SendInput(2, click_command, ctypes.sizeof(INPUT))


def current_cursor_pos():
    point = POINT()
    user32.GetCursorPos(ctypes.byref(point))
    return point.x, point.y


def colorref_to_rgb(color):
    red = color & 0xFF
    green = (color >> 8) & 0xFF
    blue = (color >> 16) & 0xFF
    return red, green, blue


def is_green_colorref(color):
    red, green, blue = colorref_to_rgb(color)
    return green >= GREEN_THRESHOLD and green - red >= GREEN_DOMINANCE and green - blue >= GREEN_DOMINANCE


def is_reset_colorref(color):
    return ((color >> 8) & 0xFF) < RESET_THRESHOLD


def make_capture_region(x, y, radius=CAPTURE_RADIUS):
    screen_width = user32.GetSystemMetrics(0)
    screen_height = user32.GetSystemMetrics(1)
    left = max(0, x - radius)
    top = max(0, y - radius)
    right = min(screen_width, x + radius + 1)
    bottom = min(screen_height, y + radius + 1)
    return (left, top, right, bottom)


def frame_has_green(frame):
    height, width = frame.shape[:2]
    red, green, blue = frame[height // 2, width // 2]
    red = int(red)
    green = int(green)
    blue = int(blue)
    return green >= GREEN_THRESHOLD and green - red >= GREEN_DOMINANCE and green - blue >= GREEN_DOMINANCE


def frame_has_reset(frame):
    height, width = frame.shape[:2]
    return int(frame[height // 2, width // 2, 1]) < RESET_THRESHOLD


class TriggerWorker(QThread):
    log_signal = Signal(str)
    stopped_signal = Signal()

    def __init__(self):
        super().__init__()
        self.running = False
        self.active = False

    def run(self):
        self.running = True
        winmm.timeBeginPeriod(1)
        kernel32.SetThreadPriority(kernel32.GetCurrentThread(), THREAD_PRIORITY_HIGHEST)
        self.log_signal.emit("Engine ready.")

        try:
            while self.running:
                if self.active:
                    self.run_trigger_loop()
                time.sleep(0.02)
        finally:
            winmm.timeEndPeriod(1)

    def run_trigger_loop(self):
        self.log_signal.emit(f"Move cursor to target pixel. Locking in {LOCK_DELAY_SECONDS}s...")
        for remaining in range(LOCK_DELAY_SECONDS, 0, -1):
            if not self.active or not self.running:
                return
            self.log_signal.emit(f"Lock in {remaining}...")
            time.sleep(1)

        if not self.active or not self.running:
            return

        lock_x, lock_y = current_cursor_pos()
        self.log_signal.emit(f"Locked pixel: ({lock_x}, {lock_y})")
        self.log_signal.emit("Monitoring with low-latency DXGI polling.")
        if self.run_dxgi_loop(lock_x, lock_y):
            self.log_signal.emit("Monitoring stopped.")
            self.stopped_signal.emit()
            return

        self.log_signal.emit("DXGI unavailable. Falling back to slower GDI polling.")
        self.run_gdi_loop(lock_x, lock_y)
        self.log_signal.emit("Monitoring stopped.")
        self.stopped_signal.emit()

    def run_dxgi_loop(self, lock_x, lock_y):
        camera = None
        try:
            region = make_capture_region(lock_x, lock_y)
            camera = dxcam.create(output_color="RGB", max_buffer_len=2, processor_backend="numpy")

            spin_count = 0
            while self.active and self.running:
                frame = camera.grab(region=region, copy=False, new_frame_only=True)
                if frame is None:
                    spin_count += 1
                    if spin_count % DXGI_SPIN_YIELD_EVERY == 0:
                        time.sleep(0)
                    continue

                if frame_has_green(frame):
                    fast_click_at(lock_x, lock_y)
                    if POST_CLICK_GUARD_SECONDS > 0:
                        time.sleep(POST_CLICK_GUARD_SECONDS)

                    while self.active and self.running:
                        frame = camera.grab(region=region, copy=False, new_frame_only=True)
                        if frame is None or frame_has_reset(frame):
                            break
                        spin_count += 1
                        if spin_count % DXGI_SPIN_YIELD_EVERY == 0:
                            time.sleep(0)

            return True
        except Exception as exc:
            self.log_signal.emit(f"DXGI capture failed: {exc}")
            return False
        finally:
            if camera is not None:
                try:
                    camera.release()
                except Exception:
                    pass

    def run_gdi_loop(self, lock_x, lock_y):
        screen_dc = user32.GetDC(None)
        if not screen_dc:
            self.log_signal.emit("Failed to acquire screen DC.")
            self.active = False
            return

        try:
            while self.active and self.running:
                color = gdi32.GetPixel(screen_dc, lock_x, lock_y)
                if is_green_colorref(color):
                    red, green, blue = colorref_to_rgb(color)
                    fast_click_at(lock_x, lock_y)
                    self.log_signal.emit(f"CLICK! R:{red} G:{green} B:{blue}")
                    if POST_CLICK_GUARD_SECONDS > 0:
                        time.sleep(POST_CLICK_GUARD_SECONDS)

                    while self.active and self.running:
                        if is_reset_colorref(gdi32.GetPixel(screen_dc, lock_x, lock_y)):
                            break
                        time.sleep(0)

                time.sleep(0)
        finally:
            user32.ReleaseDC(None, screen_dc)

    def set_active(self, active):
        self.active = active
        if active:
            self.log_signal.emit("AUTO CLICK armed.")
        else:
            self.log_signal.emit("AUTO CLICK disarmed.")

    def stop(self):
        self.running = False
        self.active = False
        self.wait()


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
        self.anim.setDuration(220)

    @Property(float)
    def circle_center_x(self):
        return self._circle_center_x

    @circle_center_x.setter
    def circle_center_x(self, pos):
        self._circle_center_x = pos
        self.update()

    def set_state(self, state):
        if self._on == state:
            return
        self._on = state
        self.toggled.emit(self._on)
        self.animate()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.set_state(not self._on)

    def animate(self):
        self.anim.stop()
        self.anim.setEndValue(self._end_x if self._on else self._start_x)
        self.anim.setEasingCurve(QEasingCurve.OutCubic)
        self.anim.start()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        progress = (self._circle_center_x - self._start_x) / (self._end_x - self._start_x)
        track_color = QColor(
            int(51 + (0 - 51) * progress),
            int(51 + (229 - 51) * progress),
            int(51 + (255 - 51) * progress),
        )
        track_color.setAlpha(255 if self._on or progress >= 0.2 else 110)

        path = QPainterPath()
        path.addRoundedRect(0, 0, self.width(), self.height(), 14, 14)
        painter.fillPath(path, track_color)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(0, 0, 0, 40))
        painter.drawEllipse(QPointF(self._circle_center_x + 1, 15), 11, 11)
        painter.setBrush(QColor("white"))
        painter.drawEllipse(QPointF(self._circle_center_x, 14), 11, 11)


class ControlRow(QFrame):
    def __init__(self, title, switch_widget):
        super().__init__()
        self.setStyleSheet("""
            QFrame { background-color: #0f1012; border-radius: 12px; border: 1px solid #1a1a1a; }
            QFrame:hover { border-color: #333; background-color: #141518; }
        """)
        self.setFixedHeight(70)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(20, 0, 20, 0)

        label = QLabel(title)
        label.setStyleSheet("color: white; font-family: 'Segoe UI'; font-weight: bold; font-size: 14px; border: none; background: transparent;")

        self.status_label = QLabel("OFF")
        self.status_label.setStyleSheet("color: #666; font-family: 'Consolas'; font-size: 12px; font-weight: bold; border: none; background: transparent;")

        layout.addWidget(label)
        layout.addStretch()
        layout.addWidget(self.status_label)
        layout.addSpacing(15)
        layout.addWidget(switch_widget)

        switch_widget.toggled.connect(self.update_status)

    def update_status(self, checked):
        self.status_label.setText("ON" if checked else "OFF")
        color = "#00e5ff" if checked else "#666"
        self.status_label.setStyleSheet(f"color: {color}; font-family: 'Consolas'; font-size: 12px; font-weight: bold; border: none; background: transparent;")


class InfoPanel(QFrame):
    def __init__(self):
        super().__init__()
        self.setStyleSheet("""
            QFrame { background-color: #101214; border-radius: 12px; border: 1px solid #202428; }
            QLabel { background: transparent; border: none; }
        """)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(5)

        title = QLabel("Lock target by cursor")
        title.setStyleSheet("color: white; font-family: 'Segoe UI'; font-size: 13px; font-weight: 800;")
        detail = QLabel("Enable, place cursor on the pixel to watch, then wait for green.")
        detail.setWordWrap(True)
        detail.setStyleSheet("color: #8a949e; font-family: 'Segoe UI'; font-size: 12px;")

        layout.addWidget(title)
        layout.addWidget(detail)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.resize(360, 440)

        self.worker = TriggerWorker()
        self.worker.start()

        self.central = QWidget()
        self.setCentralWidget(self.central)
        layout = QVBoxLayout(self.central)
        layout.setContentsMargins(20, 20, 20, 15)
        layout.setSpacing(10)

        top = QHBoxLayout()
        top.addStretch()
        close_button = QLabel()
        close_button.setFixedSize(12, 12)
        close_button.setStyleSheet("background-color: #ff5f56; border-radius: 6px;")
        close_button.setCursor(Qt.PointingHandCursor)
        close_button.mousePressEvent = lambda event: self.close()
        top.addWidget(close_button)
        layout.addLayout(top)

        title = QLabel("ACTION ASSIST")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("color: white; font-family: 'Segoe UI'; font-size: 28px; font-weight: 900;")
        layout.addWidget(title)

        badge_row = QHBoxLayout()
        badge_row.addStretch()
        badge = QLabel("By Fan1337")
        badge.setStyleSheet("background: rgba(0,229,255,0.1); color: #00e5ff; font-family: 'Consolas'; font-weight: bold; font-size: 11px; padding: 4px 8px; border-radius: 4px;")
        badge_row.addWidget(badge)
        badge_row.addStretch()
        layout.addLayout(badge_row)

        layout.addSpacing(18)

        self.switch = LivelySwitch()
        self.switch.toggled.connect(self.worker.set_active)
        layout.addWidget(ControlRow("AUTO CLICK", self.switch))

        layout.addWidget(InfoPanel())

        self.log_box = QTextEdit()
        self.log_box.setReadOnly(True)
        self.log_box.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.log_box.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.log_box.setStyleSheet("background-color: #000; color: #666; font-family: 'Consolas'; font-size: 11px; border-radius: 12px; border: 1px solid #1a1a1a; padding: 12px;")
        self.log_box.setFixedHeight(130)
        layout.addWidget(self.log_box)

        self.worker.log_signal.connect(self.append_log)

        layout.addStretch()
        footer = QLabel("Pixel trigger helper")
        footer.setAlignment(Qt.AlignCenter)
        footer.setStyleSheet("color: #333; font-family: 'Consolas'; font-size: 10px; font-weight: bold;")
        layout.addWidget(footer)

    def append_log(self, text):
        self.log_box.append(f"> {text}")
        self.log_box.verticalScrollBar().setValue(self.log_box.verticalScrollBar().maximum())

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setBrush(QColor("#050505"))
        painter.setPen(QColor("black"))
        painter.drawRoundedRect(self.rect().adjusted(1, 1, -1, -1), 32, 32)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.LeftButton and hasattr(self, "drag_pos"):
            self.move(event.globalPosition().toPoint() - self.drag_pos)

    def closeEvent(self, event):
        self.worker.stop()
        event.accept()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
