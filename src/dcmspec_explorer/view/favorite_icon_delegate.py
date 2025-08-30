"""Subclass of QStyledItemDelegate to paint a favorite icon in the favorites column."""

from PySide6.QtWidgets import QStyledItemDelegate, QStyleOptionViewItem
from PySide6.QtGui import QPainter, QIcon
from PySide6.QtCore import Qt, QModelIndex, QRect

from dcmspec_explorer.qt.qt_roles import IS_FAVORITE_ROLE


class FavoriteIconDelegate(QStyledItemDelegate):
    """Custom delegate to paint a favorite icon in the favorites column."""

    def __init__(self, heart_icon: QIcon, parent=None):
        """Initialize the delegate with a heart icon."""
        super().__init__(parent)
        self.heart_icon = heart_icon

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex):
        """Override to draw the default item."""
        super().paint(painter, option, index)

        is_favorite = index.data(IS_FAVORITE_ROLE)
        if is_favorite:
            if self.heart_icon:
                # Draw the heart icon centered in the cell
                icon_size = min(option.rect.width(), option.rect.height()) - 4
                pixmap = self.heart_icon.pixmap(icon_size, icon_size)
                icon_rect = QRect(
                    option.rect.x() + (option.rect.width() - icon_size) // 2,
                    option.rect.y() + (option.rect.height() - icon_size) // 2,
                    icon_size,
                    icon_size,
                )
                painter.drawPixmap(icon_rect, pixmap)
            else:
                # Fallback to heart character
                self._use_heart_character(painter, option)

    # TODO Rename this here and in `paint`
    def _use_heart_character(self, painter, option):
        """Draw a Unicode heart character centered in the cell."""
        painter.save()
        painter.setPen(option.palette.windowText().color())
        font = painter.font()
        font.setBold(True)
        painter.setFont(font)
        heart = "♥"
        rect = option.rect
        painter.drawText(rect, Qt.AlignCenter, heart)
        painter.restore()
