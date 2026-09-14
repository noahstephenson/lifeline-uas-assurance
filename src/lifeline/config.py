from __future__ import annotations

import hashlib
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field

PROJECT_ROOT = Path(__file__).resolve().parents[2]


class FreshnessConfig(BaseModel):
    model_config = ConfigDict(frozen=True)
    operator_link_available: float = Field(gt=0)
    navigation_confidence: float = Field(gt=0)
    energy_margin_wh: float = Field(gt=0)


class NavigationConfig(BaseModel):
    model_config = ConfigDict(frozen=True)
    invalid_below: float
    healthy_at_or_above: float
    recovery_at_or_above: float


class EnergyConfig(BaseModel):
    model_config = ConfigDict(frozen=True)
    usable_capacity_wh: float = Field(gt=0)
    protected_reserve_fraction: float = Field(ge=0, lt=1)
    warning_margin_fraction: float = Field(ge=0, lt=1)
    recovery_margin_fraction: float = Field(ge=0, lt=1)
    critical_margin_wh: float


class SitlConfig(BaseModel):
    model_config = ConfigDict(frozen=True)
    endpoint: str
    allowed_hosts: list[str]
    actions_enabled: bool = False


class LifelineConfig(BaseModel):
    model_config = ConfigDict(frozen=True)
    schema_version: str
    decision_rate_hz: float = Field(gt=0)
    link_activation_dwell_s: float = Field(gt=0)
    recovery_dwell_s: float = Field(gt=0)
    freshness_s: FreshnessConfig
    navigation: NavigationConfig
    energy: EnergyConfig
    sitl: SitlConfig


def load_config(path: Path | None = None) -> LifelineConfig:
    config_path = path or PROJECT_ROOT / "config" / "baseline.yaml"
    return LifelineConfig.model_validate(yaml.safe_load(config_path.read_text(encoding="utf-8")))


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()
