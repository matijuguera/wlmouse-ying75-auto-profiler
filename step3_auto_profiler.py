"""
WLMouse Auto Profiler
Monitors running processes and switches keyboard profiles automatically.
Requires: pip install hidapi psutil PyQt6
"""

import json
import sys
import time
import winreg
from pathlib import Path

import hid
import psutil
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QObject, QSize
from PyQt6.QtGui import QAction, QIcon, QPixmap, QFont, QColor, QPalette
from PyQt6.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QComboBox,
    QCheckBox,
    QGroupBox,
    QSystemTrayIcon,
    QMenu,
    QMessageBox,
    QFileDialog,
)

import wlmouse_protocol as proto

BASE_DIR = Path(__file__).parent
CONFIG_PATH = BASE_DIR / "config.json"
LOGO_PATH = BASE_DIR / "logo.jpg"
ICON_PATH = BASE_DIR / "logo.ico"

# WLMouse brand colors
COLOR_ORANGE = "#FFA300"
COLOR_DARK_BG = "#1a1a1a"
COLOR_PANEL_BG = "#242424"
COLOR_LIGHTER_BG = "#2e2e2e"
COLOR_TEXT = "#e0e0e0"
COLOR_TEXT_DIM = "#888888"
COLOR_BORDER = "#3a3a3a"

STARTUP_REG_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
STARTUP_REG_NAME = "WLMouseAutoProfiler"


def get_startup_command() -> str:
    """Build the command to run this script with pythonw (no console window)."""
    pythonw = Path(sys.executable).parent / "pythonw.exe"
    if not pythonw.exists():
        pythonw = Path(sys.executable)
    script = BASE_DIR / "step3_auto_profiler.py"
    return f'"{pythonw}" "{script}"'


