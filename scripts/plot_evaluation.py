"""Plot measured Text-to-SQL results, never fabricated training metrics.

Run in repository root:
    python -m pip install matplotlib
    python scripts/plot_evaluation.py

Reads generated local JSON files in results/ and saves docs/figures/*.png.
"""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[1]
LIVE = ROOT / "results" / "evaluation_latest.json"
NEGATIVE = ROOT / "results" / "negative_cases_latest.json"
OUT = ROOT / "docs" / "figures"


def read_json(path: Path) -> dict:
    if not path.is_file():
        raise SystemExit(f"Missing {path.relative_to(ROOT)}. Run the corresponding evaluation script first.")
    return json.loads(path.read_text(encoding="utf-8"))


def finish(fig, name: str) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT / name, dpi=180, bbox_inches="tight")
    plt.close(fig)
    print(f"Created {OUT / name}")


def plot_live_overview(data: dict) -> None:
    s = data["summary"]
    categories = ["Exact answers", "Clarifications"]
    observed = [s["exact_answer_matches"], s["correct_clarifications"]]
    total = [s["answerable_cases"], s["ambiguous_cases"]]
    fig, ax = plt.subplots(figsize=(8.5, 4.5))
    bars = ax.barh(categories, observed)
    ax.invert_yaxis()
    ax.set_xlim(0, max(total + [1]) * 1.2)
    ax.set_xlabel("Cases matched")
    ax.set_title("Local model benchmark outcomes (single 10-question run)")
    for bar, got, n in zip(bars, observed, total):
        ax.text(bar.get_width() + 0.12, bar.get_y() + bar.get_height()/2,
                f"{got}/{n}", va="center")
    fig.text(.01, .01, "Small synthetic benchmark; not general model accuracy.", fontsize=9)
    finish(fig, "benchmark_outcomes.png")


def plot_latency(data: dict) -> None:
    cases = [x for x in data.get("cases", []) if isinstance(x.get("latency_s"), (int, float))]
    if not cases:
        print("Skipping latency_by_question.png: no per-case timing values supplied.")
        return
    labels = [x.get("id", f"case_{i+1}").replace("_", " ") for i, x in enumerate(cases)]
    vals = [x["latency_s"] for x in cases]
    height = max(4, len(cases)*.45+1.2)
    fig, ax = plt.subplots(figsize=(9, height))
    ax.barh(labels, vals)
    ax.invert_yaxis()
    ax.set_xlabel("End-to-end latency (seconds)")
    ax.set_title("Measured time per benchmark question")
    ax.set_xlim(0, max(vals + [1]) * 1.16)
    for i, value in enumerate(vals):
        ax.text(value + max(vals + [1]) * .015, i, f"{value:.2f}s", va="center", fontsize=8)
    fig.tight_layout()
    finish(fig, "latency_by_question.png")


def plot_validation_status(data: dict) -> None:
    counts = Counter(x.get("validation_status") or "not run" for x in data.get("cases", [])
                     if x.get("observed_status") == "executed")
    if not counts:
        print("Skipping validation_status.png: no executed cases with validation data.")
        return
    keys = sorted(counts)
    vals = [counts[k] for k in keys]
    fig, ax = plt.subplots(figsize=(7, 4))
    bars = ax.bar(keys, vals)
    ax.set_title("Semantic validation statuses for executed benchmark queries")
    ax.set_ylabel("Number of queries")
    ax.set_ylim(0, max(vals) + 1.5)
    for b, v in zip(bars, vals):
        ax.text(b.get_x() + b.get_width()/2, v + .1, str(v), ha="center")
    fig.tight_layout()
    finish(fig, "validation_status.png")


def plot_negative_regressions(data: dict) -> None:
    cases = data.get("cases", [])
    if not cases:
        print("Skipping negative_case_checks.png: no case-level regression data.")
        return
    correct_accept = sum(x.get("expected_status") == "pass" and x.get("as_expected") is True for x in cases)
    incorrect_warn = sum(x.get("expected_status") == "warning" and x.get("as_expected") is True for x in cases)
    unexpected = sum(x.get("as_expected") is not True for x in cases)
    labels = ["Expected passes", "Expected warnings", "Unexpected outcomes"]
    vals = [correct_accept, incorrect_warn, unexpected]
    fig, ax = plt.subplots(figsize=(8, 4))
    bars = ax.bar(labels, vals)
    ax.set_title("Targeted fixed-SQL semantic regression checks (no LLM)")
    ax.set_ylabel("Cases")
    ax.set_ylim(0, max(vals + [1]) + 1)
    for b, v in zip(bars, vals):
        ax.text(b.get_x()+b.get_width()/2, v+.1, str(v), ha="center")
    fig.text(.01, .01, "Five selected patterns; not a general hallucination-detection rate.", fontsize=9)
    finish(fig, "negative_case_checks.png")


def main() -> None:
    live = read_json(LIVE)
    negative = read_json(NEGATIVE)
    plot_live_overview(live)
    plot_latency(live)
    plot_validation_status(live)
    plot_negative_regressions(negative)
    print("Figures are ready in docs/figures/. Review plots before committing them.")


if __name__ == "__main__":
    main()
