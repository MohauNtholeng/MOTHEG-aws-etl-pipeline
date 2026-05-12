"""CLI for local ETL execution and validation."""

from __future__ import annotations

import argparse
from pathlib import Path

from .orchestration import (
    DEFAULT_QUALITY_RULES,
    DEFAULT_SCHEMA,
    render_state_machine_input,
    run_local_pipeline,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run MOTHEG ETL jobs locally")
    parser.add_argument("--source", default="samples/input/events.jsonl")
    parser.add_argument("--raw-output", default="build/raw/events.jsonl")
    parser.add_argument("--dedupe-store", default="build/state/idempotency_keys.jsonl")
    parser.add_argument("--curated-output", default="build/curated")
    args = parser.parse_args()

    result = run_local_pipeline(
        source_path=Path(args.source),
        raw_output_path=Path(args.raw_output),
        dedupe_store_path=Path(args.dedupe_store),
        curated_output_root=Path(args.curated_output),
        schema=DEFAULT_SCHEMA,
        quality_rules=DEFAULT_QUALITY_RULES,
    )
    print(render_state_machine_input(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