def is_startup_enabled() -> bool:
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, STARTUP_REG_KEY, 0, winreg.KEY_READ)
        winreg.QueryValueEx(key, STARTUP_REG_NAME)
        winreg.CloseKey(key)
        return True
    except FileNotFoundError:
        return False


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
    QGroupBox {{
        background-color: {COLOR_PANEL_BG};
        border: 1px solid {COLOR_BORDER};
        border-radius: 8px;
        margin-top: 14px;
        padding: 16px 12px 12px 12px;
        font-weight: bold;
        font-size: 13px;
    }}
    QGroupBox::title {{
        subcontrol-origin: margin;
        subcontrol-position: top left;
        top: 7px;
        left: 14px;
        padding: 0 6px;
        color: {COLOR_ORANGE};
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
    QPushButton#btnSwitch {{
        background-color: {COLOR_ORANGE};
        color: {COLOR_DARK_BG};
        font-weight: bold;
        border: none;
    }}
    QPushButton#btnSwitch:hover {{
        background-color: #ffb733;
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
"""


def load_config():
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
        packet = proto.set_profile(profile_id)
        result = self._send(packet)
        if result:
            self.disconnect()
        return result

    def read_profile(self) -> bool:
        """Request current profile ID from keyboard."""
        packet = proto.get_profile()
        return self._send(packet)

    @property
    def connected(self) -> bool:
        return self.device is not None


class ProcessMonitor(QObject):
    """Watches if matched processes are running. Switches profile on launch, reverts on close."""

    process_matched = pyqtSignal(str, str)
    process_lost = pyqtSignal()

    def __init__(self, rules: list[dict], poll_interval_ms: int = 1000):
        super().__init__()
        self.rules = rules
        self.poll_interval_ms = poll_interval_ms
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
        running = set()
        for proc in psutil.process_iter(["name"]):
            try:
                running.add(proc.info["name"].lower())
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue

        matched = None
        for rule in self.rules:
            if rule["process"].lower() in running:
                matched = (rule["process"], rule["profile"])
                break

        if matched and self.current_match is None:
            self.current_match = matched
            self.process_matched.emit(matched[0], matched[1])
        elif not matched and self.current_match is not None:
            self.current_match = None
            self.process_lost.emit()

    def update_rules(self, rules: list[dict]):
        self.rules = rules


class RuleRow(QWidget):
    """A single rule row: process label + profile combo + delete button."""
    deleted = pyqtSignal(object)
    changed = pyqtSignal()

    def __init__(self, profiles: dict, process: str = "", profile: str = "0", parent=None):
        super().__init__(parent)
        self.process_name = process
        self.setFixedHeight(44)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        # Process label + browse button
        self.lbl_process = QLabel(process or "No process selected")
        self.lbl_process.setStyleSheet(
            f"color: {COLOR_TEXT}; font-size: 13px; padding: 4px 8px; "
            f"background-color: {COLOR_LIGHTER_BG}; border: 1px solid {COLOR_BORDER}; border-radius: 6px;"
        )
        self.lbl_process.setFixedHeight(34)
        if not process:
            self.lbl_process.setStyleSheet(
                f"color: {COLOR_TEXT_DIM}; font-size: 13px; padding: 4px 8px; font-style: italic; "
                f"background-color: {COLOR_LIGHTER_BG}; border: 1px solid {COLOR_BORDER}; border-radius: 6px;"
            )

        btn_browse = QPushButton("Browse...")
        btn_browse.setFixedSize(90, 34)
        btn_browse.clicked.connect(self._browse)

        self.profile_combo = QComboBox()
        self.profile_combo.setFixedHeight(34)
        for pid, pdata in profiles.items():
            self.profile_combo.addItem(pdata["name"], pid)
        idx = self.profile_combo.findData(profile)
        if idx >= 0:
            self.profile_combo.setCurrentIndex(idx)
        self.profile_combo.currentIndexChanged.connect(lambda: self.changed.emit())

        btn_del = QPushButton("Delete")
        btn_del.setFixedSize(70, 34)
        btn_del.clicked.connect(lambda: self.deleted.emit(self))

        layout.addWidget(self.lbl_process, 1)
        layout.addWidget(btn_browse)
        layout.addWidget(self.profile_combo)
        layout.addWidget(btn_del)

    def _browse(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Executable", "C:/",
            "Executables (*.exe);;All Files (*)"
        )
        if path:
            name = Path(path).name
            self.process_name = name
            self.lbl_process.setText(name)
            self.lbl_process.setStyleSheet(
                f"color: {COLOR_TEXT}; font-size: 13px; padding: 4px 8px; "
                f"background-color: {COLOR_LIGHTER_BG}; border: 1px solid {COLOR_BORDER}; border-radius: 6px;"
            )
            self.changed.emit()

    def get_rule(self) -> dict | None:
        if self.process_name:
            return {"process": self.process_name, "profile": self.profile_combo.currentData()}
        return None


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.config = load_config()
        self.current_profile = self.config.get("default_profile", "0")
        self.monitoring = False

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
        )
        self.monitor.process_matched.connect(self._on_process_matched)
        self.monitor.process_lost.connect(self._on_process_lost)

    def _init_ui(self):
        self.setWindowTitle("WLMouse Auto Profiler")
        self.setMinimumWidth(620)

        # Window icon
        if LOGO_PATH.exists():
            self.setWindowIcon(QIcon(str(ICON_PATH)))

        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setSpacing(12)
        layout.setContentsMargins(16, 12, 16, 8)

        # --- Header with logo ---
        header = QHBoxLayout()
        header.setSpacing(12)

        if LOGO_PATH.exists():
            logo_label = QLabel()
            pixmap = QPixmap(str(LOGO_PATH)).scaled(
                40, 40, Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )
            logo_label.setPixmap(pixmap)
            header.addWidget(logo_label)

        title_col = QVBoxLayout()
        title_col.setSpacing(0)
        title_label = QLabel("WLMouse Auto Profiler")
        title_label.setStyleSheet(f"font-size: 18px; font-weight: bold; color: {COLOR_ORANGE};")
        subtitle_label = QLabel("WLKB YING 75")
        subtitle_label.setStyleSheet(f"font-size: 11px; color: {COLOR_TEXT_DIM};")
        title_col.addWidget(title_label)
        title_col.addWidget(subtitle_label)
        header.addLayout(title_col)
        header.addStretch()

        # Status indicator in header
        self.lbl_device = QLabel()
        self.lbl_device.setObjectName("statusIcon")
        header.addWidget(self.lbl_device)

        layout.addLayout(header)

        # --- Active Profile + Manual Switch ---
        profile_group = QGroupBox("Active Profile")
        profile_layout = QVBoxLayout(profile_group)

        self.lbl_profile = QLabel(self._profile_name(self.current_profile))
        self.lbl_profile.setStyleSheet(f"font-size: 22px; font-weight: bold; color: {COLOR_ORANGE}; padding: 4px 0;")
        self.lbl_profile.setAlignment(Qt.AlignmentFlag.AlignCenter)
        profile_layout.addWidget(self.lbl_profile)

        switch_row = QHBoxLayout()
        switch_row.addStretch()

        self.cmb_manual = QComboBox()
        self.cmb_manual.setMinimumWidth(160)
        for pid, pdata in self.config["profiles"].items():
            self.cmb_manual.addItem(pdata["name"], pid)

        self.btn_switch = QPushButton("Switch")
        self.btn_switch.setObjectName("btnSwitch")
        self.btn_switch.clicked.connect(self._manual_switch)

        switch_row.addWidget(self.cmb_manual)
        switch_row.addWidget(self.btn_switch)
        switch_row.addStretch()
        profile_layout.addLayout(switch_row)

        layout.addWidget(profile_group)

        # --- Default Profile Rule ---
        default_group = QGroupBox("Default Profile")
        default_layout = QHBoxLayout(default_group)
        default_layout.setContentsMargins(12, 16, 12, 12)

        lbl_default = QLabel("When no app is matched, use:")
        lbl_default.setStyleSheet(f"color: {COLOR_TEXT}; font-size: 13px;")

        self.cmb_default = QComboBox()
        self.cmb_default.setFixedWidth(150)
        for pid, pdata in self.config["profiles"].items():
            self.cmb_default.addItem(pdata["name"], pid)
        idx = self.cmb_default.findData(self.config.get("default_profile", "0"))
        if idx >= 0:
            self.cmb_default.setCurrentIndex(idx)
        self.cmb_default.currentIndexChanged.connect(self._on_default_changed)

        default_layout.addWidget(lbl_default)
        default_layout.addWidget(self.cmb_default)
        default_layout.addStretch()

        layout.addWidget(default_group)

        # --- Rules ---
        rules_group = QGroupBox("Auto-Switch Rules")
        rules_group_layout = QVBoxLayout(rules_group)
        rules_group_layout.setSpacing(0)
        rules_group_layout.setContentsMargins(8, 20, 8, 8)

        self.rules_container = QWidget()
        self.rules_container.setStyleSheet("background: transparent;")
        self.rules_layout = QVBoxLayout(self.rules_container)
        self.rules_layout.setSpacing(6)
        self.rules_layout.setContentsMargins(0, 0, 0, 0)
        self.rules_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        self.rule_rows: list[RuleRow] = []

        rules_group_layout.addWidget(self.rules_container)

        btn_add = QPushButton("+ Add Rule")
        btn_add.setObjectName("btnAdd")
        btn_add.clicked.connect(lambda: self._add_rule_row())
        rules_group_layout.addWidget(btn_add)

        layout.addWidget(rules_group, 1)

        # --- Settings ---
        settings_group = QGroupBox("Settings")
        settings_layout = QVBoxLayout(settings_group)

        self.chk_tray = QCheckBox("Minimize to tray on close")
        self.chk_tray.setChecked(self.config.get("minimize_to_tray", True))
        self.chk_tray.stateChanged.connect(self._on_settings_changed)

        self.chk_startup = QCheckBox("Start with Windows")
        self.chk_startup.setChecked(is_startup_enabled())
        self.chk_startup.stateChanged.connect(self._on_startup_changed)

        settings_layout.addWidget(self.chk_tray)
        settings_layout.addWidget(self.chk_startup)
        layout.addWidget(settings_group)

        self._load_rules()
        self.statusBar().showMessage("Protocol: WLMouse HID v1.0.7")

        # Start as tall as the screen allows, centered
        screen = QApplication.primaryScreen().availableGeometry()
        self.resize(620, screen.height() - 64)
        self.move(screen.center().x() - 310, screen.top())

    def _init_tray(self):
        self.tray = QSystemTrayIcon(self)
        if LOGO_PATH.exists():
            self.tray.setIcon(QIcon(str(ICON_PATH)))
        self.tray.activated.connect(self._on_tray_click)
        menu = QMenu()
        show_action = QAction("Show", self)
        show_action.triggered.connect(self.show)
        quit_action = QAction("Quit", self)
        quit_action.triggered.connect(QApplication.quit)
        menu.addAction(show_action)
        menu.addAction(quit_action)
        self.tray.setContextMenu(menu)
        self.tray.show()

    def _on_tray_click(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self.show()
            self.raise_()
            self.activateWindow()

    def _auto_start(self):
        """Auto-connect device and start monitoring on launch."""
        if self.hid.connect():
            self.lbl_device.setText(f"<span style='color:#4caf50;'>&#9679;</span> Connected")
            self._log("Device connected")
            self._read_current_profile()
            self.monitor.update_rules(self.config.get("rules", []))
            self.monitor.start()
            self.monitoring = True
            self._log("Monitoring started")
        else:
            self.lbl_device.setText(f"<span style='color:#ff4444;'>&#9679;</span> Disconnected")
            self._log("Device not found — check USB connection")

    def _read_current_profile(self):
        """Read current profile from keyboard and sync the UI selector."""
        try:
            packet = proto.get_profile()
            self.hid.device.write(b"\x00" + packet)
            data = self.hid.device.read(64, timeout_ms=1000)
            if data and len(data) >= 5:
                profile_id = data[4]
                profile_str = str(profile_id)
                if profile_str in self.config.get("profiles", {}):
                    self.current_profile = profile_str
                    name = self._profile_name(profile_str)
                    self.lbl_profile.setText(name)
                    idx = self.cmb_manual.findData(profile_str)
                    if idx >= 0:
                        self.cmb_manual.setCurrentIndex(idx)
                    self._log(f"Current profile: {name}")
        except Exception as e:
            print(f"Read profile error: {e}")

    def _profile_name(self, profile_id: str) -> str:
        return self.config.get("profiles", {}).get(profile_id, {}).get("name", f"Profile {profile_id}")

    def _log(self, msg: str):
        print(f"[{time.strftime('%H:%M:%S')}] {msg}")

    def _switch_profile(self, profile_id: str) -> bool:
        pid = int(profile_id)
        name = self._profile_name(profile_id)
        self._log(f"Switching -> {name}")
        success = self.hid.switch_profile(pid)
        if success:
            self.current_profile = profile_id
            self.lbl_profile.setText(name)
            self.tray.setToolTip(f"WLMouse - {name}")
            idx = self.cmb_manual.findData(profile_id)
            if idx >= 0:
                self.cmb_manual.setCurrentIndex(idx)
            self._log(f"Switched to: {name}")
        else:
            self._log(f"ERROR: Failed to switch to {name}")
        return success

    def _manual_switch(self):
        self._switch_profile(self.cmb_manual.currentData())

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
        for rule in self.config.get("rules", []):
            self._add_rule_row(rule["process"], rule["profile"])

    def _add_rule_row(self, process: str = "", profile: str = "0"):
        row = RuleRow(self.config["profiles"], process, profile)
        row.deleted.connect(self._remove_rule_row)
        row.changed.connect(self._auto_save_rules)
        self.rule_rows.append(row)
        self.rules_layout.addWidget(row)
        self._adjust_window_height()

    def _remove_rule_row(self, row_widget):
        if row_widget in self.rule_rows:
            self.rule_rows.remove(row_widget)
            self.rules_layout.removeWidget(row_widget)
            row_widget.deleteLater()
            self._auto_save_rules()
            self._adjust_window_height()

    def _adjust_window_height(self):
        """Grow or shrink the window to fit the rule rows."""
        base_height = 550
        row_height = 50
        needed = base_height + len(self.rule_rows) * row_height
        screen = self.screen().availableGeometry().height()
        new_h = min(needed, screen - 50)
        if new_h > self.height():
            self.resize(self.width(), new_h)

    def _auto_save_rules(self):
        rules = []
        for row in self.rule_rows:
            rule = row.get_rule()
            if rule:
                rules.append(rule)
        self.config["rules"] = rules
        save_config(self.config)
        self.monitor.update_rules(rules)

    def _on_settings_changed(self):
        self.config["minimize_to_tray"] = self.chk_tray.isChecked()
        save_config(self.config)

    def _on_startup_changed(self):
        enabled = self.chk_startup.isChecked()
        try:
            set_startup_enabled(enabled)
            self._log(f"Start with Windows: {'enabled' if enabled else 'disabled'}")
        except Exception as e:
            self._log(f"ERROR: Could not change startup setting: {e}")
            self.chk_startup.setChecked(not enabled)

    def closeEvent(self, event):
        if self.chk_tray.isChecked():
            event.ignore()
            self.hide()
            self.tray.showMessage("WLMouse Auto Profiler",
                "Running in background. Right-click tray to quit.",
                QSystemTrayIcon.MessageIcon.Information, 2000)
        else:
            QApplication.quit()


LOCK_PATH = BASE_DIR / ".profiler.lock"


def acquire_lock():
    """Ensure only one instance runs. Returns lock file handle or None."""
    import msvcrt
    try:
        lock = open(LOCK_PATH, "w")
        msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
        lock.write(str(os.getpid()))
        lock.flush()
        return lock
    except (OSError, IOError):
        return None


def main():
    import os
    lock = acquire_lock()
    if lock is None:
        # Another instance is running — try to bring it to foreground
        app = QApplication(sys.argv)
        QMessageBox.information(None, "WLMouse Auto Profiler",
            "Already running. Check the system tray.")
        return

    app = QApplication(sys.argv)
    app.setApplicationName("WLMouse Auto Profiler")
    if LOGO_PATH.exists():
        app.setWindowIcon(QIcon(str(ICON_PATH)))
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
