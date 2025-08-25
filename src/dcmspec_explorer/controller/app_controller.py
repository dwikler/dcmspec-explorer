"""Controller class for the DCMspec Explorer application."""

import time
import threading
from typing import Any, Optional
import warnings
import contextlib


from PySide6.QtCore import Qt, QTimer, QObject, QModelIndex, QUrl
from PySide6.QtGui import QStandardItem

from dcmspec.progress import Progress

from dcmspec_explorer.app_config import load_app_config, setup_logger
from dcmspec_explorer.model.model import DICOM_TYPE_MAP, DICOM_USAGE_MAP
from dcmspec_explorer.model.model import Model
from dcmspec_explorer.model.model import IODEntry
from dcmspec_explorer.services.service_mediator import IODListLoaderServiceMediator, IODModelLoaderServiceMediator
from dcmspec_explorer.view.load_iod_dialog import LoadIODDialog
from dcmspec_explorer.view.main_window import MainWindow
from dcmspec_explorer.controller.iod_treeview_adapter import IODTreeViewModelAdapter


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

        # Initialize the service mediators
        self.service = IODListLoaderServiceMediator(self.model, self.logger, parent=self)
        self.iod_model_service = IODModelLoaderServiceMediator(self.model, self.logger, parent=self)

        # Use QTimer to ensure the treeview is only initialized after the window is shown
        QTimer.singleShot(0, self.initialize_treeview)

        # Connect UI elements to handlers
        self.view.header_clicked.connect(self._on_treeview_header_clicked)
        self.view.search_text_changed.connect(self._on_search_text_changed)
        self.view.iod_treeview_item_selected.connect(self._on_treeview_item_clicked)
        self.view.ui.detailsTextBrowser.anchorClicked.connect(self._on_details_link_clicked)

        # Initialize sorting state
        self.sort_column: Optional[int] = None  # No sorting on first load
        self.sort_reverse: bool = False

        self._iodmodel_loaded_call_count = 0

    def run(self) -> None:
        """Show the main application window and start the user interface."""
        self.view.show()

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
        self.service.iodlist_progress_signal.connect(self._handle_iodlist_progress, Qt.QueuedConnection)
        self.service.iodlist_loaded_signal.connect(self._handle_iodlist_loaded, Qt.QueuedConnection)
        self.service.iodlist_error_signal.connect(self._handle_iodlist_error, Qt.QueuedConnection)

    def _on_search_text_changed(self, text: str) -> None:
        """Handle search box text change and update filtering."""
        self.apply_filter_and_sort()

    def _on_treeview_item_clicked(self, index: QModelIndex) -> None:
        """Handle selection of a treeview item."""
        model = index.model()
        if not model:
            return

        selected_item_name = model.itemFromIndex(index.siblingAtColumn(0))
        selected_item_kind = model.itemFromIndex(index.siblingAtColumn(1))

        # Retrieve the node path from the selected item data
        selected_item_node_path = selected_item_name.data(Qt.UserRole) if selected_item_name else None

        # Check the clicked item level and take appropriate action
        if index.parent().isValid() is False:
            # top-level (IOD)
            self._handle_iod_item_clicked(index, selected_item_name, selected_item_kind)

        elif index.parent().parent().isValid() is False:
            # second-level (Module)
            self._handle_module_item_clicked(selected_item_node_path)

        else:
            # third-level (Attribute)
            self._handle_attribute_item_clicked(selected_item_node_path)

    def _safe_disconnect(self, *signals: Any) -> None:
        """Safely disconnect all slots from the given Qt signals, suppressing warnings.

        In PySide6/Qt, connecting the same slot to a signal multiple times results in multiple calls.
        This helper ensures that all previous connections are removed before reconnecting, which is
        especially important for signals connected dynamically in response to user actions.

        Args:
            signals: One or more Qt signal objects to disconnect.

        Note:
            PySide6 does not deduplicate signal connections automatically. This method avoids
            duplicate slot calls and suppresses harmless RuntimeWarnings if a signal is already disconnected.

        """
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", category=RuntimeWarning)
            for sig in signals:
                with contextlib.suppress(TypeError):
                    sig.disconnect()

    def _handle_iod_item_clicked(
        self, index: QModelIndex, selected_item_name: QStandardItem, selected_item_kind: QStandardItem
    ) -> None:
        """Handle click on a top-level (IOD) item."""
        # Update contents of the details panel
        table_id = selected_item_name.data(Qt.UserRole) if selected_item_name else None
        table_url = selected_item_name.data(Qt.UserRole + 1) if selected_item_name else None
        table_ref = table_id.split("table_", 1)[-1] if table_id and table_id.startswith("table_") else table_id
        html = f"""<h1>{selected_item_name.text()} IOD</h1>
                <p><span class="label">IOD Kind:</span> {selected_item_kind.text() if selected_item_kind else ""}</p>
                <p>See <a href="{table_url}">PS3.3 Table {table_ref}</a></p>
                """
        self.view.set_details_html(html)

        # Stop here if children are already populated
        if selected_item_name.hasChildren() and selected_item_name.rowCount() > 0:
            return

        # Update status bar message and display progress dialog
        self.view.update_status_bar(message="Loading IOD specification...")
        self.progress_dialog = LoadIODDialog(self.view)
        self.progress_dialog.show()
        self.view.ui.iodTreeView.setEnabled(False)

        # Start the IOD model loader worker in a background thread
        self._iod_model_worker, self._iod_model_thread = self.iod_model_service.start_iodmodel_worker(table_id)

        # Disconnect previous signal connections to avoid duplicate handlers
        self._safe_disconnect(
            self.iod_model_service.iodmodel_progress_signal,
            self.iod_model_service.iodmodel_loaded_signal,
            self.iod_model_service.iodmodel_error_signal,
        )

        # Connect signals to handlers for progress, loaded, and error
        self.iod_model_service.iodmodel_progress_signal.connect(self._handle_iodmodel_progress, Qt.QueuedConnection)
        # table_id is captured at lambda creation time as it may be out-of-scope by the time the lambda is executed
        self.iod_model_service.iodmodel_loaded_signal.connect(
            lambda sender, iod_model, table_id=table_id: self._handle_iodmodel_loaded(
                sender,
                iod_model,
                table_id,  # pass selected item table_id to recover item selection in rebuilt treeview
            ),
            Qt.QueuedConnection,
        )
        self.iod_model_service.iodmodel_error_signal.connect(self._handle_iodmodel_error, Qt.QueuedConnection)

        # Set expand property for the selected iod item in the view (will be effective when item will be populated)
        self.view.ui.iodTreeView.expand(index)

    def _handle_module_item_clicked(self, selected_item_path: str) -> None:
        """Handle click on a second-level (Module) item."""
        # Get attribute details from the model using only the node_path
        details = self.model.get_node_details(selected_item_path)

        if details:
            ie = details.get("ie", "Unspecified")
            usage = details.get("usage", "")
            usage_display = DICOM_USAGE_MAP.get(usage, f"Other ({usage})")
            html = f"""<h1>{details.get("module", "Unknown")} Module</h1>
                <p><span class="label">IE:</span> {ie}</p>
                <p><span class="label">Usage:</span> {usage_display}</p>
                <p><span class="label">Reference:</span> {details.get("ref", "")}</p>
                """
        else:
            # Fallback: only show the attribute path
            html = f"""<h1>{selected_item_path} Module</h1>"""
        self.view.set_details_html(html)

    def _handle_attribute_item_clicked(self, selected_item_path: str) -> None:
        """Handle click on a third-level or deeper (Attribute) item."""
        # Get attribute details from the model using only the node_path
        details = self.model.get_node_details(selected_item_path)

        if details:
            elem_type = details.get("elem_type", "Unspecified")
            type_display = DICOM_TYPE_MAP.get(elem_type, f"Other ({elem_type})")
            html = f"""<h1>{details.get("elem_name", "Unknown")} Attribute</h1>
                <p><span class="label">Tag:</span> {details.get("elem_tag", "")}</p>
                <p><span class="label">Type:</span> {type_display}</p>
                <p><span class="label">Description:</span> {details.get("elem_description", "")}</p>
                """
        else:
            # Fallback: only show the attribute path
            html = f"""<h1>{selected_item_path} Attribute</h1>"""
        self.view.set_details_html(html)

    def _handle_iodlist_progress(self, sender: object, progress: Progress) -> None:
        percent = progress.percent
        if percent == -1:
            self.logger.debug("Unknown progress received (-1).")
            self.view.update_status_bar(message="Loading IOD modules... (unknown progress)")
        elif percent % 10 == 0 or percent == 100:
            self.logger.debug(f"Progress update: {percent}%")
            self.view.update_status_bar(f"Loading IOD modules... {percent}%")

    def _handle_iodlist_loaded(self, sender: object, iod_entry_list: list[IODEntry]) -> None:
        # Initialize the mapping of already loaded iods (AnyTree node content added to treeview) by their table_id
        self._iod_children_loaded = {}

        # Populate the tree model with the loaded IODs applying filters and sorting
        self.apply_filter_and_sort(iod_entry_list=iod_entry_list)

        # Update the version label with the model's version
        if self.model.version:
            self.view.ui.versionLabel.setText(f"Version: {self.model.version}")
        self.view.update_status_bar(message=f"Listed {len(iod_entry_list)} IODs.")

    def _handle_iodlist_error(self, sender: object, message: str) -> None:
        self.logger.error(f"Error signal received from {sender}: {message}")
        self.view.show_error(message)
        self.view.update_status_bar(message="Error loading IOD modules.")

    def _handle_iodmodel_progress(self, sender: object, progress: Progress) -> None:
        status = progress.status
        percent = progress.percent
        step = progress.step
        total_steps = progress.total_steps
        percent = progress.percent
        self.logger.debug(
            f"IOD model progress update: status={status}, step={step}, total_steps={total_steps}, percent={percent}%"
        )

        # Update the progress dialog
        if hasattr(self, "progress_dialog") and self.progress_dialog:
            self.progress_dialog.update_step(status, percent)

    def _handle_iodmodel_loaded(self, sender: object, iod_model: object, table_id: str) -> None:
        self.logger.debug(
            f"CALL _handle_iodmodel_loaded: table_id={table_id}, "
            f"time={time.time()}, thread={threading.current_thread().name}"
        )
        if iod_model and hasattr(iod_model, "content"):
            # Add the loaded IOD content to the model
            self.model.add_iod_spec_content(table_id, iod_model.content)

            # Remember that this IOD's children are loaded
            if not hasattr(self, "_iod_children_loaded"):
                self._iod_children_loaded = {}
            self._iod_children_loaded[table_id] = iod_model.content

            # Find the parent item in the current model
            model = self.view.ui.iodTreeView.model()
            parent_item_in_model = None
            for row in range(model.rowCount()):
                item = model.item(row, 0)
                self.logger.debug(
                    f"Checking row {row}: item.data(Qt.UserRole)={item.data(Qt.UserRole)}, expected table_id={table_id}"
                )
                if item.data(Qt.UserRole) == table_id:
                    parent_item_in_model = item
                    self.logger.debug(f"Found parent item in model for table_id={table_id} at row {row}.")
                    break

            if parent_item_in_model is not None:
                self.logger.debug(
                    f"Populating children for parent_item_in_model: {parent_item_in_model.text()} (table_id={table_id})"
                )
                IODTreeViewModelAdapter.populate_treeview_model_item(parent_item_in_model, iod_model.content)
            else:
                # Debug info to help diagnose why the parent is not found
                current_filter = self.view.ui.searchLineEdit.text()
                model_table_ids = [model.item(row, 0).data(Qt.UserRole) for row in range(model.rowCount())]
                self.logger.debug(
                    f"Parent IOD not found in model. "
                    f"table_id: {table_id}, "
                    f"current_filter: '{current_filter}', "
                    f"model_table_ids: {model_table_ids}"
                )
                self.view.show_error("The selected IOD is no longer visible. Please clear the filter and try again.")

            # Hide progress dialog and re-enable treeview
            if hasattr(self, "progress_dialog") and self.progress_dialog:
                self.progress_dialog.accept()
                self.progress_dialog = None
            self.view.ui.iodTreeView.setEnabled(True)
            self.view.update_status_bar(message="IOD specification loaded.")

    def _handle_iodmodel_error(self, sender: object, message: str) -> None:
        self.logger.error(f"Error loading IOD model: {message}")
        # Hide progress dialog and re-enable treeview
        if hasattr(self, "progress_dialog") and self.progress_dialog:
            self.progress_dialog.reject()
            self.progress_dialog = None
        self.view.ui.iodTreeView.setEnabled(True)
        self.view.show_error(message)
        self.view.update_status_bar(message="Error loading IOD specification.")

    def _on_details_link_clicked(self, url: QUrl) -> None:
        """Handle clicks on links in the detailsTextBrowser."""
        url_str = url.toString()
        if (url.scheme() == "" and url.host() == "" and url.fragment()) or url_str.startswith("#"):
            self.view.show_anchor_link_warning_dialog(url_str)
        else:
            self.view.show_url_link_warning_dialog(url_str)

    def apply_filter_and_sort(self, iod_entry_list: Optional[list[IODEntry]] = None) -> None:
        """Apply current search filter and sort to the IOD list and update the treeview."""
        # Save current selection (by table_id)
        selection_model = self.view.ui.iodTreeView.selectionModel()
        selected_table_id = None
        if selection_model and selection_model.hasSelection():
            index = selection_model.currentIndex()
            model = index.model()
            selected_item = model.itemFromIndex(index.siblingAtColumn(0))
            if selected_item:
                selected_table_id = selected_item.data(Qt.UserRole)

        # Use the provided IODEntry list if given, otherwise fall back to model property
        iod_entry_list = iod_entry_list if iod_entry_list is not None else self.model.iod_list
        search_text = self.view.ui.searchLineEdit.text()
        sort_column = self.sort_column
        sort_reverse = self.sort_reverse
        loaded_children = getattr(self, "_iod_children_loaded", {})

        qt_tree_model, selected_row = IODTreeViewModelAdapter.build_treeview_model(
            iod_entry_list=iod_entry_list,
            search_text=search_text,
            sort_column=sort_column,
            sort_reverse=sort_reverse,
            loaded_children=loaded_children,
            selected_table_id=selected_table_id,
        )

        self.view.update_treeview(qt_tree_model)

        # Restore selection if possible
        if selected_row is not None:
            item = qt_tree_model.item(selected_row, 0)
            index = qt_tree_model.indexFromItem(item)
            self.view.ui.iodTreeView.setCurrentIndex(index)

    def _on_treeview_header_clicked(self, logical_index: int) -> None:
        """Handle clicks on the treeview column headers for sorting."""
        # Only allow sorting on Name (0) and Kind (1)
        if logical_index not in (0, 1):
            self.logger.info("Sorting is only supported on Name and Kind columns.")
            return

        if self.sort_column == logical_index:
            self.sort_reverse = not self.sort_reverse  # descending if True, ascending if False
        else:
            self.sort_column = logical_index
            self.sort_reverse = False

        # Update the sort indicator in the view
        self.view.update_treeview_sort_indicator(self.sort_column, self.sort_reverse)

        self.apply_filter_and_sort()
