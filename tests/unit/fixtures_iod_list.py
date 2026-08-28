"""Fixture helpers built from a real excerpt of the DICOM PS3.3 "list of tables" page.

The excerpt lives at tests/fixtures/ps3_3_list_of_tables_excerpt.html and is regenerated
via scripts/extract_test_fixtures.py -- see that script's docstring for how to refresh it
against a newer DICOM standard release.
"""

from pathlib import Path

from bs4 import BeautifulSoup

FIXTURE_PATH = Path(__file__).resolve().parent.parent / "fixtures" / "ps3_3_list_of_tables_excerpt.html"


def list_of_tables_soup() -> BeautifulSoup:
    """Return a parsed BeautifulSoup fragment for the real list-of-tables excerpt."""
    return BeautifulSoup(FIXTURE_PATH.read_text(encoding="utf-8"), "html.parser")
