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


def validate_sitl_qualification(path: Path | None = None) -> LifelineConfig:
    baseline = load_config()
    qualification_path = path or PROJECT_ROOT / "config" / "sitl-qualification.yaml"
    qualification = load_config(qualification_path)
    if not qualification.sitl.actions_enabled:
        raise ValueError("SITL qualification profile must explicitly enable actions")
    if qualification.sitl.endpoint != "udpin://127.0.0.1:14540":
        raise ValueError("SITL qualification endpoint must remain loopback-only")
    if set(qualification.sitl.allowed_hosts) != {"127.0.0.1", "localhost"}:
        raise ValueError("SITL qualification allowed hosts must remain loopback-only")
    baseline_data = baseline.model_dump()
    qualification_data = qualification.model_dump()
    baseline_data["sitl"]["actions_enabled"] = True
    if qualification_data != baseline_data:
        raise ValueError("SITL qualification profile may differ from baseline only by actions_enabled")
    return qualification


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()
