"""Background filesystem monitoring primitives built on watchdog and Qt signals."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject, Signal
from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer
from watchdog.observers.api import ObservedWatch


class EventBridge(QObject):
    """Expose watchdog activity as Qt signals that the GUI layer can consume safely.

    Watchdog callbacks do not talk directly to widgets. This bridge lets the monitor
    manager forward background events into Qt's signal/slot system instead.
    """

    file_event = Signal(str, str, bool)
    monitor_error = Signal(str)


class IngestionEventHandler(FileSystemEventHandler):
    """Translate every watchdog filesystem event into the shared event bridge."""

    def __init__(self, bridge: EventBridge) -> None:
        """Keep a reference to the bridge used for cross-thread event forwarding."""

        super().__init__()
        self.bridge = bridge

    def on_any_event(self, event: FileSystemEvent) -> None:
        """Emit a compact Qt signal for any file or directory change watchdog sees."""

        self.bridge.file_event.emit(event.event_type, event.src_path, event.is_directory)


class MonitorManager(QObject):
    """Own the watchdog observer and keep watched directories in sync with config.

    The tray controller hands this manager the latest directory list and global active
    flag whenever settings change. The manager is responsible for starting, stopping,
    scheduling, and unscheduling watches without requiring an application restart.
    """

    file_event = Signal(str, str, bool)
    monitor_error = Signal(str)

    def __init__(self) -> None:
        """Create the observer-facing state and wire internal signals outward."""

        super().__init__()
        self._observer: Observer | None = None
        self._bridge = EventBridge()
        self._handler = IngestionEventHandler(self._bridge)
        self._bridge.file_event.connect(self.file_event.emit)
        self._bridge.monitor_error.connect(self.monitor_error.emit)
        self._watches: dict[str, ObservedWatch] = {}

    def sync(self, directories: list[str], is_active: bool) -> None:
        """Reconcile active filesystem watches with the latest application state.

        When monitoring is disabled this tears everything down. When enabled, it keeps
        existing watches that still belong, removes obsolete ones, and schedules new
        watches for directories that currently exist.
        """

        if not is_active:
            self.stop()
            return

        if not self._ensure_running():
            return

        expected = set(directories)
        for directory, watch in list(self._watches.items()):
            if directory in expected:
                continue
            try:
                self._observer.unschedule(watch)
            except KeyError:
                pass
            del self._watches[directory]

        for directory in directories:
            if directory in self._watches:
                continue
            if not Path(directory).is_dir():
                continue
            try:
                watch = self._observer.schedule(self._handler, directory, recursive=False)
            except OSError as exc:
                self.monitor_error.emit(f"Failed to watch {directory}: {exc}")
                continue
            self._watches[directory] = watch

    def stop(self) -> None:
        """Stop the observer thread and clear all in-memory watch registrations."""

        if self._observer is None:
            return

        self._observer.stop()
        self._observer.join(timeout=5)
        self._observer = None
        self._watches.clear()

    def shutdown(self) -> None:
        """Provide a semantic shutdown hook for application exit paths."""

        self.stop()

    def _ensure_running(self) -> bool:
        """Start the watchdog observer if needed and report startup failures.

        Returning ``False`` lets callers skip further scheduling work when the monitor
        backend could not be started, while still keeping the rest of the application
        responsive.
        """

        if self._observer is not None and self._observer.is_alive():
            return True

        try:
            self._observer = Observer()
            self._observer.start()
        except OSError as exc:
            self._observer = None
            self.monitor_error.emit(f"Failed to start background monitor: {exc}")
            return False

        return True
