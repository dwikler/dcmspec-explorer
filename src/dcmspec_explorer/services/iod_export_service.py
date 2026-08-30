"""IOD Export Service for DCMspec Explorer."""

import copy
import logging
import queue
import threading
from typing import Any

from anytree import PreOrderIter
from inscriptis import get_text
from inscriptis.css_profiles import CSS_PROFILES
from inscriptis.model.config import ParserConfig

from dcmspec.iod_spec_printer import IODSpecPrinter

# Minimize inscriptis' layout-aware indentation, which is meant for approximating how a browser
# would visually lay out a full page; for a single description field in a spreadsheet cell, only
# its paragraph/list structure is wanted, not left-padding derived from HTML nesting depth.
_HTML_TO_TEXT_CONFIG = ParserConfig(css=CSS_PROFILES["strict"])

# Node attributes dcmspec-explorer's Model deliberately parses as raw HTML (see model.py's
# `unformatted=False` settings) so they can be rendered richly in the details pane. Exported files
# need plain text instead, so IODExportWorker converts these on an export-only copy of the model.
HTML_NODE_ATTRS = ("elem_description",)

# Excel column widths by node attribute rather than position: Normalized IODs' module attribute
# tables have no Type column (see model.py's `skip_columns` for elem_type), so the model's
# metadata.column_to_attr for those IODs omits "elem_type" and is one column shorter than for
# Composite IODs. Keying widths by attribute name keeps each column its intended width regardless
# of which columns are actually present.
XLSX_COLUMN_WIDTHS_BY_ATTR = {
    "elem_name": 25,
    "elem_tag": 12,
    "elem_type": 8,
    "elem_description": 35,
}
XLSX_DEFAULT_COLUMN_WIDTH = 20


class IODExportWorker:
    """Export a loaded IOD spec model to CSV or Excel in a background thread."""

    def __init__(
        self, iod_model: Any, fmt: str, output_path: str, logger: logging.Logger, event_queue: queue.Queue
    ) -> None:
        """Initialize the worker with the model to export and the target format/path.

        Args:
            iod_model: The loaded SpecModel to export.
            fmt: Export format, "csv" or "xlsx".
            output_path: Destination file path.
            logger: The logger instance for logging progress and errors.
            event_queue: The event queue to put the outcome event into.

        """
        self.iod_model = iod_model
        self.fmt = fmt
        self.output_path = output_path
        self.logger = logger
        self.event_queue = event_queue

    def run(self) -> None:
        """Run the worker to export the IOD model and send the outcome to the event queue."""
        self.logger.debug(f"IODExportWorker created in thread: {threading.current_thread().name}")
        try:
            export_model = self._to_plain_text_model(self.iod_model)
            printer = IODSpecPrinter(export_model, logger=self.logger, output=self.output_path)
            if self.fmt == "csv":
                printer.print_csv()
            elif self.fmt == "xlsx":
                column_widths = self._xlsx_column_widths(export_model)
                printer.print_xlsx(column_widths=column_widths)
            else:
                raise ValueError(f"Unsupported export format: {self.fmt}")
            self.event_queue.put(("loaded", self.output_path))
        except Exception as e:
            self.logger.exception(f"Failed to export IOD model to {self.output_path}")
            self.event_queue.put(("error", str(e)))

    @staticmethod
    def _xlsx_column_widths(export_model: Any) -> list[int]:
        """Return Excel column widths in the model's actual column order."""
        column_to_attr = export_model.metadata.column_to_attr
        return [
            XLSX_COLUMN_WIDTHS_BY_ATTR.get(column_to_attr[i], XLSX_DEFAULT_COLUMN_WIDTH) for i in sorted(column_to_attr)
        ]

    @staticmethod
    def _to_plain_text_model(iod_model: Any) -> Any:
        """Return a deep copy of iod_model with HTML-flagged node attributes converted to plain text."""
        export_model = copy.deepcopy(iod_model)
        for node in PreOrderIter(export_model.content):
            for attr in HTML_NODE_ATTRS:
                value = getattr(node, attr, None)
                if value:
                    setattr(node, attr, IODExportWorker._html_to_text(value))
        return export_model

    @staticmethod
    def _html_to_text(html: str) -> str:
        """Convert an HTML fragment to plain text, preserving paragraph/list structure."""
        return get_text(html, _HTML_TO_TEXT_CONFIG).strip()
