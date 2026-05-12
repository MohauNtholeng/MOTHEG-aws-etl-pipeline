from __future__ import annotations

import json
from pathlib import Path

from motheg_etl.transformation import run_transformation


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as file:
        for row in rows:
            file.write(json.dumps(row) + "\n")


def test_transformation_partitions_and_quality_checks(tmp_path: Path) -> None:
    source = tmp_path / "raw.jsonl"
    out = tmp_path / "curated"

    _write_jsonl(
        source,
        [
            {"id": "1", "event_date": "2026-05-10T09:00:00Z", "amount": 10, "source": "app"},
            {"id": "2", "event_date": "2026-05-10", "amount": -5, "source": "app"},
        ],
    )

    stats = run_transformation(
        source,
        out,
        quality_rules={
            "required": ["id", "event_date", "amount", "source"],
            "non_negative": ["amount"],
        },
    )

    assert stats.total_records == 2
    assert stats.transformed_records == 1
    assert stats.rejected_records == 1

    partition_file = out / "event_date=2026-05-10" / "data.jsonl"
    assert partition_file.exists()
    transformed = json.loads(partition_file.read_text(encoding="utf-8").strip())
    assert transformed["event_date"] == "2026-05-10"
    assert "processed_at" in transformed
