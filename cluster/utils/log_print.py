from datetime import datetime

from datetime import datetime

def log_state(color, typ, msg, decimals=0):
    colors = {
        "red": "\033[91m",
        "green": "\033[92m",
        "yellow": "\033[93m",
        "blue": "\033[94m",
        "magenta": "\033[95m",
        "cyan": "\033[96m",
        "white": "\033[97m",
        "reset": "\033[0m",
    }

    c = colors.get(color.lower(), colors["white"])
    reset = colors["reset"]

    decimals = max(0, min(6, int(decimals)))

    if decimals == 0:
        ts = datetime.now().strftime("%H:%M:%S")
    else:
        ts = datetime.now().strftime("%H:%M:%S.%f")[:9 + decimals]

    print(f"[{ts}] {c}{typ}{reset} {msg}")
