"""Custom Qt roles for storing extra data in QStandardItem objects.

These roles are used to associate domain-specific data with treeview items
without interfering with Qt's built-in roles.

Roles:
    TABLE_ID_ROLE: Used to store the unique table_id for top-level IODEntry items.
    TABLE_URL_ROLE: Used to store the table_url for top-level IODEntry items.
    NODE_PATH_ROLE: Used to store the Anytree node_path corresponding to the item.
    IS_FAVORITE_ROLE: Used to indicate favorite status for the favorite column (view/delegate).

Add new roles here as needed, using unique values to avoid conflicts.
"""

from PySide6.QtCore import Qt

TABLE_ID_ROLE = Qt.UserRole
TABLE_URL_ROLE = Qt.UserRole + 1
NODE_PATH_ROLE = Qt.UserRole + 2
IS_FAVORITE_ROLE = Qt.UserRole + 3
