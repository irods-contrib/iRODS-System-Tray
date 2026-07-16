"""Background iRODS upload worker that runs on a dedicated Qt thread."""

from __future__ import annotations

import time
from pathlib import Path, PurePosixPath
from threading import Lock

from PySide6.QtCore import QObject, Signal, Slot

from config import IRODSEnvironment, IRODSEnvironmentStore, normalize_irods_collection


class IRODSUploadWorker(QObject):
    """Perform blocking iRODS authentication and uploads away from the GUI thread."""

    upload_started = Signal(str, str)
    upload_progress = Signal(str, str, int, int)
    upload_finished = Signal(str, str)
    upload_failed = Signal(str, str)
    upload_cancelled = Signal(str, str)
    upload_paths_resolved = Signal(str, str)
    upload_debug = Signal(str)

    def __init__(self, environment_store: IRODSEnvironmentStore) -> None:
        super().__init__()
        self._environment_store = environment_store
        self._cancelled_monitored_roots: set[str] = set()
        self._cancelled_monitored_roots_lock = Lock()

    def cancel_directory_uploads(self, monitored_root: str) -> None:
        """Prevent any later queued uploads for an unavailable monitored folder."""

        normalized_root = str(Path(monitored_root).expanduser().resolve(strict=False))
        with self._cancelled_monitored_roots_lock:
            self._cancelled_monitored_roots.add(normalized_root)

    def allow_directory_uploads(self, monitored_root: str) -> None:
        """Allow uploads again for a monitored folder that became available."""

        normalized_root = str(Path(monitored_root).expanduser().resolve(strict=False))
        with self._cancelled_monitored_roots_lock:
            self._cancelled_monitored_roots.discard(normalized_root)

    @Slot(str, str, str)
    def upload_file(
        self,
        local_path: str,
        monitored_root: str,
        target_collection: str,
    ) -> None:
        """Upload a created or moved file into the configured iRODS collection."""

        local_file = Path(local_path).expanduser().resolve(strict=False)
        monitored_directory = Path(monitored_root).expanduser().resolve(strict=False)
        normalized_monitored_root = str(monitored_directory)
        environment = self._environment_store.load()
        stage = "initializing upload"

        if self._is_cancelled(normalized_monitored_root):
            self.upload_cancelled.emit(
                str(local_file),
                "Monitored folder became unavailable before upload started.",
            )
            return

        try:
            self.upload_debug.emit(
                f"upload debug -> stage={stage} local={local_file} monitored_root={monitored_directory}"
            )
            stage = "validating iRODS settings"
            self._validate_environment(environment)
            self.upload_debug.emit(f"upload debug -> stage={stage}")
            stage = "waiting for stable file"
            self._wait_for_stable_file(local_file)
            total_bytes = local_file.stat().st_size
            self.upload_debug.emit(
                f"upload debug -> stage={stage} size={total_bytes} local={local_file}"
            )
            stage = "building logical path"
            logical_path = self._build_logical_path(
                local_file,
                monitored_directory,
                target_collection,
            )
            self.upload_debug.emit(
                f"upload debug -> stage={stage} local={local_file} logical={logical_path}"
            )
            self.upload_started.emit(str(local_file), logical_path)
            stage = "streaming upload"
            self._stream_upload(local_file, logical_path, total_bytes, environment)
        except Exception as exc:  # noqa: BLE001
            self.upload_failed.emit(
                str(local_file),
                f"{stage}: {self._format_exception_message(exc)}",
            )
            return

        self.upload_finished.emit(str(local_file), logical_path)

    def _validate_environment(self, environment: IRODSEnvironment) -> None:
        """Reject incomplete iRODS settings before attempting a network connection."""

        required_values = {
            "irods_host": environment.irods_host,
            "irods_user_name": environment.irods_user_name,
            "irods_password": environment.irods_password,
            "irods_zone_name": environment.irods_zone_name,
        }
        missing = [name for name, value in required_values.items() if not str(value).strip()]
        if missing:
            missing_values = ", ".join(missing)
            raise ValueError(f"Missing iRODS settings: {missing_values}")

    def _wait_for_stable_file(self, local_file: Path) -> None:
        """Give newly created files a short window to settle before reading them."""

        previous_size: int | None = None
        stable_reads = 0

        for _attempt in range(10):
            if not local_file.exists():
                raise FileNotFoundError(f"File no longer exists: {local_file}")
            if not local_file.is_file():
                raise ValueError(f"Not a regular file: {local_file}")

            current_size = local_file.stat().st_size
            if current_size == previous_size:
                stable_reads += 1
                if stable_reads >= 2:
                    return
            else:
                stable_reads = 0

            previous_size = current_size
            time.sleep(0.3)

    def _build_logical_path(
        self,
        local_file: Path,
        monitored_directory: Path,
        target_collection: str,
    ) -> str:
        """Map a local file into the configured iRODS collection root."""

        try:
            relative_path = local_file.relative_to(monitored_directory)
        except ValueError:
            relative_path = Path(local_file.name)

        logical_root = PurePosixPath(normalize_irods_collection(target_collection))
        return str(logical_root.joinpath(*relative_path.parts))

    def _stream_upload(
        self,
        local_file: Path,
        logical_path: str,
        total_bytes: int,
        environment: IRODSEnvironment,
    ) -> None:
        """Authenticate to iRODS and upload to the configured logical path as-is."""

        try:
            from irods.session import iRODSSession
        except ImportError as exc:  # pragma: no cover - environment dependent
            raise RuntimeError(
                "python-irodsclient is not installed. Add it to the environment to enable uploads."
            ) from exc

        with iRODSSession(
            host=environment.irods_host,
            port=environment.irods_port,
            user=environment.irods_user_name,
            password=environment.irods_password,
            zone=environment.irods_zone_name,
        ) as session:
            self.upload_debug.emit(
                f"upload debug -> stage=session ready zone={environment.irods_zone_name}"
            )
            self.upload_progress.emit(str(local_file), logical_path, 0, total_bytes)
            self.upload_paths_resolved.emit(str(local_file), logical_path)
            self.upload_debug.emit(
                f"upload debug -> stage=before put local={local_file} logical={logical_path}"
            )
            print(f"iRODS put: local={local_file} logical={logical_path}", flush=True)
            session.data_objects.put(str(local_file), logical_path)
            self.upload_debug.emit("upload debug -> stage=put completed")
            self.upload_progress.emit(str(local_file), logical_path, total_bytes, total_bytes)

    def _format_exception_message(self, exc: Exception) -> str:
        """Return a stable error string even when the underlying exception is blank."""

        details = [str(part).strip() for part in getattr(exc, "args", ()) if str(part).strip()]
        if details:
            return ": ".join(details)
        return exc.__class__.__name__

    def _is_cancelled(self, monitored_root: str) -> bool:
        """Check whether uploads for this monitored folder were cancelled."""

        with self._cancelled_monitored_roots_lock:
            return monitored_root in self._cancelled_monitored_roots
