"""Application entry point for the directory ingestion tray utility."""

from __future__ import annotations

import signal
import sys

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QSystemTrayIcon

from tray import TrayController


def main() -> int:
    """Create the Qt application, validate tray support, and start the event loop.

    The tray controller owns the persistent background services and the settings
    window, so the entry point only needs to bootstrap Qt and hand off control.
    """

    app = QApplication(sys.argv)
    app.setApplicationName("System Tray Ingest")
    app.setOrganizationName("iRODS")

    if not QSystemTrayIcon.isSystemTrayAvailable():
        raise SystemExit("System tray is not available in this environment.")

    controller = TrayController(app)
    controller.show_window()

    signal.signal(signal.SIGINT, lambda *_args: app.quit())

    interrupt_timer = QTimer()
    interrupt_timer.timeout.connect(lambda: None)
    interrupt_timer.start(200)

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
