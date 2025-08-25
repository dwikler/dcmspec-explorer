"""Adapter class for converting IOD data model to Qt treeview model."""

from typing import List, Tuple, Optional
from anytree import PreOrderIter, Node

from PySide6.QtCore import Qt
from PySide6.QtGui import QStandardItemModel, QStandardItem

from dcmspec_explorer.model.model import IODEntry


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
            if sort_column == 1:
                # Sort by kind, then by name
                filtered = sorted(
                    filtered,
                    key=lambda iod: (iod.kind.lower(), iod.name.lower()),
                    reverse=sort_reverse,
                )
            else:
                filtered = sorted(
                    filtered,
                    key=lambda iod: getattr(iod, ["name", "kind", "table_url", "kind"][sort_column]).lower(),
                    reverse=sort_reverse,
                )

        model = IODTreeViewModelAdapter.populate_treeview_model_top_level(filtered)
        selected_row = None
        for row in range(model.rowCount()):
            item = model.item(row, 0)
            table_id = item.data(Qt.UserRole)
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
            item_name.setData(iod.table_id, role=Qt.UserRole)
            item_name.setData(iod.table_url, role=Qt.UserRole + 1)

            model.appendRow([item_name, item_kind, item_usage, item_favorite_flag])

        return model

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
            name.setData(node_path, role=Qt.UserRole)

            # Append the row to the parent tree item
            parent_tree_item.appendRow([name, kind, usage, favorite_flag])
            tree_items[node] = name
