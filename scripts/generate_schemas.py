import json
from pathlib import Path

from lifeline.models import DecisionRecord, EvidenceManifest, MissionSnapshot, ScenarioDefinition

ROOT = Path(__file__).resolve().parents[1]
MODELS = {
    "snapshot.schema.json": MissionSnapshot,
    "decision-record.schema.json": DecisionRecord,
    "scenario.schema.json": ScenarioDefinition,
    "evidence-manifest.schema.json": EvidenceManifest,
}

for filename, model in MODELS.items():
    target = ROOT / "schemas" / filename
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(model.model_json_schema(), indent=2) + "\n", encoding="utf-8")
