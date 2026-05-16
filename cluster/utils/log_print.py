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

    # -----------------------------------------
    # timestamp
    # -----------------------------------------

    now = datetime.now()

    if decimals == 0:
        ts = now.strftime("%H:%M:%S")
    else:
        micros = f"{now.microsecond:06d}"[:decimals]
        ts = f"{now.strftime('%H:%M:%S')}.{micros}"

    # -----------------------------------------
    # aligned tag
    # -----------------------------------------

    tag = f"[{typ}]"
    tag = f"{tag:>14}"

    # -----------------------------------------
    # print
    # -----------------------------------------

    print(f"[{ts}] {c}{tag}{reset} {msg}")
