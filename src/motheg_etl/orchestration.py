"""Local orchestration helpers and execution plan representation."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .ingestion import IngestionStats, ingest_records
from .transformation import TransformationStats, run_transformation


@dataclass(slots=True)
class PipelineRunResult:
    ingestion: IngestionStats
    transformation: TransformationStats


DEFAULT_SCHEMA: dict[str, Any] = {
    "required": ["id", "event_date", "amount", "source"],
    "properties": {
        "id": "str",
        "event_date": "str",
        "amount": "number",
        "source": "str",
    },
}

DEFAULT_QUALITY_RULES: dict[str, Any] = {
    "required": ["id", "event_date", "amount", "source"],
    "non_negative": ["amount"],
}


def run_local_pipeline(
    source_path: Path,
    raw_output_path: Path,
    dedupe_store_path: Path,
    curated_output_root: Path,
    schema: dict[str, Any] | None = None,
    quality_rules: dict[str, Any] | None = None,
) -> PipelineRunResult:
    """Run ingestion then transformation in-process for validation and local testing."""
    ingestion_stats = ingest_records(
        input_path=source_path,
        output_path=raw_output_path,
        schema=schema or DEFAULT_SCHEMA,
        idempotency_store_path=dedupe_store_path,
        idempotency_fields=["id", "event_date"],
    )

    transformation_stats = run_transformation(
        input_path=raw_output_path,
        output_root=curated_output_root,
        quality_rules=quality_rules or DEFAULT_QUALITY_RULES,
    )
    return PipelineRunResult(ingestion=ingestion_stats, transformation=transformation_stats)


def render_state_machine_input(result: PipelineRunResult) -> str:
    """Render a stable JSON payload suitable for state-machine status logging."""
    payload = {
        "ingestion": result.ingestion.__dict__,
        "transformation": result.transformation.__dict__,
    }
    return json.dumps(payload, sort_keys=True)
