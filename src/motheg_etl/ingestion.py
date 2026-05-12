"""Ingestion job with schema validation, idempotency, and retry handling."""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class SchemaValidationError(ValueError):
    """Raised when a record does not match schema requirements."""


@dataclass(slots=True)
class IngestionStats:
    total_records: int = 0
    ingested_records: int = 0
    invalid_records: int = 0
    duplicate_records: int = 0


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    if not path.exists():
        return records
    with path.open("r", encoding="utf-8") as file:
        for line in file:
            raw = line.strip()
            if not raw:
                continue
            loaded = json.loads(raw)
            if not isinstance(loaded, dict):
                raise ValueError("JSONL rows must contain JSON objects")
            records.append(loaded)
    return records


def _json_type_matches(value: Any, type_name: str) -> bool:
    mapping = {
        "str": str,
        "int": int,
        "float": float,
        "number": (int, float),
        "bool": bool,
        "list": list,
        "dict": dict,
    }
    expected = mapping.get(type_name)
    if expected is None:
        return True
    if type_name in {"int", "float", "number"} and isinstance(value, bool):
        return False
    return isinstance(value, expected)


def validate_record(record: dict[str, Any], schema: dict[str, Any]) -> None:
    required_fields = schema.get("required", [])
    if not isinstance(required_fields, list):
        raise SchemaValidationError("schema.required must be a list")

    for field in required_fields:
        if field not in record:
            raise SchemaValidationError(f"missing required field: {field}")

    properties = schema.get("properties", {})
    if not isinstance(properties, dict):
        raise SchemaValidationError("schema.properties must be a dictionary")

    for field, expected_type in properties.items():
        if field not in record or not isinstance(expected_type, str):
            continue
        if not _json_type_matches(record[field], expected_type):
            raise SchemaValidationError(
                f"field '{field}' expected type '{expected_type}', got '{type(record[field]).__name__}'"
            )


def _idempotency_key(record: dict[str, Any], key_fields: list[str] | None) -> str:
    if key_fields:
        materialized = {field: record.get(field) for field in key_fields}
    else:
        materialized = record
    packed = json.dumps(materialized, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(packed).hexdigest()


def _retry(operation: Any, max_retries: int, base_delay_seconds: float = 0.2) -> Any:
    for attempt in range(max_retries + 1):
        try:
            return operation()
        except OSError:
            if attempt == max_retries:
                raise
            time.sleep(base_delay_seconds * (2**attempt))
    raise RuntimeError("unreachable")


def ingest_records(
    input_path: Path,
    output_path: Path,
    schema: dict[str, Any],
    idempotency_store_path: Path,
    idempotency_fields: list[str] | None = None,
    max_retries: int = 3,
) -> IngestionStats:
    """Run ingestion from input JSONL into validated raw zone JSONL output."""
    stats = IngestionStats()
    input_records = _load_jsonl(input_path)

    seen_keys = {
        row["key"]
        for row in _load_jsonl(idempotency_store_path)
        if isinstance(row, dict) and isinstance(row.get("key"), str)
    }
    accepted: list[dict[str, Any]] = []
    new_keys: list[dict[str, str]] = []

    for record in input_records:
        stats.total_records += 1
        try:
            validate_record(record, schema)
        except SchemaValidationError:
            stats.invalid_records += 1
            continue

        dedupe_key = _idempotency_key(record, idempotency_fields)
        if dedupe_key in seen_keys:
            stats.duplicate_records += 1
            continue

        seen_keys.add(dedupe_key)
        accepted.append(record)
        new_keys.append({"key": dedupe_key})
        stats.ingested_records += 1

    output_path.parent.mkdir(parents=True, exist_ok=True)
    idempotency_store_path.parent.mkdir(parents=True, exist_ok=True)

    def append_records() -> None:
        with output_path.open("a", encoding="utf-8") as file:
            for record in accepted:
                file.write(json.dumps(record, separators=(",", ":")) + "\n")

    def append_dedupe_keys() -> None:
        with idempotency_store_path.open("a", encoding="utf-8") as file:
            for row in new_keys:
                file.write(json.dumps(row, separators=(",", ":")) + "\n")

    _retry(append_records, max_retries=max_retries)
    _retry(append_dedupe_keys, max_retries=max_retries)
    return stats
