#!/usr/bin/env python3
# PATCH_VERSION: v4_dynamic_process_targets_from_challenges_json

import datetime
import json
import os
import pwd
import shutil
import stat
import subprocess
from pathlib import Path
from challenge_logging import get_log_file, log_command, log_exception, log_step

SCRIPT_NAME = Path(__file__).name

CTF_USERS = [
    "enemy",
    "TheGeneral",
    "CTF{w3_hav3_1n1t1@l_@cc3$$}",
    "ctfuser",
]

LOG_SRC = Path(os.environ.get("CTF_LOG_DIR", "/var/log/ctfuser"))
ARCHIVE_DIR = Path(os.environ.get("CTF_ARCHIVE_DIR", "/srv/myCTF"))
STORY_FILE = Path(os.environ.get("CTF_STORY_FILE", "challenges.json"))


def run_command(cmd, *, check=True):
    log_command(SCRIPT_NAME, cmd)
    subprocess.run(cmd, check=check)
    log_step(SCRIPT_NAME, f"Command completed: {' '.join(str(x) for x in cmd)}")


def archive_logs():
    log_step(SCRIPT_NAME, f"Archiving logs from {LOG_SRC}; unified log is {get_log_file()}")
    if not LOG_SRC.exists():
        log_step(SCRIPT_NAME, f"Log directory does not exist: {LOG_SRC}", "WARNING")
        return

    timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    target_dir = ARCHIVE_DIR / timestamp
    target_dir.mkdir(parents=True, exist_ok=True)

    copied = 0
    for file_path in LOG_SRC.iterdir():
        if file_path.is_file():
            shutil.copy2(file_path, target_dir)
            copied += 1
            log_step(SCRIPT_NAME, f"Archived log file: {file_path} -> {target_dir}")
    log_step(SCRIPT_NAME, f"Logs archived to {target_dir}; copied={copied}")


def _safe_script_name(value):
    """Return only simple local script basenames from challenges.json."""
    if not isinstance(value, str):
        return None
    candidate = value.strip()
    if not candidate or candidate != Path(candidate).name:
        return None
    if not candidate.endswith(".py"):
        return None
    return candidate


def load_process_targets_from_story_file():
    """
    Read all challenge scripts from challenges.json and use those as process targets.

    game_over excludes itself so cleanup does not kill the currently running cleanup process.
    This means adding/removing challenge scripts in challenges.json automatically updates cleanup.
    """
    log_step(SCRIPT_NAME, f"Loading process targets from story file: {STORY_FILE}")

    try:
        with STORY_FILE.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        log_step(SCRIPT_NAME, f"Story file not found; no dynamic process targets loaded: {STORY_FILE}", "ERROR")
        return []
    except json.JSONDecodeError as exc:
        log_exception(SCRIPT_NAME, f"Story file is invalid JSON: {STORY_FILE}", exc)
        return []
    except Exception as exc:
        log_exception(SCRIPT_NAME, f"Failed to read story file: {STORY_FILE}", exc)
        return []

    challenges = data if isinstance(data, list) else data.get("challenges", [])
    targets = []
    seen = set()

    for entry in challenges:
        script = _safe_script_name(entry.get("python_script_to_run") if isinstance(entry, dict) else None)
        if not script:
            continue
        if script == SCRIPT_NAME:
            log_step(SCRIPT_NAME, f"Skipping current cleanup script in process targets: {script}")
            continue
        if script not in seen:
            targets.append(script)
            seen.add(script)

    log_step(SCRIPT_NAME, f"Loaded process targets from challenges.json: {targets if targets else 'none'}")
    return targets


def kill_processes():
    targets = load_process_targets_from_story_file()
    if not targets:
        log_step(SCRIPT_NAME, "No process targets found in challenges.json; skipping process termination", "WARNING")
        return

    log_step(SCRIPT_NAME, f"Terminating CTF-related background processes from challenges.json: {targets}")
    killed_pids = set()

    try:
        result = subprocess.run(["ps", "aux"], capture_output=True, text=True, check=False)
        lines = result.stdout.splitlines()

        for line in lines:
            for name in targets:
                if name in line and "python" in line:
                    parts = line.split()
                    if len(parts) < 2:
                        continue
                    pid = parts[1]
                    if pid == str(os.getpid()):
                        log_step(SCRIPT_NAME, f"Skipping own PID {pid}")
                        continue
                    if pid in killed_pids:
                        log_step(SCRIPT_NAME, f"Skipping duplicate process match for PID {pid} ({name})")
                        continue

                    log_step(SCRIPT_NAME, f"Killing {name} PID {pid}")
                    subprocess.run(["kill", "-9", pid], check=False)
                    killed_pids.add(pid)
                    break

        log_step(SCRIPT_NAME, f"Process termination complete; killed_pids={sorted(killed_pids)}")
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
    tmp_files = [
        "/tmp/flag.txt",
        "/tmp/flag.zip",
        "/tmp/nuclear_with_comment.png",
        "/tmp/combined_nuclear.png",
        "/tmp/nuclear_codes.txt",
    ]
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
