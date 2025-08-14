"""Main entry point for the DCMspec Explorer application."""

from PySide6.QtWidgets import QApplication
from dcmspec_explorer.controller.app_controller import AppController


def main():
    """Start the DCMspec Explorer application.

    Initialize and launch the Qt UI for exploring DICOM specifications.
    """
    app = QApplication([])

    controller = AppController()
    controller.run()
    app.exec()


if __name__ == "__main__":
    main()
