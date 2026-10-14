"""
WLMouse Auto Profiler
Monitors running processes and switches keyboard profiles automatically.
Requires: pip install hidapi psutil PyQt6
"""

import ctypes
import json
import math
import os
import sys
import time
import winreg
from pathlib import Path

import hid
import psutil
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QByteArray, QObject, QPoint, QRectF, QSize
from PyQt6.QtGui import QAction, QActionGroup, QBrush, QIcon, QPainter, QPixmap
from PyQt6.QtSvg import QSvgRenderer
from PyQt6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QComboBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLayout,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QSlider,
    QSpacerItem,
    QStackedWidget,
    QSystemTrayIcon,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

import wlmouse_protocol as proto

STOCK_MAX_PERCENT = round(proto.STOCK_BRIGHTNESS_TABLE[-1] * 100 / proto.BRIGHTNESS_MAX_VALUE)

__version__ = "1.0.0"

FROZEN = getattr(sys, "frozen", False)  # running as the PyInstaller .exe
BASE_DIR = Path(__file__).parent
# Bundled read-only resources live in the PyInstaller temp dir when frozen
RESOURCE_DIR = Path(getattr(sys, "_MEIPASS", BASE_DIR))
# Writable user data can't live inside the .exe
DATA_DIR = Path(os.environ["APPDATA"]) / "WLMouseAutoProfiler" if FROZEN else BASE_DIR
CONFIG_PATH = DATA_DIR / "config.json"
LOGO_PATH = RESOURCE_DIR / "logo.jpg"

DEFAULT_CONFIG = {
    "device": {"vendor_id": "0x36A7", "product_id": "0xF887", "usage_page": "0xFFA0"},
    "profiles": {str(i): {"name": f"Profile {i + 1}"} for i in range(3)},
    "rules": [],
    "default_profile": "0",
    "poll_interval_ms": 1000,
    "minimize_to_tray": True,
}

# WLMouse brand colors
COLOR_ORANGE = "#FFA300"
COLOR_DARK_BG = "#1a1a1a"
COLOR_PANEL_BG = "#242424"
COLOR_LIGHTER_BG = "#2e2e2e"
COLOR_TEXT = "#e0e0e0"
COLOR_TEXT_DIM = "#888888"
COLOR_BORDER = "#3a3a3a"

LOGO_CORNER_RATIO = 0.22  # rounded-square app icon, like modern desktop app logos

# Tabler Icons "settings" (MIT license), drawn flat in a single color
GEAR_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="{color}" '
    'stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round">'
    '<path d="M10.325 4.317c.426 -1.756 2.924 -1.756 3.35 0a1.724 1.724 0 0 0 2.573 1.066c1.543 '
    '-.94 3.31 .826 2.37 2.37a1.724 1.724 0 0 0 1.065 2.572c1.756 .426 1.756 2.924 0 3.35a1.724 '
    '1.724 0 0 0 -1.066 2.573c.94 1.543 -.826 3.31 -2.37 2.37a1.724 1.724 0 0 0 -2.572 1.065c-.426 '
    '1.756 -2.924 1.756 -3.35 0a1.724 1.724 0 0 0 -2.573 -1.066c-1.543 .94 -3.31 -.826 -2.37 '
    '-2.37a1.724 1.724 0 0 0 -1.065 -2.572c-1.756 -.426 -1.756 -2.924 0 -3.35a1.724 1.724 0 0 0 '
    '1.066 -2.573c-.94 -1.543 .826 -3.31 2.37 -2.37c1 .608 2.296 .07 2.572 -1.065z"/>'
    '<path d="M9 12a3 3 0 1 0 6 0a3 3 0 0 0 -6 0"/></svg>'
)


def rounded_logo(size: int) -> QPixmap:
    """The app logo as a rounded square with transparent corners, rendered at `size` px."""
    scale = QApplication.instance().devicePixelRatio() if QApplication.instance() else 1.0
    px = math.ceil(size * scale)
    source = QPixmap(str(LOGO_PATH)).scaled(
        px, px, Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation)
    result = QPixmap(px, px)
    result.fill(Qt.GlobalColor.transparent)
    painter = QPainter(result)
    # Fill a rounded rect with the logo as its texture: unlike setClipPath (which is
    # aliased in the raster engine), shape fills are antialiased, so corners stay smooth
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QBrush(source))
    radius = px * LOGO_CORNER_RATIO
    painter.drawRoundedRect(QRectF(0, 0, px, px), radius, radius)
    painter.end()
    # Exactly `size` logical px, so labels don't rescale (and blur) it on scaled displays
    result.setDevicePixelRatio(px / size)
    return result


def app_icon() -> QIcon:
    """Rounded logo at every size Windows asks for (tray, title bar, taskbar, alt-tab)."""
    icon = QIcon()
    for size in (16, 20, 24, 32, 40, 48, 64, 128, 256):
        icon.addPixmap(rounded_logo(size))
    return icon


def svg_icon(svg_template: str, color: str, hover_color: str, size: int = 18) -> QIcon:
    """Flat single-color icon from an SVG template; `hover_color` is used on mouse-over."""
    icon = QIcon()
    for mode, fill in ((QIcon.Mode.Normal, color), (QIcon.Mode.Active, hover_color)):
        renderer = QSvgRenderer(QByteArray(svg_template.format(color=fill).encode()))
        pixmap = QPixmap(size * 2, size * 2)  # 2x so it stays sharp on scaled displays
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        renderer.render(painter)
        painter.end()
        icon.addPixmap(pixmap, mode)
    return icon


