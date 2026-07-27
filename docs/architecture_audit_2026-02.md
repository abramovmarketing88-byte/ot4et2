# Architecture Audit – Telegram Bot (Profile-Centric AI Refactor)

## Metadata
- **Date:** 2026-02-19
- **Production readiness score:** 58/100
- **Final verdict:** NOT SAFE
- **Audit type:** Read-only architecture & production safety review
- **Code modified:** No
- **Commit created during audit:** No

## Executive Summary
- The profile-centric refactor is directionally correct: AI domain flows were largely shifted to `profile_id`, and `AISettings` is modeled as a 1:1 entity with `avito_profiles`.
- Despite that progress, production readiness remains limited by multiple high-risk blockers in migration safety, tenant authorization checks, and follow-up processing reliability.
- The migration path appears vulnerable to PostgreSQL constraint ordering failures and incomplete post-remap schema hardening.
- Runtime paths still contain legacy branch abstractions that increase regression risk and conceptual drift.
- Follow-up processing currently lacks robust stuck-job recovery, creating durable message delivery risk under crash/restart scenarios.
- **Overall production readiness score remains 58/100, with verdict NOT SAFE until critical remediations are completed and validated.**

## Critical Issues
1. **Migration can hard-fail when dropping columns involved in composite PK/unique constraints.**
   - Earlier schema variants used composite constraints containing `branch_id` (e.g., in dialog state semantics).
   - Dropping legacy key columns without explicitly dropping/recreating dependent PK/unique constraints first is a likely PostgreSQL hard failure.
   - Even if migration passes in some environments, it risks semantic inconsistency in constraints.

2. **Schema rebind after `profile_id` remap is incomplete (FK/NOT NULL/index hardening gaps).**
   - `profile_id` is introduced and backfilled, but required post-backfill hardening is not fully enforced.
   - Missing/uncertain NOT NULL constraints, FK rebinding to `avito_profiles`, and hot-path index recreation increase integrity/performance risk.
   - Correctness becomes application-dependent instead of DB-enforced.

3. **AI profile selection authorization bypass risk via callback spoofing.**
   - Profile selection callback processing checks settings existence but not ownership binding strongly enough.
   - A malicious actor may bind to another tenant profile ID if discoverable.

4. **Follow-up rows can become permanently stuck in `processing` after failure/restart.**
   - Items are claimed and marked `processing`, but robust timeout/recovery requeue mechanics are absent.
   - This creates durable follow-up loss and pipeline inconsistency.

## High Severity Issues
1. **Migration logic can unintentionally enable AI for migrated profiles.**
   - The enablement mapping logic may force enabled state unexpectedly, violating tenant intent.

2. **Long-lived session/transaction pressure around LLM calls.**
   - Initial commit occurs before LLM call, but session lifecycle patterns still risk prolonged transactional resource usage under load.

3. **Legacy branch abstractions remain active in naming/state/UI.**
   - Runtime terms such as `current_branch_id` and branch-mode states remain in active paths.
   - This introduces architectural drift and raises maintenance/regression risk.

4. **No explicit duplicate scheduling guard in dangerous edge paths.**
   - Absent strict idempotency/uniqueness guarantees, restart/replay conditions can create duplicate pending follow-ups.

## Medium Issues
1. **N+1 query behavior in follow-up processing.**
   - Dialog state lookups can execute per-item queries in batch loops.

2. **Weak referential guarantees for active profile pointer on user context.**
   - Lack of strict FK semantics on user profile pointer increases stale-reference risk.

3. **Model policy enforcement is only partial.**
   - UI limits exposure, but broader alias map still exists and requires strict centralized enforcement.

4. **No operational downgrade path for migration.**
   - Rollback complexity remains high without explicit safe downgrade semantics.

## Low Issues
1. **Legacy compatibility artifacts increase cognitive load.**
   - Old branch-oriented handlers/keyboards/states coexist with profile-centric logic.

