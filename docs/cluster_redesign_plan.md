# Cluster redesign plan

## Objective
Unwind the changes discovered this morning and convert them into a staged implementation plan that is safe to commit to the repository.

## Why this plan exists
The runtime is currently mixing liveness, dispatch, execution, and reconciliation in ways that create false death detection, leader oscillation, and unclear state semantics.

The main design shifts are:
- heartbeat must become an independent periodic interrupt.
- heartbeat must handle both send and receive.
- leader/isalive must only read cached liveness state.
- event states should be made more explicit.
- node state should gain an orderly drain path.

## Immediate problems
- Node 202 oscillates between STANDBY and ACTIVE because busy nodes stop sending heartbeat in time.
- The worker loop mixes tick, heartbeat, dispatch, replication, and reconciliation.
- Dispatch has an `attempt` bug.
- The current state model is too binary for what the system now needs.

## Implementation order
### P0 - Stop the bleeding
1. Split heartbeat into a dedicated worker/thread.
2. Make heartbeat responsible for both sending and receiving.
3. Remove any need for leader/isalive to generate heartbeats internally.
4. Fix the `attempt` handling bug in dispatcher.
5. Stabilize `context.py` with explicit fields.

### P1 - Normalize semantics
6. Refactor event states to a clearer phase model.
7. Split reconciliation by phase.
8. Unify alive checks behind a single helper.
9. Reduce `api_app.py` responsibility by extracting services/handlers.

### P2 - Remodel node lifecycle
10. Add `DRAIN_TO_STANDBY` as an explicit transitional state.
11. Compute expensive log metadata only when leaving ACTIVE.
12. Cache version metadata so heartbeat can publish it cheaply.

### P3 - Structural cleanup
13. Rebalance responsibilities between node runtime, worker, dispatcher, API, and event log.
14. Revisit whether leader is still the source of truth or only a coordinator.
15. Reconcile the journal-based truth model with the current election model.

## Suggested file changes
### `runtime/node_worker.py`
- Extract heartbeat into its own loop.
- Keep dispatch/reconcile separate from liveness.

### `node/node_runtime.py`
- Keep node state transitions only.
- Add support for drain-style transitions if needed.

### `runtime/api_app.py`
- Keep HTTP wiring thin.
- Move business logic out of endpoints.

### `runtime/dispatcher.py`
- Fix `attempt`.
- Avoid hidden state resets.
- Make target selection depend on a single liveness source.

### `runtime/cluster_store.py`
- Keep cached liveness state.
- Avoid using it as a dumping ground for unrelated metadata.

### `runtime/context.py`
- Declare all runtime fields explicitly.

### `runtime/state.py`
- Extend node lifecycle states.

### `runtime/events/event_state.py`
- Expand event phases if the redesign is approved.

### `runtime/reconciler/reconciler_loop.py`
- Split recovery paths by phase.

### `runtime/event_log.py`
- Cache last event/version metadata.
- Support the new drain/checkpoint flow.

## Commit strategy
- Commit 1: heartbeat extraction and liveness isolation.
- Commit 2: dispatcher `attempt` fix.
- Commit 3: context and state cleanup.
- Commit 4: event-state normalization.
- Commit 5: node lifecycle redesign.
- Commit 6: metadata/version cache support.
- Commit 7: reconciliation and API refactor.

## Acceptance criteria
- No leader oscillation under normal worker load.
- Busy nodes still heartbeat on time.
- Leader and alive checks only consume cached state.
- `attempt` is monotonic and coherent.
- New state transitions are explicit and testable.
- Version metadata is cheap to publish.

## Open questions
- Should heartbeat store only liveness or also version metadata?
- Is `last_event` enough, or do we keep a hash cache too?
- Do we want one unified state machine for node and event lifecycle, or keep them separated?
- Should leader remain authoritative, or only coordinative?

## Next session starting point
1. Freeze the current behavior map.
2. Extract heartbeat worker.
3. Fix `attempt`.
4. Redefine node lifecycle.
5. Reconcile event phase model.
