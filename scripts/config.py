"""config.py — sources.yaml loader (pydantic-settings) + store.config.json reader.

sources.yaml is real YAML (anchors/aliases included); pyyaml parses the text
and pydantic-settings models validate the structure — every section (run,
catalogs, launches, code, adoption, quality_gate, chatter, watchlist, gate)
gets typed defaults, and a malformed file raises ConfigError naming the
offending section/key instead of a KeyError or raw traceback. Read as
utf-8-sig so a Windows-editor BOM can't poison the first key.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, ValidationError
from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
)


class ConfigError(Exception):
    """Raised when sources.yaml is missing, unparseable, or invalid."""


# ── leaf models ──────────────────────────────────────────────────────────
class SourceEntry(BaseModel):
    """One source under catalogs/launches/code/adoption/chatter.

    Kinds vary per collector (api, rss, graphql, html_scrape, ...), so all
    kind-specific fields are allowed through untouched and model_dump()
    returns them exactly as written — collectors see the same dicts as
    before, now shape-validated instead of raw.
    """

    model_config = ConfigDict(extra="allow")

    kind: str | None = None
    endpoint: str | None = None


class SecuritySection(BaseModel):
    model_config = ConfigDict(extra="allow")

    osv_endpoint: str = "https://api.osv.dev/v1/query"
    red_flags: list[str] = []


class QualityGateSection(BaseModel):
    model_config = ConfigDict(extra="allow")

    staleness_max_days: int = 90
    star_floor: int = 10
    security: SecuritySection = SecuritySection()


class RunSection(BaseModel):
    model_config = ConfigDict(extra="allow")

    disable: list[str] = []
    inbox_name: str = "%Y-%m-%d-%H%M"


class WatchlistSection(BaseModel):
    model_config = ConfigDict(extra="allow")

    repos: list[str] = []
    packages: list[str] = []
    keywords: list[str] = []


class GateSection(BaseModel):
    model_config = ConfigDict(extra="allow")

    apply_to: list[str] = []
    reject_if: list[str] = []
    on_reject: str | None = None


class SourcesSettings(BaseSettings):
    """Top-level sources.yaml document, loaded from the YAML file only."""

    model_config = SettingsConfigDict(extra="ignore")

    run: RunSection = RunSection()
    catalogs: dict[str, SourceEntry] = {}
    launches: dict[str, SourceEntry] = {}
    code: dict[str, SourceEntry] = {}
    adoption: dict[str, SourceEntry] = {}
    quality_gate: QualityGateSection = QualityGateSection()
    chatter: dict[str, SourceEntry] = {}
    watchlist: WatchlistSection = WatchlistSection()
    gate: GateSection = GateSection()

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        # sources.yaml is the single source of truth; no env/dotenv secrets.
        return (YamlFileSource(settings_cls),)


class YamlFileSource(PydanticBaseSettingsSource):
    """Settings source that reads (and yaml-parses) the sources.yaml path."""

    def __init__(self, settings_cls: type[BaseSettings], path: Path | None = None) -> None:
        super().__init__(settings_cls)
        if path is None:  # sources.yaml lives beside this package
            path = Path(__file__).resolve().parent.parent / "sources.yaml"
        self._path = path
        try:
            text = path.read_text(encoding="utf-8-sig")
        except FileNotFoundError as e:
            raise ConfigError(f"sources.yaml not found at {path}") from e
        try:
            doc = yaml.safe_load(text)
        except yaml.YAMLError as e:
            raise ConfigError(f"sources.yaml is not valid YAML: {e}") from e
        self._data: dict[str, Any] = doc if isinstance(doc, dict) else {}

    def get_field_value(self, field, field_name):  # required abstract hook
        return self._data.get(field_name), field_name, False

    def __call__(self) -> dict[str, Any]:
        return self._data


def load_sources(store_root: Path) -> dict:
    # sources.yaml is code/config: lives beside this package in the project
    # root (knowledge-base/projects/tech-trends/), NOT in the raw store.
    project_root = Path(__file__).resolve().parent.parent
    path = project_root / "sources.yaml"
    try:
        settings = SourcesSettings()
    except ValidationError as e:
        raise ConfigError(
            f"sources.yaml failed validation ({path}):\n{e}"
        ) from e
    return settings.model_dump()


def load_store_config() -> dict:
    """Read scripts/store.config.json (data-root overrides; see paths.py).

    Returns {} when the file is absent (all defaults apply). Malformed
    JSON raises — a typo must not silently reroute the data root.
    """
    cfg_path = Path(__file__).resolve().parent / "store.config.json"
    if not cfg_path.exists():
        return {}
    import json
    cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    return cfg if isinstance(cfg, dict) else {}
