"""Controller class for the DCMspec Explorer application."""

import threading

from anytree import PreOrderIter

from PySide6.QtCore import Qt, QTimer, QObject
from PySide6.QtGui import QStandardItemModel, QStandardItem

from dcmspec.progress import Progress

from dcmspec_explorer.app_config import load_app_config, setup_logger
from dcmspec_explorer.model.model import DICOM_TYPE_MAP, DICOM_USAGE_MAP
from dcmspec_explorer.model.model import Model
from dcmspec_explorer.services.service_mediator import IODListLoaderServiceMediator, IODModelLoaderServiceMediator
from dcmspec_explorer.view.load_iod_dialog import LoadIODDialog
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

        # Initialize the service mediators
        self.service = IODListLoaderServiceMediator(self.model, self.logger, parent=self)
        self.iod_model_service = IODModelLoaderServiceMediator(self.model, self.logger, parent=self)

        # Use QTimer to ensure the treeview is only initialized after the window is shown
        QTimer.singleShot(0, self.initialize_treeview)

        # Connect UI elements to handlers
        self.view.ui.iodTreeView.clicked.connect(self._on_treeview_item_clicked)

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

    def _on_treeview_item_clicked(self, index):
        """Handle selection of a treeview item."""
        model = index.model()
        if not model:
            return

        # Retrieve values from the selected treeview item columns
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

    def _handle_iod_item_clicked(self, index, selected_item_name, selected_item_kind):
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

        # Connect signals to handlers for progress, loaded, and error
        self.iod_model_service.iodmodel_progress_signal.connect(self._handle_iodmodel_progress, Qt.QueuedConnection)
        self.iod_model_service.iodmodel_loaded_signal.connect(
            lambda sender, iod_model: self._handle_iodmodel_loaded(
                sender,
                iod_model,
                selected_item_name,  # add selected_item_name to received signal parameters
            ),
            Qt.QueuedConnection,
        )
        self.iod_model_service.iodmodel_error_signal.connect(self._handle_iodmodel_error, Qt.QueuedConnection)

        # Set expand property for the selected iod item in the view (will be effective when item will be populated)
        self.view.ui.iodTreeView.expand(index)

    def _handle_module_item_clicked(self, selected_item_path):
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

    def _handle_attribute_item_clicked(self, selected_item_path):
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

    def _update_iodlist_progress_ui(self, sender: object, progress: Progress) -> None:
        percent = progress.percent
        if percent == -1:
            self.logger.debug("Unknown progress received (-1).")
            self.view.update_status_bar(message="Loading IOD modules... (unknown progress)")
        elif percent % 10 == 0 or percent == 100:
            self.logger.debug(f"Progress update: {percent}%")
            self.view.update_status_bar(f"Loading IOD modules... {percent}%")

    def _update_iodlist_loaded_ui(self, sender: object, iod_modules: object) -> None:
        qt_tree_model = self._populate_qt_tree_model_top_level(iod_modules)
        self.view.update_treeview(qt_tree_model)
        self.view.update_status_bar(message=f"Listed {len(iod_modules)} IODs.")

    def _update_iodlist_error_ui(self, sender: object, message: str) -> None:
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

    def _handle_iodmodel_loaded(self, sender: object, iod_model: object, parent_item) -> None:
        if iod_model and hasattr(iod_model, "content"):
            # Attach the loaded IOD model's content to the model's tree
            table_id = parent_item.data(Qt.UserRole)
            self.model.add_iod_spec_content(table_id, iod_model.content)

            self._populate_qt_tree_model_item(parent_item, iod_model.content)
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

    def run(self) -> None:
        """Show the main application window and start the user interface."""
        self.view.show()

    def _populate_qt_tree_model_top_level(
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

        item_favorite_flag = ""
        for iod_name, table_id, table_url, iod_kind in iod_list:
            item_name = QStandardItem(iod_name)
            item_kind = QStandardItem(iod_kind)
            item_usage = QStandardItem("")  # Usage column is empty for now
            item_favorite_flag = QStandardItem(item_favorite_flag)

            # Store table_id and iod_type as data for later retrieval
            item_name.setData(table_id, role=Qt.UserRole)
            item_name.setData(table_url, role=Qt.UserRole + 1)

            model.appendRow([item_name, item_kind, item_usage, item_favorite_flag])

        return model

    def _populate_qt_tree_model_item(self, parent_item, content):
        """Populate the tree with IOD structure from the model content using AnyTree traversal."""
        if not content:
            return

        tree_items = {}  # Map from node to QStandardItem for building hierarchy

        for node in PreOrderIter(content):
            if node == content:
                continue  # Skip the root content node

            # Determine the parent tree item
            if node.parent == content:
                parent_tree_item = parent_item
            else:
                parent_tree_item = tree_items.get(node.parent, parent_item)

            # Determine node type and display text
            if hasattr(node, "module"):
                module_name = getattr(node, "module", "Unknown Module")
                display_text = module_name
                node_type = "Module"
                usage = getattr(node, "usage", "")[:1] if hasattr(node, "usage") else ""
            elif hasattr(node, "elem_name"):
                attr_name = getattr(node, "elem_name", "Unknown Attribute")
                attr_tag = getattr(node, "elem_tag", "")
                elem_type = getattr(node, "elem_type", "")
                display_text = f"{attr_tag} {attr_name}" if attr_tag else attr_name
                node_type = "Attribute"
                usage = elem_type
            else:
                display_text = str(getattr(node, "name", "Unknown Node"))
                node_type = "Unknown"
                usage = ""

            # Create QStandardItems for each column
            name = QStandardItem(display_text)
            kind = QStandardItem(node_type)
            usage = QStandardItem(usage)
            favorite_flag = QStandardItem("")

            # Optionally, store node path or other data for later retrieval
            node_path = "/".join([str(n.name) for n in node.path])
            name.setData(node_path, role=Qt.UserRole)

            # Append the row to the parent tree item
            parent_tree_item.appendRow([name, kind, usage, favorite_flag])
            tree_items[node] = name
