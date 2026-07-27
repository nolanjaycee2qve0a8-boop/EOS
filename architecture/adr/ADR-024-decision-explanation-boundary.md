# ADR-024 — Decision Explanation Boundary

## Status

Accepted

## Context

`ExecutionAudit` provides immutable provenance for a completed EMS lifecycle.
Future consumers need a stable contract for observing which source context and
decision result belong to that audited lifecycle without depending on runtime
execution or a specific EMS algorithm.

If explanation re-evaluates policy, it creates a new decision rather than
explaining the completed one. If it copies the context or result, exact
provenance is lost.

## Decision

Introduce the frozen, slotted `DecisionExplanation` model.

`DecisionExplanation.create(audit)` validates an existing `ExecutionAudit` and
retains exact references to:

- the audit;
- its execution trace;
- the source decision context as `source_context`; and
- the source `DecisionResult`.

Validation uses object identity for the audit-to-trace lifecycle relationship,
the source decision artifacts, dispatch continuity, and journal
`EventRecord` continuity.

Explanation construction only observes existing immutable artifacts. It does
not call runtime, policy evaluation, dispatchers, `CommandExecutor`,
`RuntimeReplay`, `ExecutionAudit.create()`, or `EventJournal.append()`.

## Why Explanation Is Separate from Execution

Execution owns policy evaluation, dispatch, journaling, and progression.
Explanation owns no transition or external effect. Separating them keeps
inspection deterministic and prevents explanation consumers from influencing
the completed decision.

## Why Explanation Cannot Recompute Decisions

Policy re-evaluation may depend on a different invocation or cause behavior
outside the explanation boundary. A recomputed value would not be the original
audited result. The contract therefore exposes the existing result and context
by identity.

## Why Identity Preservation Is Required

Identity proves that the explanation refers to the exact audited context,
decision, commands, events, journals, and records. Value-equal replacements
could conceal reconstruction and weaken deterministic provenance.

## Consequences

- Audited decisions have a stable immutable explanation contract.
- Decision and context identities remain intact.
- Explanation creation has no execution or journal side effects.
- No policy or runtime state is retained.
- Intelligent diagnosis, recommendations, optimization analysis, pricing,
  forecasting, cloud analytics, and UI concerns remain intentionally excluded.

## Rejected Alternatives

- Re-evaluate policy: rejected because it creates a new decision.
- Invoke runtime replay: rejected because explanation directly observes audit.
- Copy decision artifacts: rejected because copies lose exact provenance.
- Persist explanations: rejected because persistence is outside this boundary.
