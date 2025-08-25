"""Adapter class for converting IOD data model to Qt treeview model."""

from typing import List, Tuple, Optional
from anytree import PreOrderIter, Node

from PySide6.QtCore import Qt
from PySide6.QtGui import QStandardItemModel, QStandardItem

from dcmspec_explorer.model.model import IODEntry

# Define mapping of column names to their indices
COLUMN_INDEX = {
    "name": 0,
    "kind": 1,
    "usage": 2,
    "favorite": 3,
}

# Define custom roles constants for storing extra data in QStandardItem objects.
# These roles are used to associate domain-specific data with treeview items
# without interfering with Qt's built-in roles.
#
# TABLE_ID_ROLE: Used to store the unique table_id for top-level IODEntry items.
# TABLE_URL_ROLE: Used to store the table_url for top-level IODEntry items.
# NODE_PATH_ROLE: Used to store the Anytree node_path corresponding to the item
TABLE_ID_ROLE = Qt.UserRole
TABLE_URL_ROLE = Qt.UserRole + 1
NODE_PATH_ROLE = Qt.UserRole + 2


class IODTreeViewModelAdapter:
    """Adapt IOD data model to Qt treeview model."""

    @staticmethod
    def build_treeview_model(
        iod_entry_list: List[IODEntry],
        search_text: str = "",
        sort_column: Optional[int] = None,
        sort_reverse: bool = False,
        loaded_children: Optional[dict] = None,
        selected_table_id: Optional[str] = None,
    ) -> Tuple[QStandardItemModel, Optional[int]]:
        """Build a QStandardItemModel for the treeview.

        The Qt Treeview model is rebuilt each time a filter and sort is requested,
        restoring children, and returning the model and selected row.

        Args:
            iod_entry_list (List[IODEntry]): The list of IOD entries to display.
            search_text (str, optional): Text to filter the displayed entries.
            sort_column (int, optional): Column index to sort by.
            sort_reverse (bool, optional): Whether to reverse the sort order.
            loaded_children (dict, optional): Preloaded child items for the tree.
            selected_table_id (str, optional): Table ID of the selected item.

        Returns:
            Tuple[QStandardItemModel, Optional[int]]: The treeview model and the selected row index.

        """
        # Filter
        filtered = iod_entry_list
        if search_text:
            # Case sensitive search
            search_text = search_text.strip()
            filtered = [iod for iod in filtered if search_text in iod.name or search_text in iod.kind]

        # Sort if specified (no sorting at startup)
        if sort_column is not None:
            if sort_column == COLUMN_INDEX["name"]:
                # Sort by name
                filtered = sorted(
                    filtered,
                    key=lambda iod: iod.name.lower(),
                    reverse=sort_reverse,
                )
            elif sort_column == COLUMN_INDEX["kind"]:
                # Sort by kind, then by name
                filtered = sorted(
                    filtered,
                    key=lambda iod: (iod.kind.lower(), iod.name.lower()),
                    reverse=sort_reverse,
                )
            # No else needed as sorting on other columns is not supported

        model = IODTreeViewModelAdapter.populate_treeview_model_top_level(filtered)
        selected_row = None
        for row in range(model.rowCount()):
            item = model.item(row, 0)
            table_id = item.data(TABLE_ID_ROLE)
            if loaded_children and table_id in loaded_children:
                IODTreeViewModelAdapter.populate_treeview_model_item(item, loaded_children[table_id])
            if selected_table_id and table_id == selected_table_id:
                selected_row = row
        return model, selected_row

    @staticmethod
    def populate_treeview_model_top_level(
        iod_list: List[IODEntry], favorites_manager: object = None
    ) -> QStandardItemModel:
        """Convert a list of IODEntry objects into a QStandardItemModel for use with a QTreeView.

        Args:
            iod_list (List[IODEntry] or None): List of IODEntry objects.
            favorites_manager: Instance to check if a table_id is a favorite.

        Returns:
            QStandardItemModel: The model ready to be set on a QTreeView.

        """
        model = QStandardItemModel()
        model.setHorizontalHeaderLabels(["Name", "Kind", "", "♥"])

        item_favorite_flag = ""
        for iod in iod_list:
            item_name = QStandardItem(iod.name)
            item_kind = QStandardItem(iod.kind)
            item_usage = QStandardItem("")  # Usage column is empty for now
            item_favorite_flag = QStandardItem(item_favorite_flag)

            # Store table_id and iod_type as data for later retrieval
            item_name.setData(iod.table_id, role=TABLE_ID_ROLE)
            item_name.setData(iod.table_url, role=TABLE_URL_ROLE)

            model.appendRow([item_name, item_kind, item_usage, item_favorite_flag])

        return model

    @staticmethod
    def populate_iod_entry_children(tree_model: QStandardItemModel, table_id: str, content: Node) -> bool:
        """Add children items to the IODEntry item in the treeview model.

        Args:
            tree_model (QStandardItemModel): The tree model to modify.
            table_id (str): The table ID of the IODEntry to update.
            content (Node): The content node to append as children.

        Returns:
            bool: True if the item was found and updated, False otherwise.

        """
        for row in range(tree_model.rowCount()):
            item = tree_model.item(row, 0)
            if item.data(TABLE_ID_ROLE) == table_id:
                IODTreeViewModelAdapter.populate_treeview_model_item(item, content)
                return True
        return False

    @staticmethod
    def populate_treeview_model_item(parent_item: QStandardItem, content: Node) -> None:
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
            name.setData(node_path, role=NODE_PATH_ROLE)

            # Append the row to the parent tree item
            parent_tree_item.appendRow([name, kind, usage, favorite_flag])
            tree_items[node] = name
