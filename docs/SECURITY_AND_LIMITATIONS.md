# Safety boundary and limitations

## Implemented and tested in scope

- A SQLGlot AST allowlist admits a narrow single-SELECT subset against named allowlisted tables.
- Unsupported SQL constructs and destructive statements are rejected by the policy in targeted tests.
- Joins must match the validator's narrow explicit equijoin rules.
- SQL is executed via a DuckDB connection opened read-only; output rows are capped with a limit.
- The local API receives a bounded string input and returns structured results without exposing raw server stack traces to clients.
- Pattern-based semantic checks report pass/warning/unverified for supported question types.

## What is not guaranteed

- **No proven unbounded-query protection.** `LIMIT 1000` does not bound intermediate joins, full scans, memory, or execution time.
- **Not a full SQL verifier.** The allowlist does not validate all column names against schema metadata or prove joins match declared foreign keys.
- **Not safe to expose publicly.** No authentication, user-specific permissions, request throttling, network isolation, hardened deployment, or abuse controls have been demonstrated.
- **Not a general hallucination detector.** Current semantics checks are schema- and question-pattern-specific; an unsupported question may be marked unverified.
- **No calibrated correctness probability.** A score of 100 signals that implemented assertions passed, not certainty.
- **No proof of comprehensive destructive-query blocking.** Passing sampled security tests is not equivalent to exhaustive proof.
- **No data confidentiality claim.** The shipped database is synthetic; adapting this to real business data requires independent privacy, access-control and retention review.

## Threat model in one sentence

This project reduces risk from inadvertent SQL-generation mistakes in a **single-user, local synthetic-data demo**; it is not a security boundary suitable for untrusted public users or sensitive enterprise data.

## Before any real-world use

Would require database-enforced least privilege, query execution time/memory limits, stronger column/relationship checks, authentication and access control, rate limiting, auditing with privacy controls, security review, and broader correctness evaluation.
