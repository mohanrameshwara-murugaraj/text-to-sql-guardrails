# Final GitHub release checklist

This overlay **adds** documentation, CI and a targeted report script. It does not publish your repository or verify your Mac environment.

## 1. Install overlay into existing project

Copy only the new files, preserving `src/`, existing tests, database generator, and all previous changes. The overlay's README replaces the old short README; back up the old version first if it includes any information unique to your repository.

## 2. Final local checks

```bash
source .venv/bin/activate
python -m pip install -e '.[dev]'
python -m pip install -r requirements-milestone8.txt
pytest -q
python scripts/evaluate_negative.py
python scripts/evaluate.py
```

`python scripts/evaluate.py` makes real model calls and requires Ollama locally; only run it if you wish to reproduce the ten-question benchmark. The other tests must work without downloading Qwen in CI.

Check that both FastAPI and Streamlit still respond locally (see README).

## 3. Review files, ignore patterns and sensitive material

```bash
git status --short
git diff --check
git ls-files | grep -E '(\.env$|\.duckdb$|__pycache__|\.venv/|\.pyc$)' || true
```

Generated database files and `results/*_latest.json` should be ignored. Commit the synthetic input generation code, labeled benchmark questions, documentation, and CI workflow. Do not commit Ollama weights or machine-specific credentials.

## 4. Check repository state before any push

```bash
git status
git diff --stat
git remote -v
```

Review the staged changes, run all tests, then commit and push **only when you explicitly decide to**. A successful local run doesn't prove CI success: inspect GitHub Actions after pushing.

## 5. Evidence to publish

- The 10-case benchmark results with scope and limitations visible alongside the metrics.
- Optional screenshot of your actual Streamlit run (with generated SQL and validation signals).
- A separate negative-case JSON report only **after** it has been executed and checked locally.

## Completion standard

**Portfolio MVP complete** after local tests and UI are verified, GitHub CI passes, documentation accurately matches the committed code, and the intended repository is published. Do not claim production readiness.
