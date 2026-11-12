"""Run local Text-to-SQL evaluation with the actual installed Ollama model."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from text_to_sql.evaluation import run_evaluation


def main() -> None:
    parser = argparse.ArgumentParser(description="Run live NL-to-SQL evaluation")
    parser.add_argument("--database", default="data/sales.duckdb")
    parser.add_argument("--cases", default="evaluation/cases.json")
    parser.add_argument("--output", default="results/evaluation_latest.json")
    args = parser.parse_args()
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    report = run_evaluation(args.database, args.cases)
    output.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(report["summary"], indent=2))
    print(f"Saved full per-case report to: {output}")


if __name__ == "__main__":
    main()
