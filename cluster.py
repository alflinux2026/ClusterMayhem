import subprocess

USER = "alftorres"
HOST_PREFIX = "100.100.1."
SERVICE = "cluster-node"

NODES = ["200", "202", "203"]

def ssh(node, cmd):
    host = f"{HOST_PREFIX}{node}"
    full = f"ssh {USER}@{host} '{cmd}'"
    return subprocess.call(full, shell=True)

def restart(node):
    return ssh(node, f"sudo systemctl restart {SERVICE}")

def kill(node):
    return ssh(node, f"sudo pkill -9 {SERVICE}")

def start(node):
    return ssh(node, f"sudo systemctl start {SERVICE}")

def stop(node):
    return ssh(node, f"sudo systemctl stop {SERVICE}")
