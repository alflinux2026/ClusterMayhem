def dispatch_created_event(event):

    completed = get_completed_event_ids()

    if event.event_id in completed:
        return

    alive = {
        node_id: data
        for node_id, data in cluster_state.items()
        if (time.time() - data["last_seen"]) < 3.0
    }

    if not alive:
        return

    target = max(
        alive.items(),
        key=lambda x: (x[1]["priority"], x[0])
    )[0]

    event.target_node = target
    event.add_hop(f"dispatcher->worker:{target}")

    event.mark_status("executing")

    append_event(event)

    forward_event(target, event)
