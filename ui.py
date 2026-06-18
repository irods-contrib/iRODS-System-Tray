"""Settings window widgets and presentation for the tray-based monitor app."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QCheckBox,
    QFrame,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from config import IRODSEnvironment


class SettingsWindow(QWidget):
    """Provide the configuration window for monitored folders and recent activity.

    The window emits high-level signals instead of directly changing application state,
    which keeps the UI focused on presentation while the tray controller performs the
    actual persistence and monitor updates.
    """

    monitoring_toggled = Signal(bool)
    add_folder_requested = Signal()
    remove_folder_requested = Signal(str)
    save_irods_requested = Signal()

    def __init__(self) -> None:
        """Construct the minimalist settings UI used by the tray application."""

        super().__init__()
        self.setWindowTitle("Ingestion Monitor")
        self.resize(640, 460)

        self.title_label = QLabel("Directory Ingestion")
        self.title_label.setStyleSheet("font-size: 24px; font-weight: 600;")

        self.subtitle_label = QLabel("Monitor folders in the background from the system tray.")
        self.subtitle_label.setStyleSheet("color: #667085;")

        self.monitor_toggle = QCheckBox("Background monitoring enabled")
        self.monitor_toggle.toggled.connect(self.monitoring_toggled)
        self.monitor_toggle.setStyleSheet(
            "QCheckBox { font-size: 15px; font-weight: 600; padding: 6px 0; }"
        )

        self.status_label = QLabel("Ready")
        self.status_label.setWordWrap(True)
        self.status_label.setStyleSheet("color: #344054;")

        irods_card = QFrame()
        irods_card.setFrameShape(QFrame.Shape.StyledPanel)
        irods_card.setStyleSheet(
            "QFrame { border: 1px solid #d0d5dd; border-radius: 14px; background: #ffffff; }"
        )

        irods_layout = QVBoxLayout(irods_card)
        irods_layout.setContentsMargins(16, 16, 16, 16)
        irods_layout.setSpacing(12)

        irods_title = QLabel("iRODS session")
        irods_title.setStyleSheet("font-size: 16px; font-weight: 600;")

        form_layout = QFormLayout()
        form_layout.setSpacing(10)
        form_layout.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)

        self.irods_host_input = QLineEdit()
        self.irods_port_input = QSpinBox()
        self.irods_port_input.setRange(1, 65535)
        self.irods_user_name_input = QLineEdit()
        self.irods_password_input = QLineEdit()
        self.irods_password_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.irods_zone_name_input = QLineEdit()
        self.irods_home_collection_input = QLineEdit()

        form_layout.addRow("Host", self.irods_host_input)
        form_layout.addRow("Port", self.irods_port_input)
        form_layout.addRow("User", self.irods_user_name_input)
        form_layout.addRow("Password", self.irods_password_input)
        form_layout.addRow("Zone", self.irods_zone_name_input)
        form_layout.addRow("Collection", self.irods_home_collection_input)

        irods_button_row = QHBoxLayout()
        irods_button_row.setSpacing(10)
        self.save_irods_button = QPushButton("Save iRODS Settings")
        self.save_irods_button.clicked.connect(self._emit_save_irods_requested)
        irods_button_row.addWidget(self.save_irods_button)
        irods_button_row.addStretch(1)

        irods_layout.addWidget(irods_title)
        irods_layout.addLayout(form_layout)
        irods_layout.addLayout(irods_button_row)

        directory_card = QFrame()
        directory_card.setFrameShape(QFrame.Shape.StyledPanel)
        directory_card.setStyleSheet(
            "QFrame { border: 1px solid #d0d5dd; border-radius: 14px; background: #ffffff; }"
        )

        directory_layout = QVBoxLayout(directory_card)
        directory_layout.setContentsMargins(16, 16, 16, 16)
        directory_layout.setSpacing(12)

        directory_title = QLabel("Monitored folders")
        directory_title.setStyleSheet("font-size: 16px; font-weight: 600;")

        self.directory_list = QListWidget()
        self.directory_list.currentItemChanged.connect(self._update_remove_button_state)

        button_row = QHBoxLayout()
        button_row.setSpacing(10)

        self.add_button = QPushButton("Add Folder")
        self.add_button.clicked.connect(self._emit_add_requested)
        self.remove_button = QPushButton("Remove Folder")
        self.remove_button.clicked.connect(self._emit_remove_selected)
        self.remove_button.setEnabled(False)

        button_row.addWidget(self.add_button)
        button_row.addWidget(self.remove_button)
        button_row.addStretch(1)

        directory_layout.addWidget(directory_title)
        directory_layout.addWidget(self.directory_list)
        directory_layout.addLayout(button_row)

        activity_title = QLabel("Recent activity")
        activity_title.setStyleSheet("font-size: 16px; font-weight: 600;")

        self.activity_list = QListWidget()
        self.activity_list.setMaximumHeight(140)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(14)
        layout.addWidget(self.title_label)
        layout.addWidget(self.subtitle_label)
        layout.addWidget(self.monitor_toggle)
        layout.addWidget(self.status_label)
        layout.addWidget(irods_card)
        layout.addWidget(directory_card, 1)
        layout.addWidget(activity_title)
        layout.addWidget(self.activity_list)

        self.setStyleSheet(
            "QWidget { background: #f8fafc; color: #101828; }"
            "QPushButton { background: #101828; color: white; border-radius: 10px; padding: 10px 14px; }"
            "QPushButton:disabled { background: #98a2b3; }"
            "QListWidget { border: 1px solid #d0d5dd; border-radius: 10px; background: white; padding: 4px; }"
        )

    def set_monitoring_active(self, is_active: bool) -> None:
        """Update the checkbox state without re-emitting the user-facing toggle signal."""

        previous = self.monitor_toggle.blockSignals(True)
        self.monitor_toggle.setChecked(is_active)
        self.monitor_toggle.blockSignals(previous)

    def set_directories(self, directories: list[str], invalid_directories: set[str]) -> None:
        """Refresh the folder list and visually flag directories that no longer exist."""

        self.directory_list.clear()
        for directory in directories:
            label = directory
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, directory)
            if directory in invalid_directories:
                item.setForeground(QColor("#b42318"))
                item.setToolTip("Directory does not currently exist and is not being watched.")
            self.directory_list.addItem(item)
        self._update_remove_button_state()

    def set_irods_environment(self, environment: IRODSEnvironment) -> None:
        """Populate the iRODS settings form from persisted configuration."""

        self.irods_host_input.setText(environment.irods_host)
        self.irods_port_input.setValue(environment.irods_port)
        self.irods_user_name_input.setText(environment.irods_user_name)
        self.irods_password_input.setText(environment.irods_password)
        self.irods_zone_name_input.setText(environment.irods_zone_name)
        self.irods_home_collection_input.setText(environment.irods_home_collection)

    def get_irods_environment(self) -> IRODSEnvironment:
        """Collect the current form values into the config dataclass."""

        return IRODSEnvironment(
            irods_host=self.irods_host_input.text().strip(),
            irods_port=self.irods_port_input.value(),
            irods_user_name=self.irods_user_name_input.text().strip(),
            irods_password=self.irods_password_input.text(),
            irods_zone_name=self.irods_zone_name_input.text().strip(),
            irods_home_collection=self.irods_home_collection_input.text().strip(),
        )

    def set_status_message(self, message: str, *, is_error: bool = False) -> None:
        """Show a normal or error status message near the top of the window."""

        self.status_label.setText(message)
        color = "#b42318" if is_error else "#344054"
        self.status_label.setStyleSheet(f"color: {color};")

    def append_activity(self, message: str) -> None:
        """Prepend a new activity message and keep only a short rolling history."""

        self.activity_list.insertItem(0, message)
        while self.activity_list.count() > 50:
            self.activity_list.takeItem(self.activity_list.count() - 1)

    def closeEvent(self, event) -> None:  # noqa: N802
        """Hide the window instead of quitting so tray monitoring keeps running."""

        event.ignore()
        self.hide()

    def _emit_add_requested(self, _checked: bool = False) -> None:
        """Translate the add button click into a controller-facing signal."""

        self.add_folder_requested.emit()

    def _emit_remove_selected(self, _checked: bool = False) -> None:
        """Emit the currently selected directory so the controller can remove it."""

        item = self.directory_list.currentItem()
        if item is None:
            return
        directory = item.data(Qt.ItemDataRole.UserRole)
        self.remove_folder_requested.emit(directory)

    def _emit_save_irods_requested(self, _checked: bool = False) -> None:
        """Notify the controller that the user wants to persist iRODS settings."""

        self.save_irods_requested.emit()

    def _update_remove_button_state(self, *_args) -> None:
        """Enable removal only when the user has a directory selected in the list."""

        self.remove_button.setEnabled(self.directory_list.currentItem() is not None)
