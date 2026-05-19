import time
import requests
from chaos import ChaosEngine

DISPATCHER = "http://100.100.1.200:7000/event"

TOTAL = 100
RATE = 0.05

sent = []
errors = []

def send(seq):
    payload = {
        "event_type": "test",
        "payload": {
            "msg": f"message-{seq}",
            "seq": seq,
            "ts": time.time()
        }
    }

    try:
        r = requests.post(DISPATCHER, json=payload, timeout=2)
        if r.status_code == 200:
            print(f"[SEND] {seq}")
        else:
            print(f"[FAIL] {seq} code={r.status_code}")
            errors.append(seq)
    except Exception as e:
        print(f"[ERR] {seq} {e}")
        errors.append(seq)

def analyze():
    expected = set(range(TOTAL))
    received = set(sent)

    missing = sorted(list(expected - received))

    print("\n===== RESULT =====")
    print(f"sent: {len(sent)}")
    print(f"errors: {len(errors)}")
    print(f"missing seq: {missing}")

def main():

    chaos = ChaosEngine()

    print("[TORTURE] starting chaos")
    chaos.start()

    print("[TORTURE] sending events")

    for i in range(TOTAL):
        send(i)
        sent.append(i)
        time.sleep(RATE)

        # burst opcional controlado
        if i % 20 == 0:
            time.sleep(0.5)

    print("[TORTURE] stopping chaos")
    chaos.stop()

    analyze()

if __name__ == "__main__":
    main()
