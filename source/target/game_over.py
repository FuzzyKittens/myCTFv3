#!/usr/bin/env python3
# PATCH_VERSION: v3

import datetime
import grp
import os
import pwd
import shutil
import stat
import subprocess
from pathlib import Path
from challenge_logging import get_log_file, log_command, log_exception, log_step

SCRIPT_NAME = "game_over.py"
CTF_USERS = [
    "enemy",
    "TheGeneral",
    "CTF{w3_hav3_1n1t1@l_@cc3$$}",
    "ctfuser",
]
LOG_SRC = "/var/log/ctfuser"
ARCHIVE_DIR = "/srv/myCTF"
PROCESS_TARGETS = [
    "send_flag.py",
    "send_flag.py",
    "bind_shell.py",
    "bind_shell.py",
]


def run_command(cmd, *, check=True):
    log_command(SCRIPT_NAME, cmd)
    subprocess.run(cmd, check=check)
    log_step(SCRIPT_NAME, f"Command completed: {' '.join(str(x) for x in cmd)}")


def archive_logs():
    log_step(SCRIPT_NAME, f"Archiving logs from {LOG_SRC}; unified log is {get_log_file()}")
    if not os.path.exists(LOG_SRC):
        log_step(SCRIPT_NAME, f"Log directory does not exist: {LOG_SRC}", "WARNING")
        return

    timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    target_dir = Path(ARCHIVE_DIR) / timestamp
    target_dir.mkdir(parents=True, exist_ok=True)
    copied = 0
    for file in os.listdir(LOG_SRC):
        full_path = Path(LOG_SRC) / file
        if full_path.is_file():
            shutil.copy2(full_path, target_dir)
            copied += 1
            log_step(SCRIPT_NAME, f"Archived log file: {full_path} -> {target_dir}")
    log_step(SCRIPT_NAME, f"Logs archived to {target_dir}; copied={copied}")


def kill_processes():
    log_step(SCRIPT_NAME, "Terminating CTF-related background processes")
    try:
        result = subprocess.run(["ps", "aux"], capture_output=True, text=True, check=False)
        lines = result.stdout.splitlines()
        killed_pids = set()
        for line in lines:
            for name in PROCESS_TARGETS:
                if name in line and "python" in line:
                    parts = line.split()
                    if len(parts) < 2:
                        continue
                    pid = parts[1]
                    if pid not in killed_pids:
                        log_step(SCRIPT_NAME, f"Killing {name} PID {pid}")
                        subprocess.run(["kill", "-9", pid], check=False)
                        killed_pids.add(pid)
    except Exception as exc:
        log_exception(SCRIPT_NAME, "Failed to terminate CTF processes", exc)


def remove_users():
    log_step(SCRIPT_NAME, "Removing CTF users")
    for user in CTF_USERS:
        try:
            pwd.getpwnam(user)
            log_step(SCRIPT_NAME, f"Removing user: {user}")
            subprocess.run(["userdel", "-r", user], check=True)
            log_step(SCRIPT_NAME, f"User removed: {user}")
        except KeyError:
            log_step(SCRIPT_NAME, f"User does not exist, skipping: {user}")
        except subprocess.CalledProcessError as exc:
            log_exception(SCRIPT_NAME, f"Failed to remove user {user}", exc)


def reset_find_permissions():
    find_path = "/usr/bin/find"
    log_step(SCRIPT_NAME, f"Resetting SUID bit on {find_path}")
    try:
        mode = os.stat(find_path).st_mode
        new_mode = mode & ~stat.S_ISUID
        os.chmod(find_path, new_mode)
        log_step(SCRIPT_NAME, f"SUID bit removed from {find_path}; mode {oct(mode)} -> {oct(os.stat(find_path).st_mode)}")
    except Exception as exc:
        log_exception(SCRIPT_NAME, f"Failed to reset permissions on {find_path}", exc)


def cleanup_environment():
    log_step(SCRIPT_NAME, "Cleaning up temporary challenge files")
    tmp_files = ["/tmp/flag.txt", "/tmp/flag.zip", "/tmp/nuclear_with_comment.png", "/tmp/combined_nuclear.png", "/tmp/nuclear_codes.txt"]
    for item in tmp_files:
        path = Path(item)
        try:
            if path.exists():
                path.unlink()
                log_step(SCRIPT_NAME, f"Removed temp file: {path}")
            else:
                log_step(SCRIPT_NAME, f"Temp file not present, skipping: {path}")
        except Exception as exc:
            log_exception(SCRIPT_NAME, f"Failed to remove temp file {path}", exc)


def main():
    log_step(SCRIPT_NAME, "Game Over cleanup started")
    archive_logs()
    reset_find_permissions()
    kill_processes()
    remove_users()
    cleanup_environment()
    log_step(SCRIPT_NAME, "CTF environment cleanup complete")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        log_exception(SCRIPT_NAME, "Game Over cleanup failed", exc)
        raise
