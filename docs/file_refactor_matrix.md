# File-by-file refactor matrix

| File | Priority | Impact | Risk | Task |
| --- | --- | --- | --- | --- |
| `runtime/node_worker.py` | P0 | Very high | High | Extract heartbeat into its own worker and stop coupling it to dispatch/reconcile. |
| `node/node_runtime.py` | P0 | High | Medium | Keep only node state transitions and heartbeat publication helpers. |
| `runtime/cluster_store.py` | P0 | High | Medium | Centralize cached liveness and last_seen state. |
| `runtime/dispatcher.py` | P1 | Very high | High | Fix `attempt`, preserve retry semantics, and align with new liveness source. |
| `runtime/context.py` | P1 | High | Low | Declare explicit runtime fields. |
| `runtime/api_app.py` | P1 | High | Medium | Thin out endpoints and move business logic into services. |
| `runtime/state.py` | P2 | High | Medium | Add drain-oriented node state(s). |
| `runtime/events/event_state.py` | P2 | High | Medium | Expand event lifecycle only if it adds real value. |
| `runtime/reconciler/reconciler_loop.py` | P2 | High | Medium | Split recovery by phase and reduce monolithic recovery logic. |
| `runtime/event_log.py` | P3 | High | Medium | Cache version metadata and support drain checkpoint behavior. |
| `runtime/log_replication.py` | P3 | Medium | Medium | Align with cached metadata and avoid redundant reads. |
| `runtime/leader.py` | P0 | Very high | High | Make leader selection consume cached liveness only. |
| `runtime/event_router.py` | P1 | High | Medium | Ensure routing follows the new state and liveness model. |
| `runtime/bootstrap.py` | P3 | Medium | Low | Keep bootstrap stable while the runtime refactor lands. |
| `runtime/state_machine.py` | P2 | Medium | Medium | Make event-state transitions coherent with the new model. |
| `runtime/ingest.py` | P2 | High | Medium | Align ingest with the new event lifecycle. |
| `runtime/node_boot.py` | P3 | Medium | Low | Keep as pure wiring; avoid adding logic. |
| `utils/log_print.py` | P3 | Low | Low | Leave unchanged unless logging needs new tags. |

## Priority meaning
- P0: Must land first because current behavior is unstable.
- P1: Important after liveness is stable.
- P2: Semantic cleanup and lifecycle remodeling.
- P3: Structural polish and secondary alignment.

## Execution order
1. `runtime/leader.py`
2. `runtime/node_worker.py`
3. `runtime/cluster_store.py`
4. `runtime/dispatcher.py`
5. `runtime/context.py`
6. `node/node_runtime.py`
7. `runtime/api_app.py`
8. `runtime/state.py`
9. `runtime/events/event_state.py`
10. `runtime/reconciler/reconciler_loop.py`
11. `runtime/state_machine.py`
12. `runtime/ingest.py`
13. `runtime/event_log.py`
14. `runtime/log_replication.py`
15. `runtime/event_router.py`
16. `runtime/bootstrap.py`
17. `runtime/node_boot.py`
18. `utils/log_print.py`

## Notes
- The order intentionally starts with liveness and leader logic because everything else depends on stable node presence.
- The dispatcher fix should not be merged before the heartbeat/liveness split, otherwise you will keep masking the same bug with better retries.
- Event-state and node-state redesigns should be done after the runtime is no longer oscillating.