STARTUP_REG_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
STARTUP_REG_NAME = "WLMouseAutoProfiler"
STARTUP_APPROVED_KEY = r"Software\Microsoft\Windows\CurrentVersion\Explorer\StartupApproved\Run"
APP_USER_MODEL_ID = "WLMouse.AutoProfiler"


def get_startup_command() -> str:
    """Build the command to run this script with pythonw (no console window)."""
    if FROZEN:
        return f'"{sys.executable}"'
    pythonw = Path(sys.executable).parent / "pythonw.exe"
    if not pythonw.exists():
        pythonw = Path(sys.executable)
    script = BASE_DIR / "step3_auto_profiler.py"
    return f'"{pythonw}" "{script}"'


def _startup_disabled_in_windows() -> bool:
    """True if the entry was turned off in Task Manager / Settings > Startup apps."""
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, STARTUP_APPROVED_KEY, 0, winreg.KEY_READ)
        value, _ = winreg.QueryValueEx(key, STARTUP_REG_NAME)
        winreg.CloseKey(key)
        return bool(value) and value[0] & 1 == 1  # 02 = enabled, 03 = disabled
    except FileNotFoundError:
        return False


def is_startup_enabled() -> bool:
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, STARTUP_REG_KEY, 0, winreg.KEY_READ)
        winreg.QueryValueEx(key, STARTUP_REG_NAME)
        winreg.CloseKey(key)
    except FileNotFoundError:
        return False
    return not _startup_disabled_in_windows()


def set_startup_enabled(enabled: bool):
    key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, STARTUP_REG_KEY, 0, winreg.KEY_SET_VALUE)
    if enabled:
        winreg.SetValueEx(key, STARTUP_REG_NAME, 0, winreg.REG_SZ, get_startup_command())
    else:
        try:
            winreg.DeleteValue(key, STARTUP_REG_NAME)
        except FileNotFoundError:
            pass
    winreg.CloseKey(key)
    # Clear Windows' own "disabled" flag so re-enabling from the app actually works
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, STARTUP_APPROVED_KEY, 0, winreg.KEY_SET_VALUE)
        winreg.DeleteValue(key, STARTUP_REG_NAME)
        winreg.CloseKey(key)
    except FileNotFoundError:
        pass


