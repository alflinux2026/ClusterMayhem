from datetime import datetime

def log_state(color, typ, msg):
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
    print(f"[{datetime.now():%H:%M:%S}] {c}{typ}{reset} {msg}")
