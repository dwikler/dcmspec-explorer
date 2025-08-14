"""Controller class for the DCMspec Explorer application."""

import threading

from PySide6.QtCore import Qt, QTimer, QObject, QThread
from PySide6.QtGui import QStandardItemModel, QStandardItem

from dcmspec_explorer.app_config import load_app_config, setup_logger
from dcmspec_explorer.model.model import Model
from dcmspec_explorer.view.main_window import MainWindow
from dcmspec_explorer.services.iod_loading_service import IODListLoaderWorker


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

    def __init__(self):
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

        # Use QTimer to ensure the treeview is only initialized after the window is shown
        QTimer.singleShot(0, self.initialize_treeview)

    def initialize_treeview(self):
        """Initialize the treeview with list of IODs using QThread and signals.

        Shows a progress loading message while data is being loaded.
        """
        self.view.update_status_bar("Loading IOD modules...")

        # Set up the worker and thread
        self._treeview_thread = QThread()
        self._treeview_worker = IODListLoaderWorker(self.model, logger=self.logger)
        self._treeview_worker.moveToThread(self._treeview_thread)

        # Connect signals
        self._treeview_thread.started.connect(self._treeview_worker.run)
        self._treeview_worker.finished.connect(self._on_treeview_loaded)
        self._treeview_worker.error.connect(self._on_treeview_error)
        self._treeview_worker.finished.connect(self._treeview_thread.quit)
        self._treeview_worker.finished.connect(self._treeview_worker.deleteLater)
        self._treeview_thread.finished.connect(self._treeview_thread.deleteLater)
        self._treeview_worker.error.connect(self._treeview_thread.quit)
        self._treeview_worker.error.connect(self._treeview_worker.deleteLater)
        self._treeview_worker.progress.connect(self._on_treeview_progress)

        # Start the thread
        self._treeview_thread.start()

    def _on_treeview_progress(self, percent):
        if percent == -1:
            self.view.update_status_bar("Loading IOD modules... (unknown progress)")
        elif percent % 10 == 0 or percent == 100:
            self.view.update_status_bar(f"Loading IOD modules... {percent}%")

    def _on_treeview_loaded(self, iod_modules):
        qt_tree_model = self._build_qt_tree_model(iod_modules)
        self.view.update_treeview(qt_tree_model)
        self.view.update_status_bar(f"Loaded {len(iod_modules)} IOD modules.")

    def _on_treeview_error(self, message):
        self.view.show_error(message)
        self.view.update_status_bar("Error loading IOD modules.")

    def run(self):
        """Show the main application window and start the user interface."""
        self.view.show()

    def _build_qt_tree_model(self, iod_list, favorites_manager=None):
        """Convert a list of IOD module tuples into a QStandardItemModel for use with a QTreeView.

        Args:
            iod_list (List[Tuple[str, str, str, str]] or None): List of IODs as (name, table_id, href, iod_type).
            favorites_manager: Instance to check if a table_id is a favorite.

        Returns:
            QStandardItemModel: The model ready to be set on a QTreeView.

        """
        model = QStandardItemModel()
        model.setHorizontalHeaderLabels(["Name", "Kind", "", "♥"])

        for title, table_id, href, iod_type in iod_list:
            title_item = QStandardItem(title)
            kind_item = QStandardItem(iod_type)
            usage_item = QStandardItem("")  # Usage column is empty for now
            # heart_icon = "♥" if favorites_manager.is_favorite(table_id) else ""
            heart_icon = ""
            favorite_item = QStandardItem(heart_icon)

            # Store table_id and iod_type as data for later retrieval
            title_item.setData(table_id, role=Qt.UserRole)
            kind_item.setData(iod_type, role=Qt.UserRole + 1)

            model.appendRow([title_item, kind_item, usage_item, favorite_item])

        return model
