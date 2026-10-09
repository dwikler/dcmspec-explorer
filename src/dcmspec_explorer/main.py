"""Main entry point for the DCMspec Explorer application."""

import os

from PySide6.QtWidgets import QApplication
from dcmspec_explorer.controller.app_controller import AppController


def apply_style(app: QApplication) -> None:
    """Use the Fusion style on all platforms, unless QT_STYLE_OVERRIDE selects one.

    Fusion looks the same everywhere, and avoids the native macOS style that renders poorly under the
    macOS 27 design when the app is linked against its SDK.
    """
    if "QT_STYLE_OVERRIDE" not in os.environ:
        app.setStyle("Fusion")


def main():
    """Start the DCMspec Explorer application.

    Initialize and launch the Qt UI for exploring DICOM specifications.
    """
    app = QApplication([])
    apply_style(app)
    app.setApplicationName("DCMspec Explorer")
    app.setApplicationDisplayName("DCMspec Explorer")

    controller = AppController()
    controller.run()
    app.exec()


if __name__ == "__main__":
    main()
