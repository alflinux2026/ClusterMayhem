
import requests
import sys
import time

from cluster.runtime.events.cluster_event import ClusterEvent


# =============================
# SEND EVENT
# =============================
def send_event(node_url, event):

    r = requests.post(
        f"{node_url}/event",
        json=event.model_dump(),
        timeout=3
    )

    print(f"[CLIENT] sent to {node_url}")

    try:
        print(f"[RESPONSE] {r.json()}")
    except Exception:
        print(f"[RESPONSE RAW] {r.text}")

    return r.status_code == 200


# =============================
# TORTURE TEST (PURE ROUND ROBIN)
# =============================
def torture_test(node_urls, event_type, total_messages=50):

    print("\n==============================")
    print(" MAYHEM CLUSTER TORTURE TEST ")
    print("==============================\n")

    node_count = len(node_urls)

    global_cycle = 0  # 🔥 IMPORTANT: GLOBAL ACROSS ALL MESSAGES

    for i in range(total_messages):

        event = ClusterEvent(
            event_type=event_type,
            payload={
                "msg": f"message-{i}",
                "seq": i,
                "ts": time.time()
            },
            created_at=time.time()
        )

        print(f"\n########################################")
        print(f"[MESSAGE {i+1}/{total_messages}] event_id={event.event_id}")

        sent = False

        # try each message until success OR full cycle exhausted
        for _ in range(node_count):

            node = node_urls[global_cycle % node_count]
            global_cycle += 1  # 🔥 ALWAYS ADVANCE

            print(f"\n[TRY] node={node} msg={event.payload['msg']}")

            try:
                ok = send_event(node, event)

                if ok:
                    print(f"[CLIENT] DELIVERED event_id={event.event_id}")
                    sent = True
                    break

            except requests.RequestException as e:
                print(f"[ERROR] {node} -> {e}")

        if not sent:
            print("[CLUSTER] full cycle failed, retrying same event...")
            time.sleep(1)

            # retry same event again with continued rotation
            while not sent:

                node = node_urls[global_cycle % node_count]
                global_cycle += 1

                print(f"\n[RETRY LOOP] node={node} msg={event.payload['msg']}")

                try:
                    ok = send_event(node, event)

                    if ok:
                        print(f"[CLIENT] DELIVERED event_id={event.event_id}")
                        sent = True

                except requests.RequestException as e:
                    print(f"[ERROR] {node} -> {e}")

                time.sleep(0.2)

        time.sleep(0.5)

    print("\n================================")
    print(" TEST COMPLETED ")
    print("================================")


# =============================
# ENTRYPOINT
# =============================
if __name__ == "__main__":

    if len(sys.argv) < 3:
        print("Usage: python event_cli.py <node1,node2,...> <event_type>")
        sys.exit(1)

    node_urls = sys.argv[1].split(",")
    event_type = sys.argv[2]

    torture_test(node_urls, event_type, total_messages=50)

