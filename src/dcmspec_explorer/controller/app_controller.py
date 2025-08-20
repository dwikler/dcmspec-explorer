"""Controller class for the DCMspec Explorer application."""

import threading

from PySide6.QtCore import Qt, QTimer, QObject
from PySide6.QtGui import QStandardItemModel, QStandardItem

from dcmspec.progress import Progress

from dcmspec_explorer.app_config import load_app_config, setup_logger
from dcmspec_explorer.model.model import Model
from dcmspec_explorer.services.service_mediator import IODListLoaderServiceMediator
from dcmspec_explorer.view.main_window import MainWindow


class AppController(QObject):
    """Manage the interaction between the data model and the main window, following the MVP pattern.

    Manages the application's business logic and orchestrates communication between the View and the Model.

    This class is responsible for:
    - Connecting to signals emitted by the View.
    - Executing application logic.
    - Updating the View's state via its public API.

    Architectural Note: This class serves the role of a 'Presenter' in a Model-View-Presenter (MVP) architectural
    pattern. The term 'Controller' is used for clarity and familiarity, as its function is to control the application's
    flow.
    """

    def __init__(self) -> None:
        """Initialize the application controller.

        Create the model and main window instances, and prepare to connect them.
        """
        super().__init__()

        self.config = load_app_config()
        self.logger = setup_logger(self.config)

        # Log startup information
        self.logger.info("Starting DCMspec Explorer...")
        log_level_configured = self.config.get_param("log_level") or "INFO"
        config_source = (
            "app-specific"
            if self.config.config_file and "dcmspec_explorer_config.json" in self.config.config_file
            else "default"
        )
        self.logger.info(f"Logging configured: level={log_level_configured.upper()}, source={config_source}")
        # Log operational configuration at INFO level (important for users to know)
        config_file_display = self.config.config_file or "none (using defaults)"
        self.logger.info(f"Config file: {config_file_display}")
        self.logger.info(f"Cache directory: {self.config.cache_dir}")

        # Log thread information
        self.logger.debug(f"AppController created in thread: {threading.current_thread().name}")

        # Create model and view
        self.model = Model(self.config, self.logger)
        self.view = MainWindow()

        # Initialize the service mediator
        self.service = IODListLoaderServiceMediator(self.model, self.logger, parent=self)

        # Use QTimer to ensure the treeview is only initialized after the window is shown
        QTimer.singleShot(0, self.initialize_treeview)

    def initialize_treeview(self) -> None:
        """Initialize the treeview with list of IODs.

        Using a background thread and blinker signals to show a progress loading message while data is being loaded.
        """
        self.view.update_status_bar(message="Loading IOD modules...")

        # Start the worker in a background thread via the service mediator
        self._treeview_worker, self._treeview_thread = self.service.start_iodlist_worker()

        # Connect service mediator's Qt signals to UI update methods.
        # By specifying Qt.QueuedConnection, we ensure that if a signal is emitted from any thread,
        # the connected slot (UI update method) will be executed in the thread that owns the receiver object.
        # In this case, both the ServiceMediator and AppController live in the main thread, so UI updates
        # are performed in the main thread, ensuring thread safety for all Qt UI operations.
        self.service.iodlist_progress_signal.connect(self._update_iodlist_progress_ui, Qt.QueuedConnection)
        self.service.iodlist_loaded_signal.connect(self._update_iodlist_loaded_ui, Qt.QueuedConnection)
        self.service.iodlist_error_signal.connect(self._update_iodlist_error_ui, Qt.QueuedConnection)

    def _update_iodlist_progress_ui(self, sender: object, progress: Progress) -> None:
        percent = progress.percent
        self.logger.debug(f"Progress signal received from {sender}: percent={percent}")
        if percent == -1:
            self.logger.debug("Unknown progress received (-1).")
            self.view.update_status_bar(message="Loading IOD modules... (unknown progress)")
        elif percent % 10 == 0 or percent == 100:
            self.logger.debug(f"Progress update: {percent}%")
            self.view.update_status_bar(f"Loading IOD modules... {percent}%")

    def _update_iodlist_loaded_ui(self, sender: object, iod_modules: object) -> None:
        qt_tree_model = self._build_qt_tree_model(iod_modules)
        self.view.update_treeview(qt_tree_model)
        self.view.update_status_bar(message=f"Loaded {len(iod_modules)} IOD modules.")

    def _update_iodlist_error_ui(self, sender: object, message: str) -> None:
        self.logger.error(f"Error signal received from {sender}: {message}")
        self.view.show_error(message)
        self.view.update_status_bar(message="Error loading IOD modules.")

    def run(self) -> None:
        """Show the main application window and start the user interface."""
        self.view.show()

    def _build_qt_tree_model(
        self, iod_list: list[tuple[str, str, str, str]], favorites_manager: object = None
    ) -> QStandardItemModel:
        """Convert a list of IOD module tuples into a QStandardItemModel for use with a QTreeView.

        Args:
            iod_list (List[Tuple[str, str, str, str]] or None): List of IODs as (name, table_id, href, iod_type).
            favorites_manager: Instance to check if a table_id is a favorite.

        Returns:
            QStandardItemModel: The model ready to be set on a QTreeView.

        """
        model = QStandardItemModel()
        model.setHorizontalHeaderLabels(["Name", "Kind", "", "♥"])

        is_favorite = ""
        for title, table_id, href, iod_type in iod_list:
            title_item = QStandardItem(title)
            kind_item = QStandardItem(iod_type)
            usage_item = QStandardItem("")  # Usage column is empty for now
            favorite_item = QStandardItem(is_favorite)

            # Store table_id and iod_type as data for later retrieval
            title_item.setData(table_id, role=Qt.UserRole)
            kind_item.setData(iod_type, role=Qt.UserRole + 1)

            model.appendRow([title_item, kind_item, usage_item, favorite_item])

        return model