2. **Startup logging/debug noise in entrypoint paths.**
   - Not a blocker, but suboptimal for production observability hygiene.

## Architectural Observations
- **Positive:** `AISettings` is modeled as 1:1 with profile identity.
- **Positive:** Core AI dialog/follow-up/state concepts are largely remapped to `profile_id`.
- **Concern:** Mixed domain language (`branch` + `profile`) indicates incomplete consolidation.
- **Concern:** Remaining legacy abstractions increase risk of accidental policy bypasses and maintenance complexity.

## Performance Observations
- Expected scale scenario reviewed: **100 profiles / 1,000 active dialogs / 10,000 pending follow-ups**.
- Batch follow-up processing is bounded, which is good for scheduler stability.
- Main risks under scale:
  - N+1 state queries inside processing loops.
  - Missing/uncertain post-migration composite indexes on new profile-centric access paths.
  - Session/connection pressure from per-message transaction boundaries plus external LLM latency.
- Scheduler settings (`max_instances=1`, `coalesce=True`) are directionally correct but insufficient alone if stuck-state recovery is absent.

## Security Observations
### Critical
- **Tenant boundary risk in profile selection callback authorization.**
  - Missing strong ownership validation can allow cross-tenant profile binding.

### Medium
- **Callback parsing robustness concerns.**
  - Direct parsing patterns may produce noisy failure modes/DoS-like error amplification if malformed payloads are sent.

### Low / Acceptable
- API keys appear environment-backed rather than stored in DB entities.
- No obvious runtime raw-SQL injection surface in audited paths; migration SQL use is static.

## UX Consistency Review
- `/start` entry and primary menu flows are generally coherent.
- Profile selection and AI-disabled messaging behavior are present.
- Legacy compatibility commands reduce hard breakage for existing operators.
- Some profile AI menu paths appear placeholder-like, creating potential perception gaps.
- Mixed legacy/profile terminology may confuse users and support teams.

## Final Verdict
## **NOT SAFE**

The refactor is not yet production-safe due to unresolved migration integrity risk, tenant authorization gaps, and follow-up reliability weaknesses.

## Main blockers before production
1. **Harden migration ordering for constrained-column drops.**
   - Explicitly drop old PK/unique constraints first, recreate profile-based constraints, then drop legacy columns.
2. **Complete schema rebind hardening after remap.**
   - Enforce NOT NULL where required, restore FK guarantees, and ensure hot-path indexes for profile-centric query patterns.
3. **Enforce strict ownership checks in profile-selection callback paths.**
4. **Add crash-safe recovery for follow-ups stuck in `processing`.**
5. **Add idempotency/uniqueness protection for scheduling paths where duplicates are harmful.**
6. **Validate all fixes on PostgreSQL with realistic legacy data before rollout.**

## Audit checks run
- `rg --files`
- `rg -n "branch_id|ai_branches|AISettings|profile_id|followup|dialog|gpt|model|SKIP LOCKED|FOR UPDATE|max_instances|coalesce|callback_data|api key|OPENAI|llm" core bot alembic main.py`
- `rg -n "branch_id|ai_branch|ai_branches|followup_chains|current_branch_id" core bot alembic`
- `python - <<'PY' ... (AST import cycle scan) ... PY`
- `nl -ba alembic/versions/20260218_ai_seller_mode.py | sed -n '1,360p'`
- `nl -ba alembic/versions/20260218_profile_centric_ai.py | sed -n '1,320p'`
- `nl -ba core/scheduler.py | sed -n '280,520p'`
- `nl -ba bot/handlers/ai_mode.py | sed -n '1,220p'`

## How to Use This Document
This report is a **reference baseline** for the profile-centric refactor state at the time of audit. Use it as a production safety checklist before release sign-off. After critical/high-severity issues are fixed, this document must be updated with:
- remediations implemented,
- PostgreSQL migration validation evidence,
- post-fix risk reassessment,
- and an updated production readiness score and verdict.

Do not treat this report as permanently current; it is valid only until material architectural or migration changes are introduced.