STYLESHEET = f"""
    QMainWindow {{
        background-color: {COLOR_DARK_BG};
    }}
    QWidget {{
        background-color: {COLOR_DARK_BG};
        color: {COLOR_TEXT};
        font-family: "Segoe UI", sans-serif;
        font-size: 13px;
    }}
    QLabel#titleLabel {{
        font-size: 14px;
        font-weight: bold;
    }}
    QLabel#dimLabel {{
        color: {COLOR_TEXT_DIM};
    }}
    QLabel#noteLabel {{
        color: {COLOR_TEXT_DIM};
        font-size: 11px;
    }}
    QLabel#valueLabel {{
        color: {COLOR_ORANGE};
        font-size: 14px;
        font-weight: bold;
    }}
    QFrame#hline {{
        background-color: {COLOR_LIGHTER_BG};
    }}
    QFrame#ruleRow {{
        background-color: {COLOR_PANEL_BG};
        border: 1px solid {COLOR_BORDER};
        border-radius: 6px;
    }}
    QFrame#otherwiseRow {{
        border: 1px dashed {COLOR_BORDER};
        border-radius: 6px;
    }}
    QFrame#ruleRow QLabel, QFrame#otherwiseRow QLabel {{
        background: transparent;
    }}
    QPushButton#segBtn {{
        padding: 6px 0;
        font-weight: normal;
    }}
    QPushButton#segBtn:checked {{
        background-color: {COLOR_ORANGE};
        border-color: {COLOR_ORANGE};
        color: {COLOR_DARK_BG};
        font-weight: bold;
    }}
    QPushButton#tabBtn {{
        background: transparent;
        border: none;
        border-bottom: 2px solid transparent;
        border-radius: 0;
        padding: 8px 0;
        color: {COLOR_TEXT_DIM};
    }}
    QPushButton#tabBtn:hover {{
        color: {COLOR_TEXT};
    }}
    QPushButton#tabBtn:checked {{
        color: {COLOR_ORANGE};
        border-bottom-color: {COLOR_ORANGE};
    }}
    QPushButton#linkBtn {{
        background: transparent;
        border: none;
        padding: 2px 6px;
        color: {COLOR_ORANGE};
    }}
    QPushButton#linkBtn:hover {{
        color: #ffb733;
    }}
    QToolButton#gearBtn {{
        background: transparent;
        border: none;
        padding: 4px;
    }}
    QMenu {{
        background-color: {COLOR_PANEL_BG};
        border: 1px solid {COLOR_BORDER};
        padding: 4px 0;
    }}
    QMenu::item {{
        padding: 6px 16px 6px 30px;
    }}
    QMenu::item:selected {{
        background-color: {COLOR_LIGHTER_BG};
    }}
    QMenu::item:disabled {{
        color: {COLOR_TEXT_DIM};
    }}
    QMenu::indicator {{
        width: 12px;
        height: 12px;
        left: 10px;
        border: 1px solid {COLOR_BORDER};
        border-radius: 3px;
    }}
    QMenu::indicator:checked {{
        background-color: {COLOR_ORANGE};
        border-color: {COLOR_ORANGE};
    }}
    QMenu::separator {{
        height: 1px;
        background: {COLOR_BORDER};
        margin: 4px 0;
    }}
    QPushButton {{
        background-color: {COLOR_LIGHTER_BG};
        color: {COLOR_TEXT};
        border: 1px solid {COLOR_BORDER};
        border-radius: 6px;
        padding: 6px 16px;
        font-weight: 500;
    }}
    QPushButton:hover {{
        background-color: {COLOR_BORDER};
        border-color: {COLOR_ORANGE};
    }}
    QPushButton:pressed {{
        background-color: {COLOR_ORANGE};
        color: {COLOR_DARK_BG};
    }}
    QPushButton#btnAdd {{
        border-style: dashed;
        border-color: {COLOR_TEXT_DIM};
        color: {COLOR_TEXT_DIM};
    }}
    QPushButton#btnAdd:hover {{
        border-color: {COLOR_ORANGE};
        color: {COLOR_ORANGE};
    }}
    QPushButton#btnDel {{
        background-color: transparent;
        border: none;
        padding: 0;
        color: {COLOR_TEXT_DIM};
        font-weight: bold;
        font-size: 15px;
    }}
    QPushButton#btnDel:hover {{
        color: #ff4444;
    }}
    QComboBox {{
        background-color: {COLOR_LIGHTER_BG};
        border: 1px solid {COLOR_BORDER};
        border-radius: 6px;
        padding: 5px 10px;
        color: {COLOR_TEXT};
    }}
    QComboBox:hover {{
        border-color: {COLOR_ORANGE};
    }}
    QComboBox::drop-down {{
        border: none;
        width: 24px;
    }}
    QComboBox QAbstractItemView {{
        background-color: {COLOR_PANEL_BG};
        color: {COLOR_TEXT};
        selection-background-color: {COLOR_ORANGE};
        selection-color: {COLOR_DARK_BG};
        border: 1px solid {COLOR_BORDER};
    }}
    QLineEdit {{
        background-color: {COLOR_LIGHTER_BG};
        border: 1px solid {COLOR_BORDER};
        border-radius: 6px;
        padding: 5px 10px;
        color: {COLOR_TEXT};
    }}
    QLineEdit:focus {{
        border-color: {COLOR_ORANGE};
    }}
    QTableWidget {{
        background-color: {COLOR_PANEL_BG};
        border: none;
        gridline-color: {COLOR_BORDER};
        selection-background-color: {COLOR_LIGHTER_BG};
    }}
    QTableWidget::item {{
        padding: 4px;
    }}
    QHeaderView::section {{
        background-color: {COLOR_LIGHTER_BG};
        color: {COLOR_TEXT_DIM};
        border: none;
        border-bottom: 2px solid {COLOR_ORANGE};
        padding: 6px;
        font-weight: bold;
        font-size: 12px;
    }}
    QStatusBar {{
        background-color: {COLOR_PANEL_BG};
        color: {COLOR_TEXT_DIM};
        border-top: 1px solid {COLOR_BORDER};
        font-size: 11px;
    }}
    QLabel#logLabel {{
        background-color: {COLOR_LIGHTER_BG};
        border: 1px solid {COLOR_BORDER};
        border-radius: 6px;
        padding: 8px;
    }}
    QLabel#statusIcon {{
        font-size: 10px;
    }}
    QCheckBox {{
        color: {COLOR_TEXT};
        spacing: 8px;
        font-size: 13px;
    }}
    QCheckBox::indicator {{
        width: 18px;
        height: 18px;
        border: 1px solid {COLOR_BORDER};
        border-radius: 4px;
        background-color: {COLOR_LIGHTER_BG};
    }}
    QCheckBox::indicator:checked {{
        background-color: {COLOR_ORANGE};
        border-color: {COLOR_ORANGE};
    }}
    QCheckBox::indicator:hover {{
        border-color: {COLOR_ORANGE};
    }}
    QSlider::groove:horizontal {{
        background: {COLOR_LIGHTER_BG};
        height: 6px;
        border-radius: 3px;
        border: 1px solid {COLOR_BORDER};
    }}
    QSlider::handle:horizontal {{
        background: {COLOR_ORANGE};
        width: 18px;
        height: 18px;
        margin: -7px 0;
        border-radius: 9px;
    }}
    QSlider::handle:horizontal:hover {{
        background: #ffb733;
    }}
    QSlider::sub-page:horizontal {{
        background: {COLOR_ORANGE};
        border-radius: 3px;
    }}
"""


def load_config():
    if not CONFIG_PATH.exists():
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        save_config(DEFAULT_CONFIG)
    with open(CONFIG_PATH, "r") as f:
        return json.load(f)


def save_config(config):
    with open(CONFIG_PATH, "w") as f:
        json.dump(config, f, indent=2)


