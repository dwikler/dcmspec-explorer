"""Shared fixtures for unit tests (isolated collaborators, no real I/O beyond tmp_path)."""

import logging

import pytest


@pytest.fixture
def fake_logger():
    """Return a logger with a NullHandler so tests don't spam stdout."""
    logger = logging.getLogger("dcmspec_explorer.test")
    logger.handlers = [logging.NullHandler()]
    logger.setLevel(logging.DEBUG)
    return logger
