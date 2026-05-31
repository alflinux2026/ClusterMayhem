# Execution backlog

## Goal
Turn the redesign plan into a concrete implementation backlog with dependency order, so we can refactor without breaking the runtime in the middle.

## Phase 0 - Stabilize liveness
### Task 0.1 - Extract heartbeat worker
- Create a dedicated periodic worker for heartbeat send + receive.
- Keep it independent from dispatch, reconcile, and execution loops.
- Acceptance: a busy node still emits and processes heartbeats on schedule.

### Task 0.2 - Centralize liveness cache
- Store last-seen and liveness metadata in one place.
- Make leader/isalive consume cached data only.
- Acceptance: leader selection no longer creates heartbeat traffic internally.

### Task 0.3 - Stop heartbeat coupling in node loop
- Remove heartbeat from the main worker sequence.
- Keep node tick, dispatch, and reconciliation separated.
- Acceptance: worker load does not suppress heartbeats.

## Phase 1 - Fix event flow bugs
### Task 1.1 - Fix dispatcher attempt handling
- Remove the reset-to-zero bug.
- Preserve monotonic attempt semantics.
- Acceptance: retry keys remain stable and idempotency can work.

### Task 1.2 - Normalize context contract
- Declare `node_id`, `priority`, and `node` explicitly.
- Remove implicit runtime assumptions.
- Acceptance: imports and runtime access become predictable.

### Task 1.3 - Review alive timeout policy
- Define one timeout policy for all nodes.
- Use the same policy in leader, dispatch, and cleanup.
- Acceptance: no contradictory alive decisions.

## Phase 2 - Separate state semantics
### Task 2.1 - Redefine node states
- Add `DRAIN_TO_STANDBY` or equivalent.
- Make leaving ACTIVE explicit.
- Acceptance: shutdown/drain behavior is represented cleanly.

### Task 2.2 - Redefine event states if needed
- Evaluate whether `RECEIVED` and `DISPATCHED` are necessary.
- Keep only the states that add real semantic value.
- Acceptance: event lifecycle becomes easier to reason about.

### Task 2.3 - Split reconciliation by phase
- Separate recovery logic by event phase.
- Avoid one monolithic recoverer.
- Acceptance: each failure mode has a specific recovery path.

## Phase 3 - Metadata and versioning
### Task 3.1 - Cache version metadata on append
- Compute hash or `last_event` metadata when the log changes.
- Do not recalculate in the heartbeat path.
- Acceptance: version info is cheap to publish.

### Task 3.2 - Publish metadata in heartbeat
- Add version fields to the heartbeat payload.
- Use them for remote validation only.
- Acceptance: peers can compare versions without reading the file.

### Task 3.3 - Add drain checkpoint behavior
- When leaving ACTIVE, freeze and publish version metadata.
- Use the drain transition as the checkpoint point.
- Acceptance: expensive work happens only when the node is leaving ACTIVE.

## Phase 4 - Structural cleanup
### Task 4.1 - Thin `api_app.py`
- Extract endpoint logic into smaller services.
- Keep HTTP wiring minimal.
- Acceptance: API file becomes a router, not a control tower.

### Task 4.2 - Review leader responsibility
- Decide if leader remains authoritative or only coordinative.
- Align dispatch and liveness with that decision.
- Acceptance: election model and runtime behavior stop fighting each other.

### Task 4.3 - Reconcile cluster store usage
- Keep `cluster_state` only for cached topology/liveness.
- Avoid using it as a general-purpose runtime DB.
- Acceptance: responsibilities stay bounded.

## Proposed commit order
1. Heartbeat extraction and liveness cache.
2. Main loop decoupling from heartbeat.
3. Dispatcher `attempt` fix and context cleanup.
4. Alive timeout unification.
5. Node state redesign.
6. Event/reconciliation phase cleanup.
7. Version metadata caching and heartbeat payload update.
8. API and structural cleanup.

## Dependencies
- Heartbeat extraction must happen before leader/isalive simplification.
- Dispatcher `attempt` fix should land before idempotency work.
- Node drain state should be defined before version checkpointing.
- Version metadata caching should be in place before heartbeat payload changes.
- API cleanup should wait until core semantics are stable.

## Definition of done
- Heartbeat is independent and reliable.
- Busy nodes no longer look dead.
- Leader election is stable under load.
- Retry and idempotency semantics are coherent.
- Node lifecycle includes an explicit drain path.
- Version metadata is cheap and consistent.
- API and runtime responsibilities are visibly separated.