class HIDController:
    """Handles HID communication with the WLMouse keyboard."""

    def __init__(self, vendor_id: int, product_id: int, usage_page: int = 0):
        self.vendor_id = vendor_id
        self.product_id = product_id
        self.usage_page = usage_page
        self.device = None

    def connect(self) -> bool:
        try:
            devices = hid.enumerate(self.vendor_id, self.product_id)
            if self.usage_page:
                devices = [d for d in devices if d["usage_page"] == self.usage_page]
            if not devices:
                return False
            self.device = hid.device()
            self.device.open_path(devices[0]["path"])
            return True
        except Exception as e:
            print(f"HID connect error: {e}")
            return False

    def disconnect(self):
        if self.device:
            try:
                self.device.close()
            except Exception:
                pass
            self.device = None

    def _send(self, packet: bytes, retries: int = 3) -> bool:
        """Send a 64-byte packet with report ID 0x00 prepended, with auto-reconnect."""
        for attempt in range(retries):
            if not self.device:
                if not self.connect():
                    time.sleep(0.5)
                    continue
            try:
                self.device.write(b"\x00" + packet)
                return True
            except Exception as e:
                print(f"HID send error (attempt {attempt + 1}): {e}")
                self.disconnect()
                time.sleep(1)
        return False

    def switch_profile(self, profile_id: int) -> bool:
        """Switch the keyboard to the given profile (0-indexed)."""
        # If the switch reboots the keyboard (polling rate change), the next
        # _send fails on the stale handle and reconnects on its own
        return self._send(proto.set_profile(profile_id))

    def read_profile(self) -> bool:
        """Request current profile ID from keyboard."""
        packet = proto.get_profile()
        return self._send(packet)

    def _query_cmd(self, packet: bytes, command: int) -> int | None:
        """Send a CMD packet and return the value byte of its matching response."""
        if not self._send(packet):
            return None
        try:
            for _ in range(5):
                data = self.device.read(64, timeout_ms=500)
                if not data:
                    break
                value = proto.parse_cmd_response(data, command)
                if value is not None:
                    return value
        except Exception as e:
            print(f"CMD 0x{command:02X} read error: {e}")
        return None

    def read_brightness_table(self) -> list[int] | None:
        """Read the PWM values for luminance levels 1-4."""
        table = []
        for level in range(1, 5):
            value = self._query_cmd(
                proto.brightness_level_cmd(level),
                proto.CMD_BRIGHTNESS_LEVEL1 + level - 1,
            )
            if value is None:
                return None
            table.append(value)
        return table

    def write_brightness_table(self, table: list[int]) -> bool:
        """Write PWM values for luminance levels 1-4 and verify the echo."""
        for level, value in enumerate(table, start=1):
            echoed = self._query_cmd(
                proto.brightness_level_cmd(level, value),
                proto.CMD_BRIGHTNESS_LEVEL1 + level - 1,
            )
            if echoed != value:
                return False
        return True

    def read_prgb(self) -> dict | None:
        """Query the current keyboard lighting state and return parsed dict."""
        packet = proto.prgb_read()
        if not self._send(packet):
            return None
        try:
            data = self.device.read(64, timeout_ms=1000)
            if data:
                return proto.parse_prgb_response(data)
        except Exception as e:
            print(f"PRGB read error: {e}")
        return None

    def write_prgb(self, state: dict) -> bool:
        """Write a full PRGB lighting state to the keyboard."""
        packet = proto.prgb_pack(
            mode=1,
            colors=state["colors"],
            switch=state["switch"],
            direction=state["direction"],
            super_response=state["super_response"],
            luminance=state["luminance"],
            light_mode=state["light_mode"],
            speed=state["speed"],
            sleep_delay=state["sleep_delay"],
            static_mode=state.get("static_mode", 0),
        )
        return self._send(packet)

    @property
    def connected(self) -> bool:
        return self.device is not None


def foreground_process_names() -> list[str] | None:
    """Names of the focused window's process and its ancestors (lowercase), or None if unknown.

    Ancestors matter because games often run the window in a child process
    (VALORANT.exe -> VALORANT-Win64-Shipping.exe).
    """
    hwnd = ctypes.windll.user32.GetForegroundWindow()
    if not hwnd:
        return None  # transient (alt-tab, lock screen) — keep the current state
    pid = ctypes.c_ulong()
    ctypes.windll.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    try:
        proc = psutil.Process(pid.value)
        names = [proc.name().lower()]
        for parent in proc.parents()[:5]:
            names.append(parent.name().lower())
        return names
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        return None


class ProcessMonitor(QObject):
    """Switches profile when a rule's process is focused (or running), reverts otherwise."""

    process_matched = pyqtSignal(str, str)
    process_lost = pyqtSignal()

    def __init__(self, rules: list[dict], poll_interval_ms: int = 1000, foreground_only: bool = True):
        super().__init__()
        self.rules = rules
        self.poll_interval_ms = poll_interval_ms
        self.foreground_only = foreground_only
        self.current_match = None
        self._timer = None

    def start(self):
        self._timer = QTimer()
        self._timer.timeout.connect(self._poll)
        self._timer.start(self.poll_interval_ms)

    def stop(self):
        if self._timer:
            self._timer.stop()

    def _poll(self):
        if self.foreground_only:
            candidates = foreground_process_names()
            if candidates is None:
                return
        else:
            candidates = set()
            for proc in psutil.process_iter(["name"]):
                try:
                    candidates.add(proc.info["name"].lower())
                except (psutil.NoSuchProcess, psutil.AccessDenied, AttributeError):
                    continue

        matched = None
        for rule in self.rules:
            if rule["process"].lower() in candidates:
                matched = (rule["process"], rule["profile"])
                break

        if matched == self.current_match:
            return
        self.current_match = matched
        if matched:
            self.process_matched.emit(matched[0], matched[1])
        else:
            self.process_lost.emit()

    def update_rules(self, rules: list[dict]):
        self.rules = rules


