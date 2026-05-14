import requests


def send_heartbeat(peer_host, peer_port, payload, timeout=1.0):

    url = f"http://{peer_host}:{peer_port}/heartbeat"

    try:
        r = requests.post(
            url,
            json=payload,
            timeout=timeout,
        )

        return r.json()

    except Exception as e:

        print(f"[CLIENT ERROR] {url} -> {e}")

        return None

def broadcast_heartbeat(peers, payload):

    for peer in peers:

        send_heartbeat(
            peer["host"],
            peer["port"],
            payload,
        )
