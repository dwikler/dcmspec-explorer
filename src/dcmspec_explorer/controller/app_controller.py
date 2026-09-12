"""Controller class for the DCMspec Explorer application."""

import html
import os
import re
import threading
from typing import Any, List, Optional, cast
import warnings
import contextlib


from PySide6.QtCore import Qt, QTimer, QObject, QModelIndex, QUrl
from PySide6.QtGui import QStandardItem, QStandardItemModel
from PySide6.QtWidgets import QMenu

from dcmspec.progress import Progress

from dcmspec_explorer.app_config import load_app_config, setup_logger, parse_bool

from dcmspec_explorer.model.model import DICOM_TYPE_MAP, DICOM_USAGE_MAP
from dcmspec_explorer.model.model import Model
from dcmspec_explorer.model.model import IODEntry

from dcmspec_explorer.services.service_mediator import (
    IODListLoaderServiceMediator,
    IODModelLoaderServiceMediator,
    IODExportServiceMediator,
    SectionLoaderServiceMediator,
)
from dcmspec_explorer.services.favorites_manager import FavoritesManager

from dcmspec_explorer.view.load_iod_dialog import LoadIODDialog
from dcmspec_explorer.view.main_window import MainWindow

from dcmspec_explorer.controller.iod_treeview_adapter import (
    IODTreeViewModelAdapter,
    TABLE_ID_ROLE,
    TABLE_URL_ROLE,
    NODE_PATH_ROLE,
)


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

        # Initialize the favorites manager
        self.favorites_manager = FavoritesManager(self.config, self.logger)
        # Initialize the treeview adapter with favorites manager
        self.treeview_adapter = IODTreeViewModelAdapter(
            favorites_manager=self.favorites_manager,
            heart_icon=self.view.get_heart_icon(),
            cached_icon=self.view.get_cached_icon(),
            uncached_icon=self.view.get_uncached_icon(),
        )
        # Initialize the favorites view state from config
        self.show_favorites_only = parse_bool(self.config.get_param("show_favorites_on_start"))
        self.view.set_show_favorites_button_label(self.show_favorites_only)

        # Initialize the service mediators
        self.service = IODListLoaderServiceMediator(self.model, self.logger, parent=self)
        self.iod_model_service = IODModelLoaderServiceMediator(self.model, self.logger, parent=self)
        self.export_service = IODExportServiceMediator(self.model, self.logger, parent=self)
        self.section_service = SectionLoaderServiceMediator(self.model, self.logger, parent=self)

        # Let the explanation drawer resolve a section's relative image paths against the standard cache
        self.view.set_explanation_image_search_paths([os.path.join(self.config.cache_dir, "standard")])

        # Use QTimer to ensure the treeview is only initialized after the window is shown
        QTimer.singleShot(0, self.initialize_treeview)

        # Connect UI elements to handlers
        self.view.header_clicked.connect(self._on_treeview_header_clicked)
        self.view.search_text_changed.connect(self._on_search_text_changed)
        self.view.iod_treeview_item_selected.connect(self._on_treeview_item_clicked)
        self.view.iod_treeview_right_click.connect(self._on_treeview_right_click)
        self.view.details_link_clicked.connect(self._on_details_link_clicked)
        self.view.explanation_link_clicked.connect(self._on_explanation_link_clicked)
        self.view.explanation_toggle_clicked.connect(self._on_explanation_toggle_clicked)
        self.view.toggle_favorite_display_clicked.connect(self._on_toggle_favorite_display_clicked)
        self.view.check_for_updates_clicked.connect(self._on_check_for_updates_clicked)
        self.view.export_csv_action_triggered.connect(lambda: self._export_selected_iod("csv"))
        self.view.export_xlsx_action_triggered.connect(lambda: self._export_selected_iod("xlsx"))
        self.view.toggle_favorite_state_action_triggered.connect(self._on_toggle_favorite_state_action_triggered)
        self.view.file_menu_about_to_show.connect(self._on_file_menu_about_to_show)

        # Initialize sorting state
        self.sort_column: Optional[int] = None  # No sorting on first load
        self.sort_reverse: bool = False

        # Initialize progress dialog attribute (None when not used)
        self.progress_dialog: Optional[LoadIODDialog] = None

        self._iodmodel_loaded_call_count = 0

        # State for the currently selected attribute's explanatory section drawer
        self._current_table_id: Optional[str] = None
        self._current_relative_path: Optional[str] = None
        self._current_section_refs: List[str] = []
        self._explanation_loaded_section_id: Optional[str] = None
        self._explanation_has_content: bool = False

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

        # Connect signals for progress, loaded, and error
        self._connect_iodlist_signals()

    def _on_search_text_changed(self, text: str) -> None:
        """Handle search box text change and update filtering."""
        self.apply_filter_and_sort()

    def _on_toggle_favorite_display_clicked(self):
        """Toggle between showing all IODs and only favorites."""
        self.show_favorites_only = not self.show_favorites_only
        self.view.set_show_favorites_button_label(self.show_favorites_only)
        self.apply_filter_and_sort()

    def _on_treeview_item_clicked(self, index: QModelIndex) -> None:
        """Handle selection of a treeview item."""
        model = cast(Optional[QStandardItemModel], index.model())
        if not model:
            return

        selected_item_name = model.itemFromIndex(index.siblingAtColumn(0))
        selected_item_kind = model.itemFromIndex(index.siblingAtColumn(1))

        # Check the clicked item level and take appropriate action
        if index.parent().isValid() is False:
            # top-level (IOD)
            self._handle_iod_item_clicked(index, selected_item_name, selected_item_kind)

        elif index.parent().parent().isValid() is False:
            # second-level (Module)
            parent_index = index.parent()
            parent_kind_item = model.itemFromIndex(parent_index.siblingAtColumn(1))
            iod_kind = parent_kind_item.text() if parent_kind_item else "Unknown"
            details = self.get_selected_item_details(selected_item_name)
            if details is not None:
                self._handle_module_item_clicked(details, iod_kind)
            else:
                self.view.set_nodetails_html(selected_item_name, "Module")

        else:
            # third-level (Attribute)
            table_id = self.treeview_adapter.get_table_id_for_item(selected_item_name)
            details = self.get_selected_item_details(selected_item_name)
            if details is not None:
                self._current_relative_path = self._relative_path_for_item(selected_item_name)
                self._handle_attribute_item_clicked(details, table_id)
            else:
                self.view.set_nodetails_html(selected_item_name, "Attribute")

    @staticmethod
    def _relative_path_for_item(selected_item: QStandardItem) -> str:
        """Return the relative path (from the SpecModel root) for a treeview item's NODE_PATH_ROLE."""
        full_path = selected_item.data(NODE_PATH_ROLE) or ""
        path_parts = full_path.split("/") if full_path else []
        # Skip "content" if present
        if path_parts and path_parts[0] == "content":
            return "/".join(path_parts[1:])
        return full_path

    def get_selected_item_details(self, selected_item: QStandardItem) -> Optional[dict]:
        """Return SpecModel node attributes for the selected treeview item."""
        table_id = self.treeview_adapter.get_table_id_for_item(selected_item)
        if table_id is None:
            return None
        relative_path = self._relative_path_for_item(selected_item)
        return self.model.get_node_public_attrs(table_id, relative_path)

    def _on_treeview_right_click(self, index: QModelIndex, global_pos):
        """Show context menu for favorites management and export on top-level items."""
        model = cast(QStandardItemModel, index.model())
        item = model.itemFromIndex(index.siblingAtColumn(0))
        table_id = item.data(TABLE_ID_ROLE)

        # Do not show context menu if table_id is None
        if table_id is None:
            self.logger.warning("Context menu requested for item with no table_id; ignoring.")
            return

        # Create context menu for favorites management
        menu = QMenu(self.view)
        action = menu.addAction(self._favorite_action_label(table_id))
        # Connect to the signal triggered if the user selects the action
        action.triggered.connect(lambda: self._toggle_favorite(table_id))

        # Add an export submenu, enabled only once this IOD's specmodel has been loaded
        iod_name = item.text()
        export_menu = menu.addMenu("Export")
        csv_action = export_menu.addAction("CSV...")
        xlsx_action = export_menu.addAction("Excel...")
        is_loaded = self._is_iod_loaded(table_id)
        export_menu.setEnabled(is_loaded)
        if not is_loaded:
            export_menu.menuAction().setToolTip("Select this IOD first to load it")
        csv_action.triggered.connect(lambda: self._export_iod_model(table_id, iod_name, "csv"))
        xlsx_action.triggered.connect(lambda: self._export_iod_model(table_id, iod_name, "xlsx"))

        menu.exec(global_pos)

    def _favorite_action_label(self, table_id: str) -> str:
        """Return the appropriate favorite toggle label for the given IOD's current favorite state."""
        return "Remove from favorites" if self.favorites_manager.is_favorite(table_id) else "Add to favorites"

    def _is_iod_loaded(self, table_id: str) -> bool:
        """Return whether the given IOD's spec model has already been loaded."""
        return table_id in self.model.iod_specmodels

    def _export_selected_iod(self, fmt: str) -> None:
        """Export the treeview's currently selected IOD, triggered from the File > Export menu."""
        selected = self.view.get_selected_iod()
        if selected is None:
            return
        table_id, iod_name = selected
        self._export_iod_model(table_id, iod_name, fmt)

    def _on_toggle_favorite_state_action_triggered(self) -> None:
        """Toggle favorite status for the treeview's currently selected IOD, triggered from the File menu."""
        selected = self.view.get_selected_iod()
        if selected is None:
            return
        table_id, _ = selected
        self._toggle_favorite(table_id)

    def _on_file_menu_about_to_show(self) -> None:
        """Refresh the Export and favorite items' enabled state to match the currently selected IOD."""
        selected = self.view.get_selected_iod()
        if selected is None:
            self.view.set_export_menu_enabled(False, "Select an IOD first")
            self.view.set_favorite_action(enabled=False, is_favorite=False)
            return
        table_id, _ = selected
        is_loaded = self._is_iod_loaded(table_id)
        tooltip = "" if is_loaded else "Select this IOD first to load it"
        self.view.set_export_menu_enabled(is_loaded, tooltip)
        self.view.set_favorite_action(enabled=True, is_favorite=self.favorites_manager.is_favorite(table_id))

    @staticmethod
    def _normalize_export_filename(name: str) -> str:
        """Replace filesystem-unsafe characters and spaces in a proposed export filename with underscores."""
        name = re.sub(r'[\\/:*?"<>|]', "_", name.strip())
        return re.sub(r"\s+", "_", name) or "export"

    def _export_iod_model(self, table_id: str, iod_name: str, fmt: str) -> None:
        """Prompt for a destination file and export the given IOD's spec model in the given format."""
        if fmt == "xlsx":
            extension, file_filter = "xlsx", "Excel files (*.xlsx)"
        else:
            extension, file_filter = "csv", "CSV files (*.csv)"
        default_name = f"{self._normalize_export_filename(iod_name)}.{extension}"

        path = self.view.prompt_save_file("Export IOD", default_name, file_filter)
        if path is None:
            return

        self.view.update_status_bar(message="Exporting...")
        self.export_service.start_export_worker(
            iod_model=self.model.iod_specmodels[table_id], fmt=fmt, output_path=path
        )
        self._connect_export_signals()

    def _connect_export_signals(self):
        """(Re)connect IOD export signals to their handlers, safely disconnecting first."""
        self._connect_signals(
            [
                (self.export_service.iodexport_loaded_signal, self._handle_export_loaded),
                (self.export_service.iodexport_error_signal, self._handle_export_error),
            ]
        )

    def _handle_export_loaded(self, sender: object, output_path: str) -> None:
        """Update the status bar once an export finishes successfully."""
        self.view.update_status_bar(message=f"Exported to {output_path}")

    def _handle_export_error(self, sender: object, message: str) -> None:
        """Log the error and show it to the user when an export fails."""
        self._report_error(sender, message, status_bar_message="Error exporting IOD.")

    def _report_error(self, sender: object, message: str, status_bar_message: str) -> None:
        """Log an error received via an error signal, then show it to the user and on the status bar."""
        self.logger.error(f"Error signal received from {sender}: {message}")
        self.view.show_error(message)
        self.view.update_status_bar(message=status_bar_message)

    def _on_check_for_updates_clicked(self):
        """Handle Check for Updates button click: force a fresh download of the IOD list from the web."""
        self.logger.info("Check for Updates button clicked: checking DICOM standard for updates.")
        self.view.update_status_bar(message="Downloading latest IOD modules from web...")
        # Start the worker in a background thread via the service mediator, forcing download
        self._treeview_worker, self._treeview_thread = self.service.start_iodlist_worker(force_download=True)
        # Connect signals for progress, loaded, and error
        self._connect_iodlist_signals()

    def _toggle_favorite(self, table_id):
        try:
            if self.favorites_manager.is_favorite(table_id):
                self.favorites_manager.remove_favorite(table_id)
            else:
                self.favorites_manager.add_favorite(table_id)
        except Exception as e:
            self.logger.error(f"Failed to toggle favorite for {table_id}: {e}")
            self.view.show_error("Failed to update favorites.")
        self.apply_filter_and_sort()

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

    def _connect_signals(self, signal_slot_pairs):
        """Safely (re)connect a set of Qt signals to their slots.

        Args:
            signal_slot_pairs: Iterable of (signal, slot) tuples.

        This helper ensures that signals are not connected multiple times by disconnecting previous connections first.
        This prevents duplicate slot calls.

        Note:
            By specifying Qt.ConnectionType.QueuedConnection, we ensure that if a signal is emitted from any thread,
            the connected slot (UI update method) will be executed in the thread that owns the receiver object.
            In this case, both the ServiceMediator and AppController live in the main thread, so UI updates
            are performed in the main thread, ensuring thread safety for all Qt UI operations.

        """
        signals = [pair[0] for pair in signal_slot_pairs]
        self._safe_disconnect(*signals)
        for signal, slot in signal_slot_pairs:
            signal.connect(slot, Qt.ConnectionType.QueuedConnection)

    def _connect_iodlist_signals(self):
        """(Re)connect IOD list loader signals to their handlers, safely disconnecting first."""
        self._connect_signals(
            [
                (self.service.iodlist_progress_signal, self._handle_iodlist_progress),
                (self.service.iodlist_loaded_signal, self._handle_iodlist_loaded),
                (self.service.iodlist_error_signal, self._handle_iodlist_error),
            ]
        )

    def _handle_iod_item_clicked(
        self, index: QModelIndex, selected_item_name: QStandardItem, selected_item_kind: QStandardItem
    ) -> None:
        """Handle click on a top-level (IOD) item."""
        # Update contents of the details panel
        table_id = selected_item_name.data(TABLE_ID_ROLE) if selected_item_name else None
        table_url = selected_item_name.data(TABLE_URL_ROLE) if selected_item_name else None
        table_ref = table_id.split("table_", 1)[-1] if table_id and table_id.startswith("table_") else table_id
        html = f"""<h1>{selected_item_name.text()} IOD</h1>
                <p><span class="label">IOD Kind:</span> {selected_item_kind.text() if selected_item_kind else ""}</p>
                <p>See <a href="{table_url}">PS3.3 Table {table_ref}</a></p>
                """
        self.view.set_details_html(html)
        self.view.show_explanation_toggle(False)

        # Stop here if children are already populated
        if selected_item_name.hasChildren() and selected_item_name.rowCount() > 0:
            return

        self._start_iod_model_load(table_id)

        # Set expand property for the selected iod item in the view (will be effective when item will be populated)
        self.view.ui.iodTreeView.expand(index)

    def _start_iod_model_load(self, table_id: str, force_rebuild: bool = False) -> None:
        """Start (or force-reload) an IOD model load in the background and wire up its handlers.

        Used both for a top-level IOD's first load and for an explicit reload triggered from the
        explanatory section drawer (e.g. to pick up section references missing from an older cache).
        """
        self.view.show_explanation_toggle(False)

        # Update status bar message and display progress dialog
        self.view.update_status_bar(message="Loading IOD specification...")
        self.progress_dialog = LoadIODDialog(self.view)
        self.progress_dialog.show()
        self.view.ui.iodTreeView.setEnabled(False)

        # Start the IOD model loader worker in a background thread
        self._iod_model_worker, self._iod_model_thread = self.iod_model_service.start_iodmodel_worker(
            table_id, force_rebuild=force_rebuild
        )

        # Disconnect previous signal connections to avoid duplicate handlers
        self._safe_disconnect(
            self.iod_model_service.iodmodel_progress_signal,
            self.iod_model_service.iodmodel_loaded_signal,
            self.iod_model_service.iodmodel_error_signal,
        )

        # Connect signals to handlers for progress, loaded, and error
        self.iod_model_service.iodmodel_progress_signal.connect(
            self._handle_iodmodel_progress, Qt.ConnectionType.QueuedConnection
        )
        # table_id is captured at lambda creation time as it may be out-of-scope by the time the lambda is executed
        self.iod_model_service.iodmodel_loaded_signal.connect(
            lambda sender, iod_model, table_id=table_id: self._handle_iodmodel_loaded(
                sender,
                iod_model,
                table_id,  # pass selected item table_id to recover item selection in rebuilt treeview
            ),
            Qt.ConnectionType.QueuedConnection,
        )
        self.iod_model_service.iodmodel_error_signal.connect(
            self._handle_iodmodel_error, Qt.ConnectionType.QueuedConnection
        )

    def _handle_module_item_clicked(self, details: dict, iod_kind: str) -> None:
        """Handle click on a second-level (Module) item."""
        ie = details.get("ie", "Unspecified")
        usage = details.get("usage", "")
        usage_display = DICOM_USAGE_MAP.get(usage, f"Other ({usage})")
        description = details.get("description", "")
        ref_html = details.get("ref", "")
        ref_text = self.model.get_module_ref_link(ref_html) if ref_html else ""

        if iod_kind == "Composite":
            html = f"""<h1>{details.get("module", "Unknown")} Module</h1>
                <p><span class="label">IE:</span> {ie}</p>
                <p><span class="label">Usage:</span> {usage_display}</p>
                <p><span class="label">Reference:</span> {ref_text}</p>
                """
        else:
            html = f"""<h1>{details.get("module", "Unknown")} Module</h1>
                <p><span class="label">Reference:</span> {ref_text}</p>
                <p><span class="label">Description:</span> {description}</p>
                """

        self.view.set_details_html(html)
        self.view.show_explanation_toggle(False)

    def _handle_attribute_item_clicked(self, details: dict, table_id: Optional[str]) -> None:
        """Handle click on a third-level or deeper (Attribute) item."""
        elem_type = details.get("elem_type", "Unspecified")
        type_display = DICOM_TYPE_MAP.get(elem_type, f"Other ({elem_type})")
        html = f"""<h1>{details.get("elem_name", "Unknown")} Attribute</h1>
            <p><span class="label">Tag:</span> {details.get("elem_tag", "")}</p>
            <p><span class="label">Type:</span> {type_display}</p>
            <p><span class="label">Description:</span> {details.get("elem_description", "")}</p>
            """
        self.view.set_details_html(html)

        self._current_table_id = table_id
        # Key name is derived by dcmspec from the elem_description column's own attribute name.
        self._current_section_refs = details.get("elem_description_section_refs") or []
        self._explanation_loaded_section_id = None
        self._explanation_has_content = False
        self.view.show_explanation_toggle(bool(self._current_section_refs))

    def _handle_iodlist_progress(self, sender: object, progress: Progress) -> None:
        percent = progress.percent
        if percent == -1:
            self.logger.debug("Unknown progress received (-1).")
            self.view.update_status_bar(message="Loading IOD modules... (unknown progress)")
        elif percent % 10 == 0 or percent == 100:
            self.logger.debug(f"Progress update: {percent}%")
            self.view.update_status_bar(f"Loading IOD modules... {percent}%")

    def _handle_iodlist_loaded(self, sender: object, iod_entry_list: list[IODEntry]) -> None:
        # Populate the tree model with the loaded IODs applying filters and sorting
        self.apply_filter_and_sort(iod_entry_list=iod_entry_list)

        # After repopulating the treeview, re-add children for IODs by using the loaded SpecModels
        if not self.model.new_version_available:
            model = self.view.ui.iodTreeView.model()
            for table_id, iod_model in self.model.iod_specmodels.items():
                if iod_model and hasattr(iod_model, "content") and iod_model.content:
                    self.treeview_adapter.populate_iod_entry_children(model, table_id, iod_model.content)

        # Update the version label with the model's version
        if self.model.version:
            self.view.ui.versionLabel.setText(f"Version: {self.model.version}")
        if self.model.new_version_available:
            self.view.show_info(
                "DICOM Standard List Updated",
                "The list of IODs for the new DICOM standard version has been loaded.<br><br>"
                "Please expand IODs to download the new version and load their details.",
            )
            self.view.update_status_bar(
                message="IOD list updated for new DICOM version. Expand an IOD to download and view its details."
            )
        else:
            self.view.update_status_bar(message=f"Listed {len(iod_entry_list)} IODs.")

    def _handle_iodlist_error(self, sender: object, message: str) -> None:
        self._report_error(sender, message, status_bar_message="Error loading IOD modules.")

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
        if iod_model and hasattr(iod_model, "content"):
            # Find the parent item in the current treeview model
            model = self.view.ui.iodTreeView.model()
            success = self.treeview_adapter.populate_iod_entry_children(model, table_id, iod_model.content)
            if not success:
                self.view.show_error("The selected IOD is no longer visible. Please clear the filter and try again.")

            # Hide progress dialog and re-enable treeview
            if hasattr(self, "progress_dialog") and self.progress_dialog:
                self.progress_dialog.accept()
                self.progress_dialog = None
            self.view.ui.iodTreeView.setEnabled(True)
            self.view.update_status_bar(message="IOD specification loaded.")
            self._refresh_selected_attribute_after_load(table_id)

    def _refresh_selected_attribute_after_load(self, table_id: str) -> None:
        """Re-render the currently selected attribute's details after its IOD was (re)loaded.

        Keeps the details pane and drawer from showing stale pre-reload content when the load
        was triggered while that attribute was already selected (e.g. via the drawer's "Reload
        this IOD" link) -- a no-op otherwise, since _current_table_id only matches when so.
        """
        if self._current_table_id != table_id or not self._current_relative_path:
            return
        details = self.model.get_node_public_attrs(table_id, self._current_relative_path)
        if details is not None:
            self._handle_attribute_item_clicked(details, table_id)

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
        """Handle clicks on links in the details pane, routing section references to the drawer."""
        url_str = url.toString()
        is_same_page_anchor = (url.scheme() == "" and url.host() == "" and url.fragment()) or url_str.startswith("#")
        if url.scheme() == "reload":
            self._on_reload_iod_link_clicked(url.path())
        elif is_same_page_anchor:
            section_id = url.fragment()
            if section_id in self._current_section_refs:
                self._on_section_link_clicked(section_id)
            else:
                self._show_section_unavailable()
        else:
            self.view.show_url_link_warning_dialog(url_str)

    def _on_explanation_link_clicked(self, url: QUrl) -> None:
        """Handle clicks on links within a rendered explanatory section's own content.

        Links in explanation area are not resolved as in attributes details if referencing a section
        and are handled as generic links (except the special reload link)
        """
        url_str = url.toString()
        if url.scheme() == "reload":
            self._on_reload_iod_link_clicked(url.path())
        elif (url.scheme() == "" and url.host() == "" and url.fragment()) or url_str.startswith("#"):
            self.view.show_anchor_link_warning_dialog(url_str)
        else:
            self.view.show_url_link_warning_dialog(url_str)

    def _on_explanation_toggle_clicked(self) -> None:
        """Handle a click on the explanation drawer's toggle button.

        Loads (and expands) the current attribute's first referenced section if the drawer has no
        content yet (nothing loaded, and no "unavailable" message either), otherwise just toggles
        whatever's currently shown (loaded section, unavailable message, or an error) open/closed.
        """
        if self._explanation_has_content:
            self.view.set_explanation_expanded(not self.view.is_explanation_expanded())
        elif self._current_section_refs:
            self._on_section_link_clicked(self._current_section_refs[0])

    def _on_section_link_clicked(self, section_id: str) -> None:
        """Load (if needed) and show the given explanatory section in the drawer."""
        if section_id == self._explanation_loaded_section_id:
            self.view.set_explanation_expanded(True)
            return

        self.view.show_explanation_toggle(True)
        self.view.set_explanation_html("<p><em>Loading explanatory section&hellip;</em></p>")
        self._explanation_has_content = True

        self._section_worker, self._section_thread = self.section_service.start_section_worker(section_id)

        self._safe_disconnect(
            self.section_service.section_loaded_signal,
            self.section_service.section_error_signal,
        )
        self.section_service.section_loaded_signal.connect(
            lambda sender, section_model, section_id=section_id: self._handle_section_loaded(
                sender, section_model, section_id
            ),
            Qt.ConnectionType.QueuedConnection,
        )
        self.section_service.section_error_signal.connect(
            self._handle_section_error, Qt.ConnectionType.QueuedConnection
        )

    def _handle_section_loaded(self, sender: object, section_model: Any, section_id: str) -> None:
        """Render a successfully loaded explanatory section's HTML in the drawer."""
        self._explanation_loaded_section_id = section_id
        section_html = getattr(section_model.content, "html", "")
        self.view.set_explanation_html(section_html)

    def _handle_section_error(self, sender: object, message: str) -> None:
        """Show an explanatory section load failure inline in the drawer, not as a modal dialog."""
        self.logger.error(f"Error signal received from {sender}: {message}")
        self.view.set_explanation_html(f"<p>Could not load this explanatory section: {html.escape(message)}</p>")

    def _show_section_unavailable(self) -> None:
        """Show the drawer's 'not available in cache' message with a link to reload the current IOD."""
        if not self._current_table_id:
            return
        section_html = (
            "<p>This reference isn't available in your local cache yet "
            "(this IOD may have been loaded before this feature was added).</p>"
            f'<p><a href="reload:{self._current_table_id}">Reload this IOD</a></p>'
        )
        self.view.show_explanation_toggle(True)
        self.view.set_explanation_html(section_html)
        self._explanation_has_content = True

    def _on_reload_iod_link_clicked(self, table_id: str) -> None:
        """Force-reload the given IOD from source, e.g. to pick up newly available section references."""
        self._start_iod_model_load(table_id, force_rebuild=True)

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
                selected_table_id = selected_item.data(TABLE_ID_ROLE)

        # Use the provided IODEntry list if given, otherwise fall back to model property,
        # Filters the list if show favorites is selected
        all_iod_entry_list = iod_entry_list if iod_entry_list is not None else self.model.iod_list
        iod_entry_list_to_display = all_iod_entry_list
        if self.show_favorites_only:
            iod_entry_list_to_display = self.favorites_manager.filter_iod_entry_list(all_iod_entry_list)

        search_text = self.view.ui.searchLineEdit.text()
        sort_column = self.sort_column
        sort_reverse = self.sort_reverse

        qt_tree_model, selected_row = self.treeview_adapter.build_treeview_model(
            iod_entry_list=iod_entry_list_to_display,
            data_model=self.model,
            search_text=search_text,
            sort_column=sort_column,
            sort_reverse=sort_reverse,
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
        # Only allow sorting on Name and Kind
        if logical_index not in (MainWindow.COL_NAME, MainWindow.COL_KIND):
            self.logger.info("Sorting is only supported on Name and Kind columns.")
            # Hide the sort indicator if user clicks on a non-sortable column
            self.view.ui.iodTreeView.header().setSortIndicatorShown(False)
            return

        if self.sort_column != logical_index:
            self.sort_column = logical_index
            self.sort_reverse = False
        elif not self.sort_reverse:
            self.sort_reverse = True  # ascending -> descending
        else:
            # Descending -> unsorted: cycle back to the natural (unsorted) order
            self.sort_column = None
            self.sort_reverse = False

        # Update the sort indicator in the view
        if self.sort_column is None:
            self.view.ui.iodTreeView.header().setSortIndicatorShown(False)
        else:
            self.view.update_treeview_sort_indicator(self.sort_column, self.sort_reverse)

        self.apply_filter_and_sort()
