"""Model class for the DCMspec Explorer application."""

import logging
import re
from typing import List, Tuple
from dcmspec.config import Config
from dcmspec.xhtml_doc_handler import XHTMLDocHandler
from dcmspec.dom_table_spec_parser import DOMTableSpecParser


class Model:
    """Data model for DICOM specifications."""

    def __init__(self, config: Config, logger: logging.Logger):
        """Initialize the data model."""
        self.config = config
        self.logger = logger
        # URL for DICOM Part 3 Table of Contents
        self.part3_toc_url = "https://dicom.nema.org/medical/dicom/current/output/chtml/part03/ps3.3.html"
        # Initialize document handler for DICOM standard XHTML documents
        self.doc_handler = XHTMLDocHandler(config=self.config, logger=self.logger)
        # Initialize DOM parser for DICOM standard version extraction
        self.dom_parser = DOMTableSpecParser(logger=self.logger)

    def load_iod_list(self, force_download: bool = False, progress_callback=None):
        """Load list of IODs from the DICOM PS3.3 List of Tables.

        Args:
            force_download (bool): If True, force download from URL instead of using cache.
            progress_callback (callable): A callback function to report progress (0-100).

        Returns:
            List[Tuple[str, str, str, str]]: A list of IODs as (iod_name, table_id, href, iod_kind).

        """
        self.logger.debug("Loading IOD list...")

        try:
            # Use XHTMLDocHandler to download and parse the HTML with caching
            cache_file_name = "ps3.3.html"
            soup = self.doc_handler.load_document(
                cache_file_name=cache_file_name,
                url=self.part3_toc_url,
                force_download=force_download,
                progress_callback=progress_callback,
            )

            # Extract and display DICOM version using the library method
            self.dicom_version = self.dom_parser.get_version(soup, "")
            self.logger.info(f"Version {self.dicom_version}")

            # Find the list of tables div
            list_of_tables = soup.find("div", class_="list-of-tables")
            if not list_of_tables:
                error_msg = "Could not find list-of-tables section in downloaded HTML document."
                self.logger.error(error_msg)
                raise Exception(error_msg)

            # Extract IOD modules
            iod_list = self.extract_iod_list(list_of_tables)

            return iod_list

        except Exception as e:
            error_msg = f"Failed to load DICOM specification: \n{str(e)}"
            self.logger.error(error_msg)
            raise RuntimeError(error_msg) from e

    def extract_iod_list(self, list_of_tables) -> List[Tuple[str, str, str, str]]:
        """Extract list of IODs from the list of tables section.

        Returns:
            List of tuples (iod_name, table_id, href, iod_kind)

        """
        iod_modules = []

        # Find all dt elements
        dt_elements = list_of_tables.find_all("dt")

        for dt in dt_elements:
            # Find anchor tags within the dt
            anchor = dt.find("a")
            if anchor and anchor.get("href"):
                href = anchor.get("href")
                text = anchor.get_text(strip=True)

                # Check if this is an IOD Modules table
                if "IOD Modules" in text:
                    # Extract table ID from href (after the #)
                    if "#" in href:
                        table_id = href.split("#")[-1]
                    else:
                        # Fallback: try to extract from href path
                        table_id = href.split("/")[-1].replace(".html", "")

                    # Extract the title (remove the table number prefix)
                    title_match = re.match(r"^[A-Z]?\.\d+(?:\.\d+)*-\d+\.\s*(.+)$", text)
                    title = title_match[1] if title_match else text

                    # Strip " IOD Modules" from the end of the title
                    if title.endswith(" IOD Modules"):
                        iod_name = title[:-12]  # Remove " IOD Modules" (12 characters)

                    # Determine IOD type based on table_id
                    if "_A." in table_id:
                        iod_kind = "Composite"
                    elif "_B." in table_id:
                        iod_kind = "Normalized"
                    else:
                        iod_kind = "Other"

                    iod_modules.append((iod_name, table_id, href, iod_kind))

        return iod_modules
