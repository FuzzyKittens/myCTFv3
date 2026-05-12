#!/usr/bin/env python3
# PATCH_VERSION: v3

import os
import pathlib
import pwd
import stat
import subprocess
from challenge_logging import log_command, log_exception, log_step

SCRIPT_NAME = "make_privesc.py"


def run_command(cmd, *, input_bytes=None, check=True):
    log_command(SCRIPT_NAME, cmd)
    subprocess.run(cmd, input=input_bytes, check=check)
    log_step(SCRIPT_NAME, f"Command completed: {' '.join(str(x) for x in cmd)}")


def make_suid(path):
    log_step(SCRIPT_NAME, f"Attempting to set SUID bit on {path}")
    try:
        mode = os.stat(path).st_mode
        log_step(SCRIPT_NAME, f"Current mode for {path}: {oct(mode)}")
        new_mode = mode | stat.S_ISUID
        os.chmod(path, new_mode)
        log_step(SCRIPT_NAME, f"SUID bit set on {path}; new mode: {oct(os.stat(path).st_mode)}")
    except Exception as exc:
        log_exception(SCRIPT_NAME, f"Failed to set SUID on {path}", exc)
        raise


def user_exists(username):
    log_step(SCRIPT_NAME, f"Checking whether user exists: {username}")
    try:
        pwd.getpwnam(username)
        log_step(SCRIPT_NAME, f"User exists: {username}")
        return True
    except KeyError:
        log_step(SCRIPT_NAME, f"User does not exist: {username}")
        return False


def create_user(username):
    log_step(SCRIPT_NAME, f"Starting user creation step for {username}")
    if user_exists(username):
        log_step(SCRIPT_NAME, f"Skipping creation; user already exists: {username}")
        return
    run_command(["useradd", "-m", username])
    log_step(SCRIPT_NAME, f"User created: {username}")


def lock_down_home(username):
    log_step(SCRIPT_NAME, f"Locking down home directory for {username}")
    user_info = pwd.getpwnam(username)
    home_dir = user_info.pw_dir
    os.chown(home_dir, user_info.pw_uid, user_info.pw_gid)
    os.chmod(home_dir, 0o750)
    log_step(SCRIPT_NAME, f"Permissions for {home_dir} set to 750")


def create_encrypted_file(username, password, message):
    log_step(SCRIPT_NAME, f"Creating encrypted nuclear codes file for {username}")
    user_info = pwd.getpwnam(username)
    home_dir = pathlib.Path(user_info.pw_dir)
    docs_dir = home_dir / "Documents"
    zip_file = docs_dir / "nuclear_codes.zip"
    plaintext_path = pathlib.Path("/tmp/nuclear_codes.txt")

    log_step(SCRIPT_NAME, f"Ensuring documents directory exists: {docs_dir}")
    docs_dir.mkdir(exist_ok=True)

    log_step(SCRIPT_NAME, f"Writing temporary plaintext nuclear codes file: {plaintext_path}")
    plaintext_path.write_text(message, encoding="utf-8")

    log_step(SCRIPT_NAME, f"Creating encrypted ZIP file: {zip_file}; password value intentionally not logged")
    run_command(["zip", "-j", "-P", password, str(zip_file), str(plaintext_path)])

    os.chown(zip_file, user_info.pw_uid, user_info.pw_gid)
    log_step(SCRIPT_NAME, f"Ownership set on ZIP file: {zip_file}")

    plaintext_path.unlink(missing_ok=True)
    log_step(SCRIPT_NAME, f"Temporary plaintext file removed: {plaintext_path}")
    log_step(SCRIPT_NAME, f"Encrypted ZIP written to {zip_file}")


def main():
    target = "/usr/bin/find"
    username = "TheGeneral"
    log_step(SCRIPT_NAME, "Privilege escalation challenge setup started")
    make_suid(target)
    create_user(username)
    lock_down_home(username)
    nuclear_codes = """
TOP SECRET: Nuclear Launch Codes

Alpha Target: 38402-BRAVO-1228
Beta Target: 44120-ECHO-1991
Gamma Target: 99123-TANGO-4421

FLAG: CTF{Pr1v_3sc@l@t1oN}
"""
    create_encrypted_file(username, "tuckerbear2", nuclear_codes)
    log_step(SCRIPT_NAME, "Privilege escalation challenge setup complete")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        log_exception(SCRIPT_NAME, "Privilege escalation setup failed", exc)
        raise
