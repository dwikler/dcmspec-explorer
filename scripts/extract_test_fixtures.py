"""Regenerate tests/fixtures/ps3_3_list_of_tables_excerpt.html from a local ps3.3.html.

Run manually after a DICOM standard update (poetry run python scripts/extract_test_fixtures.py)
and re-review the diff -- chosen table_ids may be renumbered or removed between versions.
"""

import re
from pathlib import Path

from bs4 import BeautifulSoup

SOURCE = Path("cache/standard/ps3.3.html")
DEST = Path("tests/fixtures/ps3_3_list_of_tables_excerpt.html")
# One representative table_id per _extract_iod_list kind branch, plus a couple of
# non-"IOD Modules" dt texts to exercise the skip-non-IOD branch.
WANTED_TABLE_IDS = {"table_A.2-1", "table_B.7-1", "table_F.3-1"}
WANTED_OTHER_TEXTS = {"5.4-1. Example Module Table", "8.8-1. Code Sequence Macro Attributes"}


def main():
    """Extract a small set of real <dt> entries from ps3.3.html into a test fixture file."""
    soup = BeautifulSoup(SOURCE.read_text(encoding="utf-8"), "html.parser")
    version_match = re.search(r"DICOM PS3\.3 (\S+) -", soup.text)
    version = version_match[1] if version_match else "unknown"
    list_of_tables = soup.find("div", class_="list-of-tables")
    kept = [
        dt
        for dt in list_of_tables.find_all("dt")
        if (a := dt.find("a"))
        and (
            (a.get("href", "").split("#")[-1] in WANTED_TABLE_IDS)
            or " ".join(dt.get_text().split()) in WANTED_OTHER_TEXTS
        )
    ]
    body = "\n".join(str(dt) for dt in kept)
    DEST.write_text(
        f"<!-- Extracted from DICOM PS3.3 {version} via scripts/extract_test_fixtures.py -->\n"
        f'<div class="list-of-tables"><dl>\n{body}\n</dl></div>\n',
        encoding="utf-8",
    )
    print(f"Wrote {DEST} ({len(kept)} entries, source version {version})")


if __name__ == "__main__":
    main()
