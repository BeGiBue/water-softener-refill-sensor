"""Tests mit echtem Home Assistant (pytest-homeassistant-custom-component).

Aufruf (im Repository-Wurzelverzeichnis): pip install -r requirements_test.txt && pytest tests_ha
"""
from __future__ import annotations

import pathlib

import pytest

pytest_plugins = "pytest_homeassistant_custom_component"

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _register_custom_components() -> None:
    """Das Paket custom_components des Plugins verdeckt das des Repositorys: Pfad ergänzen."""
    import custom_components

    ours = str(ROOT / "custom_components")
    if ours not in list(custom_components.__path__):
        custom_components.__path__.append(ours)


_register_custom_components()


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    yield
