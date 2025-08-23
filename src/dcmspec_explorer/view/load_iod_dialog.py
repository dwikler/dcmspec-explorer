"""Load IOD Dialog View Class for the DCMspec Explorer application."""

from PySide6.QtWidgets import QDialog

from dcmspec.progress import ProgressStatus

from dcmspec_explorer.view.load_iod_dialog_ui import Ui_LoadIODDialog


class LoadIODDialog(QDialog):
    """Dialog for reporting progress on loading IOD model."""

    def __init__(self, parent=None):
        """Initialize the Load IOD Dialog."""
        super().__init__(parent)
        self.ui = Ui_LoadIODDialog()
        self.ui.setupUi(self)

        # Map ProgressStatus enum values to progress bar widgets
        self.status_to_bar = {
            ProgressStatus.DOWNLOADING_IOD: self.ui.progressBarDownload,
            ProgressStatus.PARSING_IOD_MODULE_LIST: self.ui.progressBarParseTable,
            ProgressStatus.PARSING_IOD_MODULES: self.ui.progressBarParseModules,
            ProgressStatus.SAVING_IOD_MODEL: self.ui.progressBarSaveModel,
        }

    def update_step(self, status, percent):
        """Update the progress bar for a specific status."""
        bar = self.status_to_bar.get(status, None)
        if bar:
            if percent == -1:
                bar.setValue(100)
            else:
                bar.setValue(percent)
