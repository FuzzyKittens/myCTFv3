#!/usr/bin/env python3
# PATCH_VERSION: v3

import os
import pwd
import subprocess
from challenge_logging import log_command, log_exception, log_step

SCRIPT_NAME = "setup_environment.py"
USERNAME = "ctfuser"
ENEMYNAME = "CTF{w3_hav3_1n1t1@l_@cc3$$}"
PASSWORD = "ArmyCyberRocks"
LOG_DIR = "/var/log/ctfuser"


def user_exists(username):
    log_step(SCRIPT_NAME, f"Checking whether user exists: {username}")
    try:
        pwd.getpwnam(username)
        log_step(SCRIPT_NAME, f"User exists: {username}")
        return True
    except KeyError:
        log_step(SCRIPT_NAME, f"User does not exist: {username}")
        return False


def run_command(cmd, *, input_bytes=None, check=True, redact=False):
    display_cmd = ["<redacted>" if redact else str(part) for part in cmd]
    log_command(SCRIPT_NAME, display_cmd)
    subprocess.run(cmd, input=input_bytes, check=check)
    log_step(SCRIPT_NAME, f"Command completed: {' '.join(display_cmd)}")


def create_user(username):
    log_step(SCRIPT_NAME, f"Starting user creation step for {username}")
    if user_exists(username):
        log_step(SCRIPT_NAME, f"Skipping creation; user already exists: {username}")
        return

    run_command(["sudo", "useradd", "--badname", "-m", "-s", "/bin/bash", username])
    log_step(SCRIPT_NAME, f"Setting password for {username}; password value intentionally not logged")
    run_command(["sudo", "chpasswd"], input_bytes=f"{username}:{PASSWORD}".encode(), redact=True)
    log_step(SCRIPT_NAME, f"User created and password set: {username}")


def setup_environment():
    log_step(SCRIPT_NAME, "Environment setup started")
    create_user(USERNAME)
    create_user(ENEMYNAME)

    log_step(SCRIPT_NAME, "Adding CTF users to users group")
    run_command(["sudo", "usermod", "-G", "users", USERNAME])
    run_command(["sudo", "usermod", "-G", "users", ENEMYNAME])

    log_step(SCRIPT_NAME, "Removing sudo group membership if present")
    run_command(["sudo", "deluser", USERNAME, "sudo"], check=False)
    run_command(["sudo", "deluser", ENEMYNAME, "sudo"], check=False)

    log_step(SCRIPT_NAME, f"Ensuring log directory exists: {LOG_DIR}")
    os.makedirs(LOG_DIR, exist_ok=True)
    run_command(["sudo", "chown", f"{USERNAME}:{USERNAME}", LOG_DIR])
    run_command(["sudo", "chmod", "755", LOG_DIR])

    log_step(SCRIPT_NAME, "Environment setup complete")
    print("[✅] User setup complete. You can test it with:")
    print(f"    su - {USERNAME}")


if __name__ == "__main__":
    try:
        setup_environment()
    except Exception as exc:
        log_exception(SCRIPT_NAME, "Environment setup failed", exc)
        raise
