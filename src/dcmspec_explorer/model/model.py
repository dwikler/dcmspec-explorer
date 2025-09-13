"""Model class for the DCMspec Explorer application."""

import logging
import os
import re
import shutil
import tempfile
import html
from typing import List, NamedTuple, Tuple, Any, Optional
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from dcmspec.config import Config
from dcmspec.xhtml_doc_handler import XHTMLDocHandler
from dcmspec.dom_table_spec_parser import DOMTableSpecParser
from dcmspec.iod_spec_builder import IODSpecBuilder
from dcmspec.spec_factory import SpecFactory
from dcmspec.spec_model import SpecModel

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
    """Data model for DICOM specifications.

    This class loads, parses, and manages the in-memory representation of DICOM IODs.

    Attributes:
        _iod_entries: Dictionary mapping table_id to IODEntry objects for fast lookup.
        _iod_specmodels: Dictionary mapping table_id to loaded SpecModel instances.

    """

    PART3_XHTML_CACHE_FILE_NAME = "Part3.xhtml"
    PART3_XHTML_URL = "https://dicom.nema.org/medical/dicom/current/output/html/part03.html"

    def __init__(self, config: Config, logger: logging.Logger):
        """Initialize the data model.

        _iod_entries: Dictionary mapping table_id to IODEntry objects for fast lookup.
        _iod_specmodels: Dictionary mapping table_id to loaded SpecModel instances (set by load_iod_model)
        """
        self.config = config
        self.logger = logger
        # URL for DICOM Part 3 Table of Contents
        self.part3_toc_url = "https://dicom.nema.org/medical/dicom/current/output/chtml/part03/ps3.3.html"
        # Initialize document handler for DICOM standard XHTML documents
        self.doc_handler = XHTMLDocHandler(config=self.config, logger=self.logger)
        # Initialize DOM parser for DICOM standard version extraction
        self.dom_parser = DOMTableSpecParser(logger=self.logger)
        # Initialize DICOM version tracking attributes
        self._version: Optional[str] = None
        self._new_version_available = False

        # Initialize the IOD entries and spec models dictionaries
        self._iod_entries: dict[str, IODEntry] = {}  # Dict mapping table_id to IODEntry objects
        self._iod_specmodels: dict[str, SpecModel] = {}  # Dict mapping table_id to loaded SpecModel instances

    @property
    def iod_list(self) -> List[IODEntry]:
        """Return the current IOD list as a list of IODEntry objects."""
        if not hasattr(self, "_iod_entries") or not self._iod_entries:
            return []
        return list(self._iod_entries.values())

    @property
    def iod_specmodels(self) -> dict[str, Any]:
        """Return a dictionary of all loaded IOD SpecModel instances, keyed by table_id."""
        return self._iod_specmodels

    @property
    def new_version_available(self) -> bool:
        """Return True if the DICOM version changed after the last load."""
        return self._new_version_available

    @property
    def version(self) -> Optional[str]:
        """Return the DICOM version string for the loaded iod_list."""
        return self._version

    def load_iod_list(
        self, force_download: bool = False, progress_observer: Optional[ServiceProgressObserver] = None
    ) -> List[IODEntry]:
        """Load list of IODs from the DICOM PS3.3 List of Tables.

        This method manages the full workflow for loading the IOD list, including:
        - Managing a temporary file for the new download if force_download is True.
        - Downloading or reading from cache the IOD list HTML.
        - Parsing the IOD list and version from the HTML.
        - Checking if the version changed.
        - Archiving the old cache if needed.
        - Moving the temp file to the canonical location if applicable.
        - Updating the in-memory model.

        Args:
            force_download (bool): If True, force download from URL instead of using cache.
            progress_observer (ServiceProgressObserver): A progress observer to report progress.

        Returns:
            List[IODEntry]: A list of IODEntry objects.

        """
        self.logger.debug("Loading IOD list...")

        cache_file_name = "ps3.3.html"

        try:
            # Step 1: Prepare temp file if needed
            temp_file_name, temp_file_path = (None, None)
            if force_download:
                temp_file_name, temp_file_path = self._create_temp_iod_list_file()

            # Step 2. Download or read cache in temp or cache file in cache/standard folder
            soup = self._load_iod_list_html(force_download, cache_file_name, temp_file_name, progress_observer)

            # Step 3. If force_download, move the temp file to cache root to protect it from archiving
            if force_download and temp_file_name:
                temp_file_path = self._move_temp_file_to_cache_root(temp_file_name)

            # Step 4: Parse the IOD list and version from the HTML
            iod_entry_list, version = self._parse_iod_list_from_html(soup)

            # Step 5: Check if the version changed
            self._new_version_available = self._detect_version_changed(version)

            # Step 6: Archive/move the old cache if needed
            if force_download and self._new_version_available:
                self._archive_previous_version_cache()

            # Step 7: If a temp file was used, move it to the canonical location after archiving/version handling
            if force_download and temp_file_path:
                self._move_temp_iod_list_to_cache(temp_file_path, cache_file_name)

            # Step 8: Update the in-memory model and version
            self._version = version
            self._iod_entries = self._build_iods_model(iod_entry_list)

        except Exception as e:
            error_msg = f"Failed to load DICOM specification: \n{str(e)}"
            self.logger.error(error_msg)
            raise RuntimeError(error_msg) from e

        return iod_entry_list

    def load_iod_model(
        self, table_id: str, logger: logging.Logger, progress_observer: Optional[ServiceProgressObserver] = None
    ) -> Any:
        """Load the IOD model for the given table_id using the IODSpecBuilder API.

        If the model is not already loaded in memory, build it using
        the dcmspec IODSpecBuilder class method which handles:
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
        # Return in-memory model if already loaded
        if table_id in self.iod_specmodels:
            return self.iod_specmodels[table_id]

        # Define Part 3 URL and file names
        url = self.PART3_XHTML_URL
        cache_file_name = self.PART3_XHTML_CACHE_FILE_NAME
        model_file_name = f"Part3_{table_id}_expanded.json"

        # Determine if this is a composite or normalized IOD
        composite_iod = "_A." in table_id

        # Create the IOD specification factory
        c_iod_columns_mapping = {0: "ie", 1: "module", 2: "ref", 3: "usage"}
        c_iod_unformatted = {0: True, 1: True, 2: False, 3: True}
        n_iod_columns_mapping = {0: "module", 1: "ref", 2: "description"}
        n_iod_unformatted = {0: True, 1: False, 2: True}
        iod_columns_mapping = c_iod_columns_mapping if composite_iod else n_iod_columns_mapping
        iod_unformatted = c_iod_unformatted if composite_iod else n_iod_unformatted
        iod_factory = SpecFactory(
            column_to_attr=iod_columns_mapping,
            name_attr="module",
            config=self.config,
            logger=logger,
            parser_kwargs={"unformatted": iod_unformatted},
        )

        # Create the modules specification factory

        # Set parser unformatted to False for elem_description (column 3), others remain True
        parser_kwargs: dict[str, Any] = {"unformatted": {0: True, 1: True, 2: True, 3: False}}
        # Set skip_columns to elem_type column if IOD is normalized (no Type column)
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

        # Build and store the model in memory
        try:
            iod_model, _ = builder.build_from_url(
                url=url,
                cache_file_name=cache_file_name,
                json_file_name=model_file_name,
                table_id=table_id,
                force_download=False,
                progress_observer=progress_observer,
            )
        except ValueError as ve:
            self.logger.error(
                f"Error unpacking result from build_from_url for table_id '{table_id}', url '{url}': {ve}. "
                "The returned value did not match the expected tuple shape (SpecModel, ...)."
            )
            raise RuntimeError("Failed to load the DICOM model. Please try again or contact support.") from ve

        # Type and attribute checks to ensure the returned object is as expected.
        if not isinstance(iod_model, SpecModel):
            self.logger.error(
                f"Unexpected return type for table_id '{table_id}', url '{url}': {type(iod_model)} (expected SpecModel)"
            )
            raise TypeError(
                "The selected DICOM model could not be loaded. This may be due to a corrupted file or network issue."
            )
        if not hasattr(iod_model, "content"):
            self.logger.error(
                (
                    f"Returned SpecModel is missing 'content' attribute for table_id '{table_id}', "
                    f"url '{url}': {type(iod_model)}"
                )
            )
            raise RuntimeError(
                "The IOD was loaded, but its content could not be accessed. The content may be incomplete or corrupted."
            )

        # Store the loaded model in memory
        self._iod_specmodels[table_id] = iod_model

        return iod_model

    def get_specmodel_node(self, table_id: str, relative_path: str) -> Any:
        """Return the node from the loaded SpecModel tree given a table_id and a relative path.

        Args:
            table_id (str): The table_id of the IOD (e.g., "table_A.49-1").
            relative_path (str): The path from the SpecModel root, e.g., "Module/Attribute".

        Returns:
            SpecModel node or None if not found.

        """
        specmodel = self.iod_specmodels.get(table_id)
        if not specmodel or not hasattr(specmodel, "content"):
            return None
        node = specmodel.content
        if not relative_path:
            return node
        for part in relative_path.split("/"):
            children = getattr(node, "children", [])
            node = next((child for child in children if getattr(child, "name", None) == part), None)
            if node is None:
                return None
        return node

    def get_node_public_attrs(self, table_id: str, relative_path: str) -> Optional[dict]:
        """Return all public attributes of a node in the SpecModel tree given its table_id and relative path.

        This method locates the node in the loaded SpecModel tree using the provided table_id and relative_path,
        and returns its public attributes (those not starting with an underscore) as a dictionary.
        If the node is not found, returns None.

        Args:
            table_id (str): The table_id of the IOD (e.g., "table_A.49-1").
            relative_path (str): The path from the SpecModel root, e.g., "Module/Attribute".

        Returns:
            dict: The node's public attributes.
            The consumer (controller/view) should select which attributes to display.

        """
        node = self.get_specmodel_node(table_id, relative_path)
        if node:
            return {k: v for k, v in node.__dict__.items() if not k.startswith("_")}
        return None

    def get_module_ref_link(self, ref_value: str) -> str:
        """Return formatted HTML anchor for the module reference, or escaped plain text if not available or unsafe."""
        if not ref_value:
            return ""
        soup = BeautifulSoup(ref_value, "xml")
        anchor = soup.find("a", class_="xref")
        if anchor and anchor.has_attr("href"):
            href = anchor["href"].strip()
            anchor_text = anchor.get_text(strip=True)
            # Only allow fragment identifiers (starting with #)
            if href.startswith("#"):
                url = f"{self.PART3_XHTML_URL}{href}"
                return f'<a href="{url}">{anchor_text}</a>'
            else:
                self.logger.warning(
                    f"Unsafe or unexpected href in module ref: {href!r}. Escaping and displaying as plain text."
                )
        # Fallback: escape and display as plain text.
        # Escaping prevents XSS (Cross-Site Scripting) if ref_value contains malicious HTML/script.
        return html.escape(ref_value)

    def _create_temp_iod_list_file(self) -> Tuple[str, str]:
        """Create a unique temp file for downloading the IOD list file in the standard cache directory.

        Returns:
            Tuple[str, str]: (temp_file_name, temp_file_path)

        """
        with tempfile.NamedTemporaryFile(delete=False, dir=self._standard_cache_dir(), suffix=".html") as tmp:
            temp_file_name = os.path.basename(tmp.name)
            temp_file_path = tmp.name
        return temp_file_name, temp_file_path

    def _load_iod_list_html(
        self,
        force_download: bool,
        cache_file_name: str,
        temp_file_name: Optional[str] = None,
        progress_observer: Optional[ServiceProgressObserver] = None,
    ) -> BeautifulSoup:
        """Download or load the IOD list HTML from cache, using a temp file if force_download is True.

        This method only handles loading (download or cache read), not parsing.

        Returns:
            BeautifulSoup: The loaded HTML soup.

        """
        if not force_download or not temp_file_name:
            return self.doc_handler.load_document(
                cache_file_name=cache_file_name,
                url=self.part3_toc_url,
                force_download=False,
                progress_observer=progress_observer,
            )
        return self.doc_handler.load_document(
            cache_file_name=temp_file_name,
            url=self.part3_toc_url,
            force_download=True,
            progress_observer=progress_observer,
        )

    def _move_temp_file_to_cache_root(self, temp_file_name: str) -> str:
        """Move the temp file from cache/standard to cache root and return the new path."""
        cache_root_temp_path = os.path.join(self.config.cache_dir, temp_file_name)
        src_path = os.path.join(self._standard_cache_dir(), temp_file_name)
        try:
            shutil.move(src_path, cache_root_temp_path)
            return cache_root_temp_path
        except Exception as e:
            self.logger.warning(f"Failed to move temp IOD list file from cache/standard to cache root: {e}")
            return src_path

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

    def _detect_version_changed(self, new_version: str) -> bool:
        """Detect if the DICOM version has changed compared to the current version.

        Args:
            new_version (str): The new DICOM version string.

        Returns:
            bool: True if the version has changed, False otherwise.

        """
        return self._version is not None and self._version != new_version

    def _move_temp_iod_list_to_cache(self, temp_file_path: str, cache_file_name: str) -> None:
        """Move the temp IOD list file to the canonical cache location after archiving/version handling."""
        cache_file_path = os.path.join(self._standard_cache_dir(), cache_file_name)
        if not os.path.exists(self._standard_cache_dir()):
            os.makedirs(self._standard_cache_dir(), exist_ok=True)
        try:
            shutil.move(temp_file_path, cache_file_path)
        except Exception as e:
            self.logger.warning(f"Failed to move temp IOD list file to {cache_file_path}: {e}")

    def _archive_previous_version_cache(self) -> None:
        """Move the entire standard and model cache folders to a versioned cache/<old_version>/ folder."""
        prev_version = self._version
        if not prev_version:
            self.logger.info("No previous version found; skipping cache move.")
            return

        versioned_dir = self._versioned_dir(prev_version)
        standard_cache_dir = self._standard_cache_dir()
        model_cache_dir = self._model_cache_dir()
        versioned_standard_dir = self._versioned_standard_dir(prev_version)
        versioned_model_dir = self._versioned_model_dir(prev_version)

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
        self._move_folder_if_exists(
            src=standard_cache_dir,
            dst=versioned_standard_dir,
            ensure_parent=versioned_dir,
            description="standard cache folder to versioned folder",
        )

        # Move the entire model folder if it exists
        self._move_folder_if_exists(
            src=model_cache_dir,
            dst=versioned_model_dir,
            ensure_parent=versioned_dir,
            description="model cache folder to versioned folder",
        )

    def _move_folder_if_exists(
        self, src: str, dst: str, ensure_parent: Optional[str] = None, description: str = ""
    ) -> None:
        """Move a folder from src to dst if it exists, creating parent if needed, and log the result.

        Args:
            src (str): Source folder path.
            dst (str): Destination folder path.
            ensure_parent (str, optional): Parent directory to create before moving.
            description (str, optional): Description for logging.

        """
        if os.path.exists(src):
            if ensure_parent:
                os.makedirs(ensure_parent, exist_ok=True)
            try:
                shutil.move(src, dst)
                self.logger.info(f"Moved {description}: {src} -> {dst}")
            except Exception as e:
                self.logger.warning(f"Failed to move {description}: {src} -> {dst}: {e}")

    def _build_iods_model(self, iod_entry_list: List[IODEntry]) -> dict[str, IODEntry]:
        """Build a dict mapping table_id to IODEntry objects.

        Args:
            iod_entry_list (List[IODEntry]): List of IODEntry objects.

        Returns:
            dict: Dict mapping table_id to the corresponding IODEntry.

        """
        return {iod.table_id: iod for iod in iod_entry_list}

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

    def _standard_cache_dir(self) -> str:
        return os.path.join(self.config.cache_dir, "standard")

    def _model_cache_dir(self) -> str:
        return os.path.join(self.config.cache_dir, "model")

    def _versioned_dir(self, version: str) -> str:
        return os.path.join(self.config.cache_dir, version)

    def _versioned_standard_dir(self, version: str) -> str:
        return os.path.join(self._versioned_dir(version), "standard")

    def _versioned_model_dir(self, version: str) -> str:
        return os.path.join(self._versioned_dir(version), "model")