class ProfileSelector(QWidget):
    """Segmented buttons, one per keyboard profile; the active one is highlighted."""

    selected = pyqtSignal(str)

    def __init__(self, profiles: dict, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        self.group = QButtonGroup(self)
        self.buttons: dict[str, QPushButton] = {}
        for pid, pdata in profiles.items():
            btn = QPushButton(pdata["name"])
            btn.setObjectName("segBtn")
            btn.setCheckable(True)
            btn.setToolTip(pdata["name"])
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(lambda _=False, p=pid: self.selected.emit(p))
            self.group.addButton(btn)
            self.buttons[pid] = btn
            layout.addWidget(btn)

    def set_active(self, profile_id: str):
        if profile_id in self.buttons:
            self.buttons[profile_id].setChecked(True)


class BrightnessControl(QWidget):
    """0-100% slider with a readout; `changed` fires only for user moves."""

    changed = pyqtSignal(int)

    def __init__(self, value: int, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setRange(0, 100)
        self.slider.setPageStep(10)
        self.slider.setValue(value)
        self.slider.setEnabled(False)  # until the lighting state is read from the keyboard
        self.lbl_value = QLabel(f"{value}%")
        self.lbl_value.setObjectName("valueLabel")
        self.lbl_value.setFixedWidth(44)
        self.lbl_value.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        layout.addWidget(self.slider, 1)
        layout.addWidget(self.lbl_value)
        self.slider.valueChanged.connect(self._on_moved)

    def _on_moved(self, value: int):
        self.lbl_value.setText(f"{value}%")
        self.changed.emit(value)



class RuleRow(QFrame):
    """One rule on a single line: app name, profile combo, remove button."""

    deleted = pyqtSignal(object)
    changed = pyqtSignal()

    def __init__(self, profiles: dict, process: str, profile: str, parent=None):
        super().__init__(parent)
        self.setObjectName("ruleRow")
        self.process_name = process
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 4, 4, 4)
        layout.setSpacing(6)

        lbl_name = QLabel(Path(process).stem)
        lbl_name.setToolTip(process)
        # Don't let long exe names widen the window; they're clipped instead
        lbl_name.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)

        self.profile_combo = make_profile_combo(profiles, profile)
        self.profile_combo.currentIndexChanged.connect(lambda: self.changed.emit())

        btn_del = QPushButton("✕")
        btn_del.setObjectName("btnDel")
        btn_del.setFixedSize(26, 26)
        btn_del.setToolTip("Remove rule")
        btn_del.clicked.connect(lambda: self.deleted.emit(self))

        layout.addWidget(lbl_name, 1)
        layout.addWidget(self.profile_combo)
        layout.addWidget(btn_del)

    def get_rule(self) -> dict:
        return {"process": self.process_name, "profile": self.profile_combo.currentData()}


def make_profile_combo(profiles: dict, selected: str) -> QComboBox:
    combo = QComboBox()
    combo.setFixedWidth(112)
    for pid, pdata in profiles.items():
        combo.addItem(pdata["name"], pid)
    idx = combo.findData(selected)
    if idx >= 0:
        combo.setCurrentIndex(idx)
    return combo


