"""Application entry point for the directory ingestion tray utility."""

from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication, QSystemTrayIcon

from tray import TrayController


def main() -> int:
    """Create the Qt application, validate tray support, and start the event loop.

    The tray controller owns the persistent background services and the settings
    window, so the entry point only needs to bootstrap Qt and hand off control.
    """

    app = QApplication(sys.argv)
    app.setApplicationName("Directory Ingestion")
    app.setOrganizationName("OpenCode")

    if not QSystemTrayIcon.isSystemTrayAvailable():
        raise SystemExit("System tray is not available in this environment.")

    controller = TrayController(app)
    controller.show_window()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
