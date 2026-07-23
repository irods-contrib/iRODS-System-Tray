"""Application entry point for the directory ingestion tray utility."""

from __future__ import annotations

import signal
import sys
from pathlib import Path
from string import Template

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QGuiApplication, QPalette
from PySide6.QtWidgets import QApplication, QSystemTrayIcon

from tray import TrayController

APP_DIR = Path(__file__).resolve().parent
THEME_TEMPLATE_PATH = APP_DIR / "theme.qss.template"

THEME_TOKENS = {
    "dark": {
        "window_bg": "#14171a",
        "card_bg": "#1c2024",
        "field_bg": "#15181b",
        "border": "#5b5c61",
        "text": "#e6e8eb",
        "muted": "#8b93a0",
        "accent": "#00BDAC",
        "accent_hover": "#17c8b7",
        "accent_pressed": "#029e90",
        "accent_text": "#062019",
        "error": "#f87171",
        "disabled_bg": "#3a3f46",
        "disabled_text": "#6b7280",
    },
    "light": {
        "window_bg": "#f8fafc",
        "card_bg": "#ffffff",
        "field_bg": "#ffffff",
        "border": "#d0d5dd",
        "text": "#101828",
        "muted": "#5b5c61",
        "accent": "#00BDAC",
        "accent_hover": "#17c8b7",
        "accent_pressed": "#029e90",
        "accent_text": "#062019",
        "error": "#b42318",
        "disabled_bg": "#98a2b3",
        "disabled_text": "#ffffff",
    },
}


def _palette_from_tokens(tokens: dict[str, str]) -> QPalette:
    """Build a QPalette from the same token dict that fills theme.qss.template."""

    palette = QPalette()
    window_color = QColor(tokens["window_bg"])
    base_color = QColor(tokens["card_bg"])
    text_color = QColor(tokens["text"])
    muted_color = QColor(tokens["muted"])
    accent_color = QColor(tokens["accent"])
    accent_text_color = QColor(tokens["accent_text"])

    palette.setColor(QPalette.ColorRole.Window, window_color)
    palette.setColor(QPalette.ColorRole.WindowText, text_color)
    palette.setColor(QPalette.ColorRole.Base, base_color)
    palette.setColor(QPalette.ColorRole.AlternateBase, window_color)
    palette.setColor(QPalette.ColorRole.Text, text_color)
    palette.setColor(QPalette.ColorRole.Button, base_color)
    palette.setColor(QPalette.ColorRole.ButtonText, text_color)
    palette.setColor(QPalette.ColorRole.ToolTipBase, base_color)
    palette.setColor(QPalette.ColorRole.ToolTipText, text_color)
    palette.setColor(QPalette.ColorRole.PlaceholderText, muted_color)
    palette.setColor(QPalette.ColorRole.Highlight, accent_color)
    palette.setColor(QPalette.ColorRole.HighlightedText, accent_text_color)

    for role in (
        QPalette.ColorRole.WindowText,
        QPalette.ColorRole.Text,
        QPalette.ColorRole.ButtonText,
    ):
        palette.setColor(QPalette.ColorGroup.Disabled, role, muted_color)

    return palette


def _apply_theme(app: QApplication) -> None:
    """
    Switch the app's palette and stylesheet to match the current OS color scheme.
    Uses QStyleHints instead of platform-specific registry/plist reads.
    """

    is_dark = QGuiApplication.styleHints().colorScheme() == Qt.ColorScheme.Dark
    tokens = THEME_TOKENS["dark" if is_dark else "light"]
    app.setPalette(_palette_from_tokens(tokens))
    app.setStyleSheet(Template(THEME_TEMPLATE_PATH.read_text()).substitute(tokens))


def main() -> int:
    """Create the Qt application, validate tray support, and start the event loop.

    The tray controller owns the persistent background services and the settings
    window, so the entry point only needs to bootstrap Qt and hand off control.
    """

    app = QApplication(sys.argv)
    app.setApplicationName("System Tray Ingest")
    app.setOrganizationName("iRODS")
    app.setStyle("Fusion")
    _apply_theme(app)
    QGuiApplication.styleHints().colorSchemeChanged.connect(lambda _scheme: _apply_theme(app))

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
