import time
import random
import requests
import threading

from cluster.runtime.events.cluster_event import ClusterEvent


# =====================================================
# ⚙️ CONFIGURACIÓN
# =====================================================

NODES = [
    "http://100.100.1.200:7000",
    "http://100.100.1.202:7000",
    "http://100.100.1.203:7000",
]

# 📦 Número total de eventos que se van a inyectar al cluster
# Unidad: eventos (integer count)
EVENTS = 50

# ⏱️ Rango de tiempo entre eventos consecutivos
# Unidad: segundos (s)
# Ejemplo: (0.3, 1.2) = entre 300ms y 1200ms de espera entre eventos
EVENT_DELAY_RANGE = (3, 6)

# 💥 Probabilidad de lanzar un BOOT (simulación de caída o reinicio de nodo)
# Unidad: probabilidad (0.0 → 1.0)
# Ejemplo: 0.05 = 5% de probabilidad por evento
BOOT_PROBABILITY = 0.3

# ⛔ Duración del estado BOOT del nodo (simulación de downtime)
# Unidad: segundos (s)
# Ejemplo: (1.5, 4.0) = el nodo estará “caído” entre 1.5s y 4s
BOOT_DURATION_RANGE = (5, 15)

# 🌐 Timeout de las peticiones HTTP hacia el cluster
# Unidad: segundos (s)
# Ejemplo: 5 = si no responde en 5s, se considera fallo
REQUEST_TIMEOUT = 5


# =====================================================
# 🧨 BOOT CHAOS
# =====================================================

def boot_node(node, seconds):
    try:
        requests.post(
            f"{node}/boot",
            json={"seconds": seconds},
            timeout=1
        )
        print(f"[CHAOS] BOOT {node} {seconds:.2f}s")
    except Exception as e:
        print(f"[CHAOS FAIL] {node} -> {repr(e)}")


# =====================================================
# 📦 EVENT SENDING (CORRECT FORMAT)
# =====================================================

def send_event(i):
    node = random.choice(NODES)

    event = ClusterEvent(
        event_type="chaos.test",
        payload={
            "msg": f"message-{i}",
            "seq": i,
            "source": "chaos_torture"
        },
        created_at=time.time()
    )

    try:
        r = requests.post(
            f"{node}/event",
            json=event.model_dump(),
            timeout=REQUEST_TIMEOUT
        )

        print(f"[TORTURE] {i} -> {node} ({r.status_code}) {r.text}")

    except Exception as e:
        print(f"[TORTURE FAIL] {node} -> {repr(e)}")


# =====================================================
# 🔥 MAIN LOOP
# =====================================================

def chaos_loop():
    for i in range(EVENTS):

        if random.random() < BOOT_PROBABILITY:
            node = random.choice(NODES)
            threading.Thread(
                target=boot_node,
                args=(node, random.uniform(*BOOT_DURATION_RANGE)),
                daemon=True
            ).start()

        send_event(i)
        time.sleep(random.uniform(*EVENT_DELAY_RANGE))


# =====================================================
# 🚀 ENTRYPOINT
# =====================================================

def main():
    print("[MAIN] starting cluster chaos torture")
    chaos_loop()
    print("[MAIN] done")


if __name__ == "__main__":
    main()
