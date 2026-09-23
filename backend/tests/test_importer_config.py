from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from importer.config import ImportConfig, load_config
from importer.settings import PROJECT_ROOT
from tests.test_importer_build import make_config


def test_repository_config_is_valid() -> None:
    config = load_config(PROJECT_ROOT / "config" / "import.yaml")
    assert "en" in config.languages
    assert config.numeric_fame_threshold > config.fame_threshold


def test_type_threshold_falls_back_to_default() -> None:
    config = make_config()
    assert config.type_fame_threshold("country") == 50
    assert config.type_fame_threshold("city") == 100


def test_class_to_type_prefers_first_configured_type() -> None:
    config = make_config(
        entity_types={
            "country": {"classes": ["Q6256"]},
            "state": {"classes": ["Q6256", "Q7275"]},
            "city": {"classes": ["Q515"]},
        }
    )
    assert config.class_to_type() == {
        "Q6256": "country",
        "Q7275": "state",
        "Q515": "city",
        "Q5": "person",
    }


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"languages": ["de"]}, "must include 'en'"),
        (
            {"related_types": {"country": {"classes": ["Q5"]}}},
            "defined as entity and related type",
        ),
        (
            {"relations": [{"property": "P36", "name": "CAPITAL", "fallback_target_type": "x"}]},
            "unknown fallback_target_type",
        ),
        (
            {
                "relations": [
                    {"property": "P36", "name": "CAPITAL"},
                    {"property": "P36", "name": "OTHER"},
                ]
            },
            "duplicate relation property",
        ),
        (
            {"numeric_properties": [{"property": "P2046", "name": "area", "unit": "km2"}]},
            "has no conversions",
        ),
        (
            {"date_properties": [{"property": "P571", "name": "label", "tier": "base"}]},
            "reserved node property names",
        ),
        ({"relations": [{"property": "P36", "name": "capital"}]}, "String should match"),
        ({"entity_types": {"country": {"classes": ["6256"]}}}, "String should match"),
    ],
)
def test_invalid_config_is_rejected(overrides: dict[str, Any], message: str) -> None:
    with pytest.raises(ValidationError, match=message):
        make_config(**overrides)


def test_unknown_keys_are_rejected(tmp_path: Path) -> None:
    config_file = tmp_path / "import.yaml"
    config_file.write_text("languages: [en]\nunexpected: 1\n", encoding="utf-8")
    with pytest.raises(ValidationError, match="unexpected"):
        load_config(config_file)


def test_config_is_immutable() -> None:
    config = make_config()
    with pytest.raises(ValidationError):
        config.fame_threshold = 1  # type: ignore[misc]
    assert isinstance(config, ImportConfig)
