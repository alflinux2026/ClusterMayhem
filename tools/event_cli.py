import requests
import uuid
import time
import sys


def send_event(node_url, event_type, payload):

    event = {
        "event_id": str(uuid.uuid4()),
        "type": event_type,
        "payload": payload,
        "created_at": time.time()
    }

    r = requests.post(f"{node_url}/event", json=event, timeout=3)

    print(f"[CLIENT] sent to {node_url}")
    print(f"[RESPONSE] {r.json()}")


if __name__ == "__main__":

    if len(sys.argv) < 3:
        print("Usage: python event_cli.py <node_url> <type>")
        print("Example: python event_cli.py http://100.100.1.203:7000 test")
        sys.exit(1)

    node_url = sys.argv[1]
    event_type = sys.argv[2]

    payload = {
        "msg": "hello cluster",
        "seq": int(time.time())
    }

    send_event(node_url, event_type, payload)