def hline() -> QFrame:
    line = QFrame()
    line.setObjectName("hline")
    line.setFixedHeight(1)
    return line


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.config = load_config()
        self.current_profile = self.config.get("default_profile", "0")
        self.monitoring = False
        self.prgb_state: dict | None = None

        self._init_hid()
        self._init_monitor()
        self._init_ui()
        self._init_tray()
        self._auto_start()

    def _init_hid(self):
        dev = self.config["device"]
        self.hid = HIDController(
            int(dev["vendor_id"], 16),
            int(dev["product_id"], 16),
            int(dev.get("usage_page", "0x0000"), 16),
        )

    def _init_monitor(self):
        self.monitor = ProcessMonitor(
            self.config.get("rules", []),
            self.config.get("poll_interval_ms", 1000),
            self.config.get("foreground_only", True),
        )
        self.monitor.process_matched.connect(self._on_process_matched)
        self.monitor.process_lost.connect(self._on_process_lost)

    def _init_ui(self):
        self.setWindowTitle("WLMouse Auto Profiler")
        if LOGO_PATH.exists():
            self.setWindowIcon(app_icon())
        profiles = self.config["profiles"]

        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        # The window always fits its content (grows/shrinks with the rules). A fixed
        # width on the widget would be overridden by SetFixedSize, so the width comes
        # from this zero-height spacer instead
        layout.setSizeConstraint(QLayout.SizeConstraint.SetFixedSize)
        layout.addSpacerItem(QSpacerItem(400, 0, QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed))

        # --- Header ---
        header = QHBoxLayout()
        header.setContentsMargins(14, 10, 14, 10)
        header.setSpacing(8)
        if LOGO_PATH.exists():
            logo = QLabel()
            logo.setPixmap(rounded_logo(22))
            header.addWidget(logo)
        title = QLabel("Auto Profiler")
        title.setObjectName("titleLabel")
        header.addWidget(title)
        header.addStretch()
        self.lbl_device = QLabel()
        self.lbl_device.setObjectName("statusIcon")
        header.addWidget(self.lbl_device)
        layout.addLayout(header)
        layout.addWidget(hline())

        # --- Profiles ---
        self.profile_selector = ProfileSelector(profiles)
        self.profile_selector.selected.connect(self._switch_profile)
        profiles_row = QHBoxLayout()
        profiles_row.setContentsMargins(14, 10, 14, 10)
        profiles_row.addWidget(self.profile_selector)
        layout.addLayout(profiles_row)
        layout.addWidget(hline())

        # --- Tabs ---
        tab_bar = QHBoxLayout()
        tab_bar.setContentsMargins(0, 0, 0, 0)
        tab_bar.setSpacing(0)
        self.pages = QStackedWidget()
        tab_group = QButtonGroup(self)
        self.tab_buttons: list[QPushButton] = []
        for index, name in enumerate(("Rules", "Lighting")):
            btn = QPushButton(name)
            btn.setObjectName("tabBtn")
            btn.setCheckable(True)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(lambda _=False, i=index: self.pages.setCurrentIndex(i))
            tab_group.addButton(btn)
            tab_bar.addWidget(btn)
            self.tab_buttons.append(btn)
        self.tab_buttons[0].setChecked(True)
        layout.addLayout(tab_bar)
        layout.addWidget(hline())

        # Rules page: one row per app, then the fallback ("Any other app") row
        rules_page = QWidget()
        rules_layout = QVBoxLayout(rules_page)
        rules_layout.setContentsMargins(14, 10, 14, 10)
        rules_layout.setSpacing(6)
        self.rules_layout = QVBoxLayout()
        self.rules_layout.setSpacing(6)
        rules_layout.addLayout(self.rules_layout)

        otherwise = QFrame()
        otherwise.setObjectName("otherwiseRow")
        otherwise_layout = QHBoxLayout(otherwise)
        otherwise_layout.setContentsMargins(10, 4, 4, 4)
        otherwise_layout.setSpacing(6)
        lbl_otherwise = QLabel("Any other app")
        lbl_otherwise.setObjectName("dimLabel")
        lbl_otherwise.setToolTip("Profile used when no app from the list is matched")
        self.cmb_default = make_profile_combo(profiles, self.config.get("default_profile", "0"))
        self.cmb_default.currentIndexChanged.connect(self._on_default_changed)
        otherwise_layout.addWidget(lbl_otherwise, 1)
        otherwise_layout.addWidget(self.cmb_default)
        otherwise_layout.addSpacing(26 + 6)  # line up with the rows' remove button
        rules_layout.addWidget(otherwise)

        btn_add = QPushButton("+ Add app")
        btn_add.setObjectName("btnAdd")
        btn_add.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_add.clicked.connect(self._add_app)
        rules_layout.addWidget(btn_add)
        rules_layout.addStretch()
        self.pages.addWidget(rules_page)

        # Lighting page
        lighting_page = QWidget()
        lighting_layout = QVBoxLayout(lighting_page)
        lighting_layout.setContentsMargins(14, 12, 14, 10)
        lighting_layout.setSpacing(6)
        lbl_brightness = QLabel("Brightness")
        lbl_brightness.setObjectName("dimLabel")
        lighting_layout.addWidget(lbl_brightness)
        self.brightness = BrightnessControl(self._brightness_percent())
        lighting_layout.addWidget(self.brightness)
        note = QLabel(f"Factory max was {STOCK_MAX_PERCENT}%  ·  higher draws more USB power")
        note.setObjectName("noteLabel")
        lighting_layout.addWidget(note)
        lighting_layout.addStretch()
        self.pages.addWidget(lighting_page)
        layout.addWidget(self.pages)

        # --- Footer: version + settings gear ---
        layout.addWidget(hline())
        footer = QHBoxLayout()
        footer.setContentsMargins(14, 4, 8, 4)
        version = QLabel(f"v{__version__}")
        version.setObjectName("noteLabel")
        footer.addWidget(version)
        footer.addStretch()
        self.btn_settings = QToolButton()
        self.btn_settings.setObjectName("gearBtn")
        self.btn_settings.setIcon(svg_icon(GEAR_SVG, COLOR_TEXT_DIM, COLOR_ORANGE))
        self.btn_settings.setIconSize(QSize(18, 18))
        self.btn_settings.setAutoRaise(True)  # uses the hover (Active) icon color
        self.btn_settings.setToolTip("Settings")
        self.btn_settings.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_settings.clicked.connect(self._show_settings_menu)
        footer.addWidget(self.btn_settings)
        layout.addLayout(footer)

        # Settings are actions so the gear menu and the tray menu share them
        self.act_foreground = QAction("Only use an app's profile while its window is focused", self)
        self.act_foreground.setCheckable(True)
        self.act_foreground.setChecked(self.config.get("foreground_only", True))
        self.act_foreground.toggled.connect(self._on_settings_changed)
        self.act_startup = QAction("Start with Windows", self)
        self.act_startup.setCheckable(True)
        self.act_startup.setChecked(is_startup_enabled())
        self.act_startup.toggled.connect(self._on_startup_changed)
        self.act_tray = QAction("Minimize to tray on close", self)
        self.act_tray.setCheckable(True)
        self.act_tray.setChecked(self.config.get("minimize_to_tray", True))
        self.act_tray.toggled.connect(self._on_settings_changed)
        self.settings_menu = QMenu(self)
        self.settings_menu.addActions([self.act_foreground, self.act_startup, self.act_tray])

        # Apply live while dragging, debounced so we don't flood the HID endpoint
        self._brightness_debounce = QTimer(self)
        self._brightness_debounce.setSingleShot(True)
        self._brightness_debounce.setInterval(150)
        self._brightness_debounce.timeout.connect(self._on_brightness_changed)
        self.brightness.changed.connect(self._on_brightness_slider_moved)

        self._load_rules()
        self.adjustSize()
        screen = QApplication.primaryScreen().availableGeometry()
        self.move(screen.center() - self.rect().center())

    def _show_settings_menu(self):
        # Open upwards, right-aligned to the gear (it sits at the bottom of the window)
        hint = self.settings_menu.sizeHint()
        pos = self.btn_settings.mapToGlobal(QPoint(self.btn_settings.width() - hint.width(), -hint.height()))
        self.settings_menu.exec(pos)

    def _init_tray(self):
        self.tray = QSystemTrayIcon(self)
        if LOGO_PATH.exists():
            self.tray.setIcon(app_icon())
        self.tray.activated.connect(self._on_tray_click)

        menu = QMenu()
        self.act_tray_status = QAction("YING 75", self)
        self.act_tray_status.setEnabled(False)
        menu.addAction(self.act_tray_status)
        menu.addSeparator()
        profile_group = QActionGroup(self)
        self.tray_profile_actions: dict[str, QAction] = {}
        for pid, pdata in self.config["profiles"].items():
            act = QAction(pdata["name"], self)
            act.setCheckable(True)
            act.triggered.connect(lambda _=False, p=pid: self._switch_profile(p))
            profile_group.addAction(act)
            menu.addAction(act)
            self.tray_profile_actions[pid] = act
        menu.addSeparator()
        menu.addActions([self.act_foreground, self.act_startup])
        menu.addSeparator()
        open_action = QAction("Open window", self)
        open_action.triggered.connect(self._show_main_window)
        quit_action = QAction("Quit", self)
        quit_action.triggered.connect(QApplication.quit)
        menu.addActions([open_action, quit_action])
        self.tray_menu = menu  # keep a reference; the tray doesn't own it
        self.tray.setContextMenu(menu)
        self.tray.show()
        self._refresh_profile_ui()

    def _on_tray_click(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self._show_main_window()

    def _show_main_window(self):
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def _refresh_profile_ui(self):
        """Reflect the active profile in the window and the tray menu."""
        pid = self.current_profile
        self.profile_selector.set_active(pid)
        if pid in self.tray_profile_actions:
            self.tray_profile_actions[pid].setChecked(True)
        self.tray.setToolTip(f"WLMouse - {self._profile_name(pid)}")


    def _auto_start(self):
        """Start monitoring and keep (re)connecting to the keyboard in the background."""
        self._set_connected_ui(False)
        # The table lives in RAM, so any keyboard reset (profile switch with a
        # different polling rate, replug, hub reset) reverts it to stock
        self.brightness_watchdog = QTimer(self)
        self.brightness_watchdog.timeout.connect(self._ensure_brightness)
        self.brightness_watchdog.start(3000)
        # Retry forever: at launch (e.g. Start with Windows, wake from sleep) the
        # keyboard may not be enumerated yet, and it can be unplugged at any time
        self.connection_timer = QTimer(self)
        self.connection_timer.timeout.connect(self._check_connection)
        self.connection_timer.start(2000)
        self._check_connection()
        self.monitor.update_rules(self.config.get("rules", []))
        self.monitor.start()
        self.monitoring = True
        self._log("Monitoring started")

    def _keyboard_present(self) -> bool:
        devices = hid.enumerate(self.hid.vendor_id, self.hid.product_id)
        return any(
            not self.hid.usage_page or d["usage_page"] == self.hid.usage_page for d in devices
        )

    def _set_connected_ui(self, connected: bool):
        color, text = ("#4caf50", "Connected") if connected else ("#ff4444", "Disconnected")
        dot = f"<span style='color:{color};'>&#9679;</span>"
        self.lbl_device.setText(f"{dot} {text}")
        self.act_tray_status.setText(f"YING 75 · {text}")

    def _check_connection(self):
        present = self._keyboard_present()
        if self.hid.connected and not present:
            self.hid.disconnect()
            self._set_connected_ui(False)
            self._log("Device disconnected — waiting for it to come back")
        elif not self.hid.connected and present and self.hid.connect():
            self._set_connected_ui(True)
            self._log("Device connected")
            self._read_current_profile()
            self._read_brightness()
            self._apply_brightness()
            # Re-evaluate the rules so the right profile is applied after reconnecting
            self.monitor.current_match = None
        elif self.hid.connected:
            self._set_connected_ui(True)  # _send may have reconnected on its own

    def _read_current_profile(self):
        """Read current profile from keyboard and sync the UI selector."""
        try:
            packet = proto.get_profile()
            self.hid.device.write(b"\x00" + packet)
            data = self.hid.device.read(64, timeout_ms=1000)
            profile_id = proto.parse_cmd_response(data, proto.CMD_CONFIG_ID) if data else None
            if profile_id is not None:
                profile_str = str(profile_id)
                if profile_str in self.config.get("profiles", {}):
                    self.current_profile = profile_str
                    self._refresh_profile_ui()
                    self._log(f"Current profile: {self._profile_name(profile_str)}")
        except Exception as e:
            print(f"Read profile error: {e}")

    def _profile_name(self, profile_id: str) -> str:
        return self.config.get("profiles", {}).get(profile_id, {}).get("name", f"Profile {profile_id}")

    def _log(self, msg: str):
        print(f"[{time.strftime('%H:%M:%S')}] {msg}")

    def _switch_profile(self, profile_id: str) -> bool:
        pid = int(profile_id)
        name = self._profile_name(profile_id)
        if not self.hid.connected:
            self._log(f"Keyboard not connected — {name} will be applied on reconnect")
            self._refresh_profile_ui()  # undo the highlight of the clicked button
            return False
        self._log(f"Switching -> {name}")
        success = self.hid.switch_profile(pid)
        if success:
            self.current_profile = profile_id
            self._log(f"Switched to: {name}")
        else:
            self._log(f"ERROR: Failed to switch to {name}")
        self._refresh_profile_ui()
        return success

    def _on_process_matched(self, process_name: str, profile_id: str):
        self._log(f"Detected: {process_name} -> {self._profile_name(profile_id)}")
        self._switch_profile(profile_id)

    def _on_default_changed(self):
        profile_id = self.cmb_default.currentData()
        self.config["default_profile"] = profile_id
        save_config(self.config)
        self._log(f"Default profile set to: {self._profile_name(profile_id)}")

    def _on_process_lost(self):
        default = self.cmb_default.currentData() or self.config.get("default_profile", "0")
        self._log(f"App closed -> reverting to {self._profile_name(default)}")
        self._switch_profile(default)

    def _load_rules(self):
        self.rule_rows: list[RuleRow] = []
        for rule in self.config.get("rules", []):
            self._add_rule_row(rule["process"], rule["profile"])

    def _add_rule_row(self, process: str, profile: str):
        row = RuleRow(self.config["profiles"], process, profile)
        row.deleted.connect(self._remove_rule_row)
        row.changed.connect(self._auto_save_rules)
        self.rule_rows.append(row)
        self.rules_layout.addWidget(row)

    def _add_app(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select the game or app", "C:/", "Executables (*.exe);;All Files (*)"
        )
        if not path:
            return
        name = Path(path).name
        if any(row.process_name.lower() == name.lower() for row in self.rule_rows):
            self._log(f"{name} already has a rule")
            return
        # A new app most likely wants a profile other than the fallback one
        default = self.cmb_default.currentData()
        profile = next((p for p in self.config["profiles"] if p != default), default)
        self._add_rule_row(name, profile)
        self._auto_save_rules()

    def _remove_rule_row(self, row_widget):
        if row_widget in self.rule_rows:
            self.rule_rows.remove(row_widget)
            self.rules_layout.removeWidget(row_widget)
            row_widget.deleteLater()
            self._auto_save_rules()

    def _auto_save_rules(self):
        rules = [row.get_rule() for row in self.rule_rows]
        self.config["rules"] = rules
        save_config(self.config)
        self.monitor.update_rules(rules)

    def _on_settings_changed(self):
        self.config["minimize_to_tray"] = self.act_tray.isChecked()
        self.config["foreground_only"] = self.act_foreground.isChecked()
        self.monitor.foreground_only = self.act_foreground.isChecked()
        save_config(self.config)

    def _read_brightness(self):
        """Query current PRGB state from the keyboard (needed to change the level)."""
        state = self.hid.read_prgb()
        if state:
            self.prgb_state = state
            self.brightness.slider.setEnabled(True)
        else:
            self._log("Could not read lighting state")

    def _brightness_percent(self) -> int:
        if "brightness_percent" in self.config:
            return max(0, min(int(self.config["brightness_percent"]), 100))
        # Migrate the old "max" setting (PWM value of level 4)
        legacy = self.config.get("brightness_max", proto.STOCK_BRIGHTNESS_TABLE[-1])
        return round(int(legacy) * 100 / proto.BRIGHTNESS_MAX_VALUE)

    @staticmethod
    def _brightness_table(percent: int) -> list[int]:
        return proto.scaled_brightness_table(round(percent * proto.BRIGHTNESS_MAX_VALUE / 100))

    def _apply_brightness(self):
        """0% = lights off (level 0); otherwise level 4 with the table scaled to the percent.

        Levels 1-3 scale along, so the Fn brightness keys keep working. The table lives in
        RAM, so it is re-applied on connect and by the watchdog after any keyboard reset.
        """
        percent = self._brightness_percent()
        level = 4 if percent > 0 else 0
        if percent > 0:
            table = self._brightness_table(percent)
            if not self.hid.write_brightness_table(table):
                self._log("ERROR: Failed to write brightness table")
                return
        if self.prgb_state is not None and self.prgb_state["luminance"] != level:
            state = dict(self.prgb_state, luminance=level)
            if not self.hid.write_prgb(state):
                self._log("ERROR: Failed to set brightness level")
                return
            self.prgb_state = state
        self._log(f"Brightness set to {percent}%")

    def _ensure_brightness(self):
        """Re-apply the brightness table if the keyboard reset since the last check."""
        percent = self._brightness_percent()
        if percent == 0 or not self.hid.connected:
            return  # off, or disconnected — _check_connection handles reconnecting
        level4 = proto.CMD_BRIGHTNESS_LEVEL1 + 3
        value = self.hid._query_cmd(proto.brightness_level_cmd(4), level4)
        if value is not None and value != self._brightness_table(percent)[-1]:
            self._log("Keyboard reset detected — re-applying brightness")
            self._apply_brightness()

    def _on_brightness_slider_moved(self, value: int):
        self._pending_brightness = value
        self._brightness_debounce.start()

    def _on_brightness_changed(self):
        self.config["brightness_percent"] = self._pending_brightness
        self.config.pop("brightness_max", None)
        save_config(self.config)
        self._apply_brightness()

    def _on_startup_changed(self, enabled: bool):
        try:
            set_startup_enabled(enabled)
            self._log(f"Start with Windows: {'enabled' if enabled else 'disabled'}")
        except Exception as e:
            self._log(f"ERROR: Could not change startup setting: {e}")
            self.act_startup.blockSignals(True)
            self.act_startup.setChecked(not enabled)
            self.act_startup.blockSignals(False)

    def closeEvent(self, event):
        if self.act_tray.isChecked():
            event.ignore()
            self.hide()
            self.tray.showMessage("WLMouse Auto Profiler",
                "Running in background. Right-click tray to quit.",
                QSystemTrayIcon.MessageIcon.Information, 2000)
        else:
            QApplication.quit()


LOCK_PATH = DATA_DIR / ".profiler.lock"


def acquire_lock():
    """Ensure only one instance runs. Returns lock file handle or None."""
    import msvcrt
    try:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        lock = open(LOCK_PATH, "w")
        msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
        lock.write(str(os.getpid()))
        lock.flush()
        return lock
    except (OSError, IOError):
        return None


def main():
    lock = acquire_lock()
    if lock is None:
        # Another instance is running — try to bring it to foreground
        app = QApplication(sys.argv)
        QMessageBox.information(None, "WLMouse Auto Profiler",
            "Already running. Check the system tray.")
        return

    # Own taskbar identity, otherwise Windows groups the window under pythonw.exe and its icon
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_USER_MODEL_ID)

    app = QApplication(sys.argv)
    app.setApplicationName("WLMouse Auto Profiler")
    if LOGO_PATH.exists():
        app.setWindowIcon(app_icon())
    app.setStyleSheet(STYLESHEET)

    window = MainWindow()
    window.show()
    ret = app.exec()

    # Release lock
    try:
        import msvcrt
        msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)
        lock.close()
        LOCK_PATH.unlink(missing_ok=True)
    except Exception:
        pass

    sys.exit(ret)


if __name__ == "__main__":
    import os
    main()
