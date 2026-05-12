"""Transformation job with partitioning and quality checks."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .ingestion import _load_jsonl


class DataQualityError(ValueError):
    """Raised when a record fails data-quality checks."""


@dataclass(slots=True)
class TransformationStats:
    total_records: int = 0
    transformed_records: int = 0
    rejected_records: int = 0


def _normalize_date(value: str) -> str:
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    dt = datetime.fromisoformat(value)
    return dt.date().isoformat()


def _validate_quality(record: dict[str, Any], quality_rules: dict[str, Any]) -> None:
    required_fields = quality_rules.get("required", [])
    for field in required_fields:
        if record.get(field) in (None, ""):
            raise DataQualityError(f"required field missing or empty: {field}")

    non_negative_fields = quality_rules.get("non_negative", [])
    for field in non_negative_fields:
        value = record.get(field)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise DataQualityError(f"field must be numeric: {field}")
        if value < 0:
            raise DataQualityError(f"field must be non-negative: {field}")


def _transform_record(record: dict[str, Any]) -> dict[str, Any]:
    transformed = dict(record)
    transformed["event_date"] = _normalize_date(str(record["event_date"]))
    transformed["processed_at"] = datetime.now(UTC).isoformat()
    return transformed


def run_transformation(
    input_path: Path,
    output_root: Path,
    quality_rules: dict[str, Any],
    partition_field: str = "event_date",
) -> TransformationStats:
    """Transform JSONL records into partitioned output."""
    stats = TransformationStats()
    records = _load_jsonl(input_path)

    for record in records:
        stats.total_records += 1
        try:
            _validate_quality(record, quality_rules)
            transformed = _transform_record(record)
            partition_value = transformed[partition_field]
        except (DataQualityError, KeyError, ValueError):
            stats.rejected_records += 1
            continue

        partition_dir = output_root / f"{partition_field}={partition_value}"
        partition_dir.mkdir(parents=True, exist_ok=True)
        with (partition_dir / "data.jsonl").open("a", encoding="utf-8") as file:
            file.write(json.dumps(transformed, separators=(",", ":")) + "\n")

        stats.transformed_records += 1

    return stats
