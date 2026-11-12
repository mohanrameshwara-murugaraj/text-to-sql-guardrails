# Project Summary — Safe Text-to-SQL

**One-line overview:** I built a local natural-language analytics interface that turns business questions into SQL and adds explicit safety controls and limited semantic verification before presenting the results.

## The problem

LLMs can create SQL that executes successfully but answers the wrong business question. A valid result is not necessarily a reliable business answer. Enterprise analytics tools also need to keep generated SQL away from write-capable database access.

## What I built

I used a synthetic sales schema in DuckDB and a local Qwen 2.5 Coder model through Ollama. The application selects relevant schema context, requests structured SQL, checks the candidate with an AST-based allowlist, executes approved SQL on a read-only connection, and shows results in Streamlit through a FastAPI backend. A deterministic validation module flags a few known semantic mistakes, such as counting joined order rows when asked for distinct customers.

## My engineering decisions

- I separated generation from SQL execution, so the model never authorizes its own queries.
- I used explicit business definitions and clarification handling instead of guessing ambiguous terms such as “revenue.”
- I made the correctness checks explainable, and allowed the verifier to report “unverified” instead of manufacturing confidence.
- I kept the model local to avoid recurring API charges and built deterministic tests that do not depend on Ollama being available.

## Evidence

The latest recorded local run completed **91 automated tests**. In a separate **10-question synthetic-database benchmark**, the system matched reference SQL results on **8/8 answerable questions** and returned the expected clarification status for **2/2 ambiguous questions**. Average latency was **7.249 seconds per question**. These results describe that run, not a generalized accuracy rate.

No incorrect executed answers occurred in that benchmark, so it **did not measure the hallucination detector's live recall**. Separate targeted regression cases exercise specific known-wrong SQL patterns, but these are not a representative detection benchmark.

## Main challenge and what I learned

The difficult part was distinguishing “SQL that runs” from “SQL that answers the question.” A JOIN can silently multiply records while leaving SQL syntactically valid and results plausible. Adding a semantic check for customer entity counting forced me to validate the meaning of aggregates, not just their presence.

## Scope

This is a **local portfolio MVP**, not a deployed enterprise product. Authentication, resource isolation, and broad semantic correctness are not demonstrated. The README includes reproducible setup instructions, evaluation interpretation, and explicit limitations.
