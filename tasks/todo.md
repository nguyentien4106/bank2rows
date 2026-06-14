# TODO: Free-Quota + Per-Page Billing — ✅ COMPLETE

Full plan: [tasks/plan.md](plan.md) · Spec: [SPEC.md](../SPEC.md)

Rules: 50 free pages/month (calendar month, Asia/Ho_Chi_Minh) · 500 VND/page overage ·
page = OCR `total_pages` · charge at OCR completion · failed jobs free · charge what they
have & deliver on shortfall · upload-time `pypdf` pre-flight 402 block.

All 7 tasks implemented test-first, one commit each.

## Phase 1 — Billing foundation
- [x] **Task 1:** `MonthlyUsage` model + `FileJob.billed_at` + migration — commit ab5e3a9
- [x] **Task 2:** Quota constants + pure charge math — commit a626320
  - TDD caught a bug: naive `used + job - 50` double-counts overage past quota; corrected to `max(0, job - max(0, free - used))`.
- [x] **Task 3:** `charge_for_job` — idempotent, partial-charge — commit 2f158ad

## Phase 2 — Wire into live flow
- [x] **Task 4:** Charge at OCR `DONE` transition (retry-safe) — commit cddcc60
- [x] **Task 5:** Upload pre-flight `pypdf` estimate + 402 block — commit f525ba9

## Phase 3 — Surface usage + front-end
- [x] **Task 6:** `GET /billing/usage` endpoint — commit 2ad844f
- [x] **Task 7:** FE usage widget + 402 handling (typecheck/lint pass) — commit 3abb7b3

## Pre-req (discovered during build)
- [x] Test harness repaired (legacy `app.crud` imports) + `items` template tests removed — commit d883c85

## Known / flagged
- `mypy` is pre-existing-broken repo-wide (SQLModel `sa_type` overload); new code follows the `# ty:ignore` convention; ruff is clean.
- `tests/api/routes/test_private.py::test_create_user` fails (dev-only `/private` route, `ENVIRONMENT != local`) — pre-existing, unrelated to billing.

## Follow-ups (out of scope)
- [ ] Remove legacy `frontend/` + template `items/` domain (SPEC decision #7)
- [ ] Decide repo-wide type-checker story (install `ty`, fix mypy pattern, or drop mypy from lint gate)
