"""Model class for the DCMspec Explorer application."""

import logging
import os
import re
import shutil
import tempfile
from typing import List, NamedTuple, Tuple
from urllib.parse import urljoin

from anytree import Node

from bs4 import BeautifulSoup
from dcmspec.config import Config
from dcmspec.xhtml_doc_handler import XHTMLDocHandler
from dcmspec.dom_table_spec_parser import DOMTableSpecParser
from dcmspec.iod_spec_builder import IODSpecBuilder
from dcmspec.spec_factory import SpecFactory

from dcmspec_explorer.services.progress_observer import ServiceProgressObserver

# DICOM usage code to text mapping
DICOM_USAGE_MAP = {
    "M": "Mandatory (M)",
    "U": "User Optional (U)",
    "C": "Conditional (C)",
    "": "Unspecified",
}

# DICOM attribute type code to text mapping
DICOM_TYPE_MAP = {
    "1": "Mandatory (1)",
    "1C": "Conditional (1C)",
    "2": "Mandatory, may be empty (2)",
    "2C": "Conditional, may be empty (2C)",
    "3": "Optional (3)",
    "": "Unspecified",
}


class IODEntry(NamedTuple):
    """Define an IOD entry."""

    name: str
    table_id: str
    table_url: str
    kind: str


class Model:
    """Data model for DICOM specifications."""

    PART3_XHTML_CACHE_FILE_NAME = "Part3.xhtml"

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
        # Initialize DICOM version tracking attributes
        self._version = None
        self._new_version_available = False

    @property
    def version(self):
        """Return the DICOM version string for the loaded iod_list."""
        return self._version

    @property
    def new_version_available(self):
        """Return True if the DICOM version changed after the last load."""
        return self._new_version_available

    @property
    def iod_list(self) -> List[IODEntry]:
        """Return the current IOD list as a list of IODEntry objects."""
        if not hasattr(self, "_iod_dict") or not self._iod_dict:
            return []
        return [IODEntry(node.name, node.table_id, node.table_url, node.iod_kind) for node in self._iod_dict.values()]

    def load_iod_list(
        self, force_download: bool = False, progress_observer: ServiceProgressObserver = None
    ) -> List[IODEntry]:
        """Load list of IODs from the DICOM PS3.3 List of Tables.

        Args:
            force_download (bool): If True, force download from URL instead of using cache.
            progress_observer (ServiceProgressObserver): A progress observer to report progress.

        Returns:
            List[IODEntry]: A list of IODEntry objects.

        """
        self.logger.debug("Loading IOD list...")

        cache_file_name = "ps3.3.html"
        standard_cache_dir = os.path.join(self.config.cache_dir, "standard")

        try:
            if force_download:
                # Create a unique temp filename for the standard folder
                with tempfile.NamedTemporaryFile(delete=False, dir=standard_cache_dir, suffix=".html") as tmp:
                    temp_file_name = os.path.basename(tmp.name)
                    temp_file_path = tmp.name
                soup = self.doc_handler.load_document(
                    cache_file_name=temp_file_name,
                    url=self.part3_toc_url,
                    force_download=True,
                    progress_observer=progress_observer,
                )
                # Move the temp file from standard/ to cache root to protect it from archiving
                cache_root_temp_path = os.path.join(self.config.cache_dir, temp_file_name)
                try:
                    shutil.move(temp_file_path, cache_root_temp_path)
                    temp_file_path = cache_root_temp_path  # Update for later use
                except Exception as e:
                    self.logger.warning(f"Failed to move temp TOC from standard to cache root: {e}")
            else:
                soup = self.doc_handler.load_document(
                    cache_file_name=cache_file_name,
                    url=self.part3_toc_url,
                    force_download=False,
                    progress_observer=progress_observer,
                )

            iod_entry_list, version = self._parse_iod_list_from_html(soup)
            self._handle_version_change(version, force_download)
            self._iod_root, self._iod_dict = self._build_iods_model(iod_entry_list)
        except Exception as e:
            error_msg = f"Failed to load DICOM specification: \n{str(e)}"
            self.logger.error(error_msg)
            raise RuntimeError(error_msg) from e

        # Move the temp file to the canonical location after archiving/version handling
        if force_download:
            final_toc_path = os.path.join(standard_cache_dir, cache_file_name)
            if not os.path.exists(standard_cache_dir):
                os.makedirs(standard_cache_dir, exist_ok=True)
            try:
                shutil.move(temp_file_path, final_toc_path)
            except Exception as e:
                self.logger.warning(f"Failed to move new TOC to {final_toc_path}: {e}")

        return iod_entry_list

    def _handle_version_change(self, version: str, force_download: bool) -> None:
        """Handle changes in the DICOM version.

        Args:
            version (str): The new DICOM version.
            force_download (bool): If True, force download from URL instead of using cache.

        """
        # Check if the version changed
        self._new_version_available = self._version is not None and self._version != version

        # If force_download and the version has changed, clear the cache
        if force_download and self._new_version_available:
            self.logger.info(
                f"New DICOM version detected ({version}), clearing cache for previous version ({self._version})."
            )
            self._archive_previous_version_cache()
        else:
            self.logger.info(f"Same DICOM version detected ({version}), keeping cached files.")

        # Update the version
        self._version = version

    def _parse_iod_list_from_html(self, soup: BeautifulSoup) -> Tuple[List[IODEntry], str]:
        """Parse the HTML soup, extract IOD list and version.

        Args:
            soup: BeautifulSoup object of the loaded HTML.

        Returns:
            Tuple[List[IODEntry], str]: A tuple of (IODEntry list, version string).

        """
        # Extract DICOM standard version
        version = self.dom_parser.get_version(soup, "")

        # Find the list of tables section
        list_of_tables = soup.find("div", class_="list-of-tables")
        if not list_of_tables:
            error_msg = "Could not find list-of-tables section in downloaded HTML document."
            self.logger.error(error_msg)
            raise ValueError(error_msg)

        # Extract IOD list from the list of tables section
        iod_entry_list = self._extract_iod_list(list_of_tables)

        return iod_entry_list, version

    def _build_iods_model(self, iod_entry_list: List[IODEntry]):
        """Build a tree model for IODs and a dict mapping table_id to IOD nodes.

        The tree structure supports later addition of modules and attributes as children of each IOD node.
        The dict allows fast lookup of IOD nodes by table_id.

        Args:
            iod_entry_list (List[IODEntry]): List of IODEntry objects.

        Returns:
            Tuple[Any, dict]: (iod_root, iod_dict)
                iod_root: The AnyTree root node for all IODs.
                iod_dict: Dict mapping table_id to the corresponding IOD node.

        """
        iod_root = Node("IOD List")
        iod_dict = {}
        for iod in iod_entry_list:
            # Create a node for each IOD and attach it to the root
            iod_node = Node(
                iod.name, parent=iod_root, table_id=iod.table_id, table_url=iod.table_url, iod_kind=iod.kind
            )
            # Store the node in the dict for fast lookup by table_id
            iod_dict[iod.table_id] = iod_node
        return iod_root, iod_dict

    def _extract_iod_list(self, list_of_tables) -> List[IODEntry]:
        """Extract list of IODs from the list of tables section.

        Returns:
            List[IODEntry]: A list of IODEntry objects.

        """
        # Compute the base URL by stripping the filename from part3_toc_url
        base_url = self.part3_toc_url.rsplit("/", 1)[0] + "/"
        iod_entry_list = []

        # Find all dt elements
        dt_elements = list_of_tables.find_all("dt")

        for dt in dt_elements:
            # Find anchor tags within the dt
            anchor = dt.find("a")
            if anchor and anchor.get("href"):
                # in the chunked HTML document ps3.3.html list of table anchors, hrefs are of the form filename#table_id
                href = anchor.get("href")
                text = anchor.get_text(strip=True)

                # Check if this is an IOD Modules table
                if "IOD Modules" in text:
                    # Extract table ID from href (after the #)
                    if "#" in href:
                        table_id = href.split("#")[-1]
                        table_url = urljoin(base_url, href)
                    else:
                        table_id = "table_id_not_found"
                        self.logger.warning(f"Table ID not found in href: {href}")

                    # Extract the title (remove the table number prefix)
                    title_match = re.match(r"^[A-Z]?\.\d+(?:\.\d+)*-\d+\.\s*(.+)$", text)
                    title = title_match[1] if title_match else text

                    # Strip " IOD Modules" from the end of the title
                    if title.endswith(" IOD Modules"):
                        iod_name = title[:-12]  # Remove " IOD Modules" (12 characters)

                    # Determine IOD kind based on table_id
                    if "_A." in table_id:
                        iod_kind = "Composite"
                    elif "_B." in table_id:
                        iod_kind = "Normalized"
                    else:
                        iod_kind = "Other"

                    iod_entry_list.append(IODEntry(iod_name, table_id, table_url, iod_kind))

        return iod_entry_list

    def load_iod_model(self, table_id: str, logger: logging.Logger, progress_observer: ServiceProgressObserver = None):
        """Load the IOD model for the given table_id using the IODSpecBuilder API.

        This method uses the IODSpecBuilder.build_from_url() method which handles:
        - Cache detection and loading (fast for cached models)
        - Web download and parsing (slower for non-cached models)
        - Model building and JSON serialization

        Args:
            table_id (str): The table identifier (e.g., "table_A.49-1")
            logger (logging.Logger): Logger instance for progress tracking and debugging
            progress_observer (ServiceProgressObserver): A progress observer to report progress.

        Returns:
            IOD model object with content attribute containing the AnyTree structure,
            or None if building failed.

        """
        url = "https://dicom.nema.org/medical/dicom/current/output/html/part03.html"
        cache_file_name = self.PART3_XHTML_CACHE_FILE_NAME
        model_file_name = f"Part3_{table_id}_expanded.json"

        # Determine if this is a composite or normalized IOD
        composite_iod = "_A." in table_id

        # Create the IOD specification factory
        c_iod_columns_mapping = {0: "ie", 1: "module", 2: "ref", 3: "usage"}
        n_iod_columns_mapping = {0: "module", 1: "ref", 2: "description"}
        iod_columns_mapping = c_iod_columns_mapping if composite_iod else n_iod_columns_mapping
        iod_factory = SpecFactory(
            column_to_attr=iod_columns_mapping,
            name_attr="module",
            config=self.config,
            logger=logger,
        )

        # Create the modules specification factory

        # Set unformatted to False for elem_description (column 3), others remain True
        parser_kwargs = {"unformatted": {0: True, 1: True, 2: True, 3: False}}
        if not composite_iod:
            parser_kwargs["skip_columns"] = [2]
        module_factory = SpecFactory(
            column_to_attr={0: "elem_name", 1: "elem_tag", 2: "elem_type", 3: "elem_description"},
            name_attr="elem_name",
            parser_kwargs=parser_kwargs,
            config=self.config,
            logger=logger,
        )

        # Create the builder
        builder = IODSpecBuilder(
            iod_factory=iod_factory,
            module_factory=module_factory,
            logger=logger,
        )

        # Build and return the model
        return builder.build_from_url(
            url=url,
            cache_file_name=cache_file_name,
            json_file_name=model_file_name,
            table_id=table_id,
            force_download=False,
            progress_observer=progress_observer,
        )

    def add_iod_spec_content(self, table_id, iod_content):
        """Add the loaded IOD specification content (AnyTree node) as a child of its IOD node.

        Args:
            table_id (str): The table identifier (e.g., "table_A.49-1") of the IOD node
            iod_content (AnyTree node): The loaded IOD specification content to add

        """
        iod_node = self._iod_dict.get(table_id)
        if iod_node and iod_content:
            iod_content.parent = iod_node

    def get_node_by_path(self, node_path):
        """Return the AnyTree node given its full path in the model.

        Args:
            node_path (str): The full path to the node (e.g., "IOD List/Some IOD/Some Module/Some Attribute").

        Returns:
            AnyTree node or None if not found.

        """
        if not self._iod_root or not node_path:
            return None

        # Split the path and traverse from the root
        path_parts = node_path.split("/")
        node = self._iod_root
        for part in path_parts[1:]:  # skip "IOD List" (the root itself)
            node = next((child for child in node.children if child.name == part), None)
            if node is None:
                return None

        # Return the node's attributes as a dict
        return node

    def get_node_details(self, node_path):
        """Return all attributes of an Anytree node given its full path in the model.

        This method locates the node in the IOD tree using the provided node_path,
        and returns its attributes as a dictionary. If the node is not found, returns None.

        Args:
            node_path (str): The full path to the node (e.g., "IOD List/Some IOD/Some Module/Some Attribute").

        Returns:
            dict: The node's attributes including anytree metadata.
            The consumer (controller/view) should select which attributes to display.

        """
        node = self.get_node_by_path(node_path)
        return None if node is None else node.__dict__

    def _archive_previous_version_cache(self):
        """Move the entire standard and model cache folders to a versioned cache/<old_version>/ folder."""
        prev_version = self._version
        if not prev_version:
            self.logger.info("No previous version found; skipping cache move.")
            return

        cache_dir = self.config.cache_dir
        versioned_dir = os.path.join(cache_dir, prev_version)
        standard_cache_dir = os.path.join(cache_dir, "standard")
        model_cache_dir = os.path.join(cache_dir, "model")
        versioned_standard_dir = os.path.join(versioned_dir, "standard")
        versioned_model_dir = os.path.join(versioned_dir, "model")

        # If the versioned archive already exists, move it to a timestamped backup folder
        if os.path.exists(versioned_dir):
            from datetime import datetime

            timestamp = datetime.now().strftime("%Y-%m-%dT%H-%M-%S")
            backup_dir = f"{versioned_dir}_backup_{timestamp}"
            try:
                shutil.move(versioned_dir, backup_dir)
                self.logger.info(f"Existing archive {versioned_dir} moved to {backup_dir}")
            except Exception as e:
                self.logger.warning(f"Failed to move existing archive {versioned_dir} to {backup_dir}: {e}")

        # Move the entire standard folder if it exists
        if os.path.exists(standard_cache_dir):
            os.makedirs(versioned_dir, exist_ok=True)
            try:
                shutil.move(standard_cache_dir, versioned_standard_dir)
                self.logger.info(f"Moved standard cache folder to versioned folder: {versioned_standard_dir}")
            except Exception as e:
                self.logger.warning(f"Failed to move {standard_cache_dir} to {versioned_standard_dir}: {e}")

        # Move the entire model folder if it exists
        if os.path.exists(model_cache_dir):
            os.makedirs(versioned_dir, exist_ok=True)
            try:
                shutil.move(model_cache_dir, versioned_model_dir)
                self.logger.info(f"Moved model cache folder to versioned folder: {versioned_model_dir}")
            except Exception as e:
                self.logger.warning(f"Failed to move {model_cache_dir} to {versioned_model_dir}: {e}")
