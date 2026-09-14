"""Custom Qt roles for storing extra data in QStandardItem objects.

These roles are used to associate additional data with each treeview item such as domain-specific data,
property or view state.

Roles:
    TABLE_ID_ROLE: Used to store the unique table_id for top-level IODEntry items.
    TABLE_URL_ROLE: Used to store the table_url for top-level IODEntry items.
    NODE_PATH_ROLE: Used to store the Anytree node_path corresponding to the item.
    IS_FAVORITE_ROLE: Used to indicate favorite status for the favorite column (view/delegate).
    IS_PLACEHOLDER_ROLE: View-only state marking a top-level IOD item's not-yet-loaded placeholder child.

Add new roles here as needed, using unique values to avoid conflicts.
"""

from PySide6.QtCore import Qt

TABLE_ID_ROLE = Qt.ItemDataRole.UserRole.value
TABLE_URL_ROLE = Qt.ItemDataRole.UserRole.value + 1
NODE_PATH_ROLE = Qt.ItemDataRole.UserRole.value + 2
IS_FAVORITE_ROLE = Qt.ItemDataRole.UserRole.value + 3
IS_PLACEHOLDER_ROLE = Qt.ItemDataRole.UserRole.value + 4
