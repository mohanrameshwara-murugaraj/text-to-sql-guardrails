# Evaluation methodology and observed evidence

## Source and reproducibility

The following summary was copied from the project author's **live terminal output on 2026-11-12**, produced by `python scripts/evaluate.py` against the synthetic `data/sales.duckdb` and local Ollama model. It has not been rerun inside this documentation authoring environment. The detailed per-case JSON remains on the author's Mac at `results/evaluation_latest.json` and is **not** bundled here.

```json
{
  "answerable_cases": 8,
  "exact_answer_matches": 8,
  "exact_answer_accuracy": 1.0,
  "executed_answerable_cases": 8,
  "execution_rate": 1.0,
  "ambiguous_cases": 2,
  "correct_clarifications": 2,
  "clarification_rate": 1.0,
  "wrong_executed_answers": 0,
  "wrong_answers_flagged_by_validator": 0,
  "wrong_answer_detection_rate": null,
  "mean_latency_s": 7.249,
  "statuses": {"executed": 8, "clarification": 2}
}
```

## Interpretation

- **Exact result agreement:** eight of eight answerable questions matched the hand-written reference SQL's result table. This is a *single small local benchmark*, not an estimate of real-world success rate.
- **Clarification:** two of two deliberately ambiguous questions returned a clarification response. This measures only those examples.
- **Latency:** `7.249 s` is the mean elapsed time per question over all ten cases, not a database-only query execution time.
- **Detection:** `null` is correct: there were zero wrong executed answers to test whether the detector flags them. Never replace this field with `100%`.
- **Scope:** comparisons ignore row order and column alias text, but require equal row/column counts and corresponding values. Some schema-specific queries are close to included few-shot examples; the sample is not a held-out production dataset.

## What CI covers

Deterministic tests cover policy and pipeline behavior using stubbed integrations. CI without the local Qwen model cannot reproduce the ten live LLM outputs and should not claim to do so. Local `pytest -q` and `python scripts/evaluate.py` answer different questions.

## Targeted negative tests

`tests/test_customer_count_negative.py` contains five previously passed regression tests covering valid customer counts and invalid joined-row/order counts. The additional `scripts/evaluate_negative.py` script in Milestone 10 records a fixed set of semantic checks with explicit expected status and a JSON report. **Results from this new script are unverified until run locally.**

These checks demonstrate detection of narrow known failures; they do not establish detector recall, precision, or robustness against unseen or adversarial SQL.

## Evidence improvements that would change the claims

A larger, separately curated set of wrong-but-executable queries with known ground-truth labels is needed before publishing detection precision/recall or false-positive rates. Likewise, general text-to-SQL accuracy needs varied, held-out schemas and multiple model runs; none of that is asserted here.
