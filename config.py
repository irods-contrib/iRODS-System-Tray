"""Configuration persistence helpers for the tray application's saved state."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Iterable


CONFIG_PATH = Path(__file__).resolve().with_name("app_state.json")


@dataclass(slots=True)
class AppConfig:
    """Store the persisted monitoring toggle and normalized directory list."""

    is_monitoring_active: bool = True
    monitored_directories: list[str] = field(default_factory=list)


def normalize_directory(path: str) -> str:
    """Convert a user-provided path into one canonical absolute directory string.

    This keeps saved paths consistent so duplicate entries caused by relative paths,
    home-directory shortcuts, or mixed path styles collapse to a single value.
    """

    return str(Path(path).expanduser().resolve(strict=False))


def normalize_directories(paths: Iterable[str]) -> list[str]:
    """Normalize, de-duplicate, and preserve the original order of directory paths.

    The UI and config layer both rely on this to avoid saving repeated entries while
    still keeping the list stable for display and future reloads.
    """

    unique_paths: list[str] = []
    seen: set[str] = set()
    for raw_path in paths:
        if not raw_path:
            continue
        normalized = normalize_directory(raw_path)
        if normalized in seen:
            continue
        seen.add(normalized)
        unique_paths.append(normalized)
    return unique_paths


class ConfigStore:
    """Load and save the application state as JSON on disk.

    This class isolates file I/O from the tray controller so the rest of the app can
    work with a simple ``AppConfig`` object instead of raw JSON data.
    """

    def __init__(self, path: Path | None = None) -> None:
        """Allow tests or callers to override the default config file location."""

        self.path = path or CONFIG_PATH

    def load(self) -> AppConfig:
        """Read configuration from disk and fall back to defaults on any error.

        Invalid JSON, missing files, or malformed directory lists should not prevent
        the tray application from starting, so this method always returns a usable
        ``AppConfig`` instance.
        """

        if not self.path.exists():
            return AppConfig()

        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return AppConfig()

        directories = payload.get("monitored_directories", [])
        if not isinstance(directories, list):
            directories = []

        return AppConfig(
            is_monitoring_active=bool(payload.get("is_monitoring_active", True)),
            monitored_directories=normalize_directories(directories),
        )

    def save(self, config: AppConfig) -> None:
        """Persist the current configuration atomically to reduce corruption risk.

        The file is written to a temporary path first and then replaced in one step so
        an interrupted write is less likely to leave behind a partially written config.
        """

        payload = asdict(config)
        payload["monitored_directories"] = normalize_directories(config.monitored_directories)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = self.path.with_suffix(".tmp")
        temp_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        temp_path.replace(self.path)
