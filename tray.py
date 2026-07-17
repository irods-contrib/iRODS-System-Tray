"""System tray coordinator tying together config, monitoring, and the settings UI."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject, QRectF, Qt, QTimer
from PySide6.QtGui import QAction, QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QApplication, QFileDialog, QMenu, QSystemTrayIcon

LOGO_PATH = Path(__file__).resolve().with_name("irods_logo.svg")

from config import ConfigStore, normalize_directory
from monitor import MonitorManager
from ui import SettingsWindow


class TrayController(QObject):
    """Own the long-lived application state and system tray interactions.

    This controller is the central integration point for the app: it loads and saves
    configuration, updates the watchdog monitor, reacts to GUI events, and handles tray
    icon behavior so monitoring can continue while the window stays hidden.
    """

    def __init__(self, app: QApplication) -> None:
        """Build the tray icon, menu, monitor, and settings window for the app."""

        super().__init__()
        self.app = app
        self.app.setQuitOnLastWindowClosed(False)

        self.config_store = ConfigStore()
        self.config = self.config_store.load()
        self.monitor = MonitorManager()
        self.window = SettingsWindow()

        self.monitor_toggle_action = QAction("Toggle Monitoring", self)
        self.monitor_toggle_action.setCheckable(True)
        self.monitor_toggle_action.toggled.connect(self.set_monitoring_active)
        self.menu = QMenu()

        tray_icon = QIcon(self._build_icon())
        self.tray_icon = QSystemTrayIcon(tray_icon, self)
        self.tray_icon.setToolTip("iRODS Ingest")
        self.window.setWindowIcon(tray_icon)
        self.tray_icon.activated.connect(self._handle_tray_activation)

        self._single_click_timer = QTimer(self)
        self._single_click_timer.setSingleShot(True)
        self._single_click_timer.timeout.connect(self.toggle_window)

        self._build_menu()
        self._connect_signals()
        self._sync_from_config()
        self.tray_icon.show()

    def show_window(self) -> None:
        """Show and focus the settings window from the tray or startup path."""

        self.window.show()
        self.window.raise_()
        self.window.activateWindow()

    def toggle_window(self) -> None:
        """Hide the settings window if visible, otherwise show and focus it."""

        if self.window.isVisible():
            self.window.hide()
            return
        self.show_window()

    def prompt_add_directory(self) -> None:
        """Open a native folder picker and add the chosen directory if provided."""

        selected = QFileDialog.getExistingDirectory(
            self.window,
            "Select folder to monitor",
            str(Path.home()),
        )
        if selected:
            self.add_directory(selected)

    def add_directory(self, path: str) -> None:
        """Normalize and persist a new monitored directory from the UI."""

        normalized = normalize_directory(path)
        if normalized in self.config.monitored_directories:
            self.window.set_status_message(f"Already monitoring {normalized}")
            return

        self.config.monitored_directories.append(normalized)
        self._persist_and_sync()
        self.window.set_status_message(f"Added {normalized}")

    def remove_directory(self, path: str) -> None:
        """Remove a monitored directory, then persist and resync background watches."""

        self.config.monitored_directories = [
            directory for directory in self.config.monitored_directories if directory != path
        ]
        self._persist_and_sync()
        self.window.set_status_message(f"Removed {path}")

    def set_monitoring_active(self, is_active: bool) -> None:
        """Apply the global monitoring toggle from either the tray or the window."""

        self.config.is_monitoring_active = is_active
        self._persist_and_sync()

    def exit_application(self) -> None:
        """Save state, stop background monitoring, and quit the Qt application cleanly."""

        self.config_store.save(self.config)
        self.monitor.shutdown()
        self.tray_icon.hide()
        self.app.quit()

    def _build_icon(self) -> QPixmap:
        """Rasterize the iRODS logo SVG."""

        renderer = QSvgRenderer(str(LOGO_PATH))
        size = renderer.defaultSize().scaled(32, 32, Qt.AspectRatioMode.KeepAspectRatio)
        pixmap = QPixmap(32, 32)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        renderer.render(
            painter,
            QRectF((32 - size.width()) / 2, (32 - size.height()) / 2, size.width(), size.height()),
        )
        painter.end()
        return pixmap

    def _build_menu(self) -> None:
        """Create the tray context menu and wire actions to controller methods."""

        open_action = self.menu.addAction("Open Settings")
        open_action.triggered.connect(lambda _checked=False: self.show_window())
        self.menu.addAction(self.monitor_toggle_action)
        self.menu.addSeparator()
        exit_action = self.menu.addAction("Exit")
        exit_action.triggered.connect(lambda _checked=False: self.exit_application())
        self.tray_icon.setContextMenu(self.menu)

    def _connect_signals(self) -> None:
        """Connect UI and monitor signals so changes flow through one controller."""

        self.window.add_folder_requested.connect(self.prompt_add_directory)
        self.window.remove_folder_requested.connect(self.remove_directory)
        self.window.monitoring_toggled.connect(self.set_monitoring_active)
        self.monitor.file_event.connect(self._handle_file_event)
        self.monitor.monitor_error.connect(self._handle_monitor_error)

    def _sync_from_config(self, *, show_status: bool = True) -> None:
        """Push the current config into the monitor, tray menu, and visible window.

        This keeps every surface of the app consistent after startup or after any user
        action that changes directories or the global enabled state.
        """

        self.monitor.sync(self.config.monitored_directories, self.config.is_monitoring_active)

        invalid_directories = {
            directory
            for directory in self.config.monitored_directories
            if not Path(directory).is_dir()
        }

        self.window.set_monitoring_active(self.config.is_monitoring_active)
        previous = self.monitor_toggle_action.blockSignals(True)
        self.monitor_toggle_action.setChecked(self.config.is_monitoring_active)
        self.monitor_toggle_action.blockSignals(previous)
        self.window.set_directories(self.config.monitored_directories, invalid_directories)

        if show_status:
            if not self.config.is_monitoring_active:
                self.window.set_status_message("Monitoring paused.")
            elif invalid_directories:
                self.window.set_status_message(
                    f"Monitoring active for available folders. {len(invalid_directories)} folder(s) are missing.",
                    is_error=True,
                )
            else:
                self.window.set_status_message("Monitoring active.")

    def _persist_and_sync(self) -> None:
        """Save the latest state and immediately refresh monitoring and UI widgets."""

        self.config.monitored_directories = list(dict.fromkeys(self.config.monitored_directories))
        self.config_store.save(self.config)
        self._sync_from_config()

    def _handle_tray_activation(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        """Interpret tray clicks so single and double clicks both toggle the window.

        A short timer delays the single-click action long enough to detect a possible
        double-click without triggering both behaviors.
        """

        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self._single_click_timer.start(self.app.doubleClickInterval())
        elif reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self._single_click_timer.stop()
            self.toggle_window()

    def _handle_file_event(self, event_type: str, path: str, is_directory: bool) -> None:
        """Format background file events into readable activity log entries."""

        entry_type = "folder" if is_directory else "file"
        self.window.append_activity(f"{event_type}: {entry_type} -> {path}")

    def _handle_monitor_error(self, message: str) -> None:
        """Surface monitoring failures in both the status area and activity log."""

        self.window.set_status_message(message, is_error=True)
        self.window.append_activity(f"warning: {message}")
