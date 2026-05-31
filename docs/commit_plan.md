# Commit plan

## Commit 1 - Heartbeat isolation
**Scope**
- Extract heartbeat into a dedicated worker/thread.
- Separate heartbeat send and heartbeat receive concerns.
- Keep the worker loop from coupling heartbeat to dispatch/reconcile.

**Files**
- `runtime/node_worker.py`
- `node/node_runtime.py`
- `runtime/cluster_store.py`
- `runtime/leader.py`

**Message**
- `refactor(runtime): isolate heartbeat from worker loop`

**Goal**
Busy nodes must keep heartbeating even when dispatch or execution is heavy.

---

## Commit 2 - Liveness cache cleanup
**Scope**
- Make leader selection read cached liveness only.
- Ensure `isalive` logic does not trigger send/receive work.
- Normalize `last_seen` and cached node state.

**Files**
- `runtime/cluster_store.py`
- `runtime/leader.py`
- `runtime/api_app.py`
- `runtime/node_worker.py`

**Message**
- `refactor(runtime): centralize cached liveness checks`

**Goal**
No function should fabricate heartbeat traffic while checking liveness.

---

## Commit 3 - Dispatcher retry fix
**Scope**
- Fix `attempt` handling.
- Preserve retry monotonicity.
- Align execution key semantics with retries.

**Files**
- `runtime/dispatcher.py`
- `runtime/worker/event_worker.py`
- `runtime/state_machine.py`

**Message**
- `fix(dispatcher): preserve attempt semantics`

**Goal**
Retries must be consistent and idempotency must have a stable basis.

---

## Commit 4 - Runtime context contract
**Scope**
- Declare all runtime fields explicitly.
- Remove implicit assumptions from runtime modules.

**Files**
- `runtime/context.py`
- `runtime/node_boot.py`
- `runtime/api_app.py`
- `runtime/dispatcher.py`

**Message**
- `refactor(runtime): define explicit context contract`

**Goal**
Runtime access should be predictable and self-documenting.

---

## Commit 5 - Node lifecycle redesign
**Scope**
- Add drain-style state transition.
- Make leaving ACTIVE explicit.
- Prepare metadata checkpoint on exit from ACTIVE.

**Files**
- `runtime/state.py`
- `node/node_runtime.py`
- `runtime/node_worker.py`

**Message**
- `refactor(state): add drain transition for node lifecycle`

**Goal**
Node lifecycle must support an orderly handoff, not just on/off behavior.

---

## Commit 6 - Event lifecycle cleanup
**Scope**
- Rework event states only if the new semantics are justified.
- Split reconciliation by phase.
- Align ingest and state machine behavior.

**Files**
- `runtime/events/event_state.py`
- `runtime/reconciler/reconciler_loop.py`
- `runtime/state_machine.py`
- `runtime/ingest.py`

**Message**
- `refactor(events): normalize lifecycle phases and recovery`

**Goal**
Event recovery must match the actual phase where the failure occurs.

---

## Commit 7 - Version metadata cache
**Scope**
- Cache hash or last-event metadata on append.
- Publish metadata via heartbeat.
- Avoid recalculating expensive metadata in the heartbeat path.

**Files**
- `runtime/event_log.py`
- `runtime/log_replication.py`
- `runtime/node_worker.py`
- `node/node_runtime.py`

**Message**
- `refactor(logs): cache version metadata for heartbeat`

**Goal**
Version metadata should be cheap to publish and useful for validation.

---

## Commit 8 - API thinning
**Scope**
- Remove non-routing logic from `api_app.py`.
- Extract endpoint helpers and service calls.
- Keep HTTP layer thin.

**Files**
- `runtime/api_app.py`
- `runtime/event_router.py`
- `runtime/ingest.py`

**Message**
- `refactor(api): thin HTTP runtime layer`

**Goal**
The API should route, not orchestrate everything.

---

## Commit 9 - Bootstrap and wiring cleanup
**Scope**
- Keep bootstrap as wiring only.
- Keep `node_boot.py` as a clean entrypoint.
- Avoid reintroducing logic into startup.

**Files**
- `runtime/bootstrap.py`
- `runtime/node_boot.py`
- `runtime/api_app.py`

**Message**
- `chore(runtime): keep startup wiring minimal`

**Goal**
Startup should remain boring, predictable, and hard to break.

## Recommended merge rule
- One commit per concern.
- No mixed semantic + structural changes in the same commit if avoidable.
- Do not touch event semantics before heartbeat/liveness is stable.
- Do not touch API cleanup before the core runtime stops oscillating.
