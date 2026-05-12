from __future__ import annotations

import json
from pathlib import Path

from motheg_etl.ingestion import ingest_records


SCHEMA = {
    "required": ["id", "event_date", "amount", "source"],
    "properties": {
        "id": "str",
        "event_date": "str",
        "amount": "number",
        "source": "str",
    },
}


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as file:
        for row in rows:
            file.write(json.dumps(row) + "\n")


def test_ingestion_validates_schema_and_deduplicates(tmp_path: Path) -> None:
    source = tmp_path / "input.jsonl"
    out = tmp_path / "raw.jsonl"
    dedupe = tmp_path / "dedupe.jsonl"

    _write_jsonl(
        source,
        [
            {"id": "1", "event_date": "2026-05-10", "amount": 10, "source": "app"},
            {"id": "1", "event_date": "2026-05-10", "amount": 10, "source": "app"},
            {"id": "2", "amount": 12, "source": "app"},
        ],
    )

    stats = ingest_records(source, out, SCHEMA, dedupe, idempotency_fields=["id", "event_date"])

    assert stats.total_records == 3
    assert stats.ingested_records == 1
    assert stats.duplicate_records == 1
    assert stats.invalid_records == 1

    lines = out.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
