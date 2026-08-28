"""Unit tests for the pure logic in dcmspec_explorer.app_config."""

import pytest

from dcmspec_explorer.app_config import parse_bool


class TestParseBool:
    """Tests for parse_bool."""

    @pytest.mark.parametrize(
        "value, expected",
        [
            (True, True),
            (False, False),
            ("true", True),
            ("yes", True),
            ("on", True),
            ("1", True),
            ("false", False),
            ("no", False),
            ("off", False),
            ("0", False),
            ("", False),
            (1, True),
            (0, False),
            (None, False),
        ],
    )
    def test_converts_value_to_expected_bool(self, value, expected):
        """parse_bool handles Python bools, common truthy/falsy strings, and other types via bool()."""
        assert parse_bool(value) is expected
