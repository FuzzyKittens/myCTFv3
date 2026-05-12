#!/usr/bin/env python3
# PATCH_VERSION: v3

import os
import pwd
import pty
import select
import socket
import subprocess
import time
import datetime
from pathlib import Path
from challenge_logging import get_log_file, log_command, log_exception, log_step

SCRIPT_NAME = "bind_shell.py"
HOST = "0.0.0.0"
PORT = 8000
PASSWORD = "ArmyCyberRocks"
USERNAME = "ctfuser"
ADDUSER = "CTF{w3_hav3_1n1t1@l_@cc3$$}"
LOG_DIR = "/var/log/ctfuser"


def run_command(cmd, *, input_bytes=None, check=True, stdout=None, stderr=None):
    log_command(SCRIPT_NAME, cmd)
    subprocess.run(cmd, input=input_bytes, check=check, stdout=stdout, stderr=stderr)
    log_step(SCRIPT_NAME, f"Command completed: {' '.join(cmd)}")


def create_ctf_user(username, password):
    log_step(SCRIPT_NAME, f"Ensuring playable shell user exists: {username}")
    try:
        pwd.getpwnam(username)
        log_step(SCRIPT_NAME, f"User already exists: {username}")
    except KeyError:
        log_step(SCRIPT_NAME, f"Creating user: {username}")
        run_command(["useradd", "-m", "-s", "/bin/bash", "-G", "users", username])
        log_step(SCRIPT_NAME, f"Setting password for {username}; password not logged")
        run_command(["chpasswd"], input_bytes=f"{username}:{password}".encode())
        run_command(["deluser", username, "sudo"], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        log_step(SCRIPT_NAME, f"User created with no sudo and added to users group: {username}")

    run_command(["mkdir", "-p", LOG_DIR])
    run_command(["chown", f"{username}:{username}", LOG_DIR])
    run_command(["chmod", "755", LOG_DIR])

    do_not_read_path = Path(f"/home/{username}/DoNotReadMe.txt")
    log_step(SCRIPT_NAME, f"Writing bonus clue file: {do_not_read_path}")
    do_not_read_path.write_text("CTF{R1ck_R011}\n", encoding="utf-8")
    run_command(["chown", f"{username}:{username}", str(do_not_read_path)])
    run_command(["chmod", "644", str(do_not_read_path)])

    history_path = Path(f"/home/{username}/.bash_history")
    bonus_flag = "CTF{c4n_y0u_r34d_h1st0ry?}"
    fake_commands = [
        "ls -la",
        "cd /var/log",
        "cat /etc/passwd",
        "nmap 192.168.1.0/24",
        "echo 'debugging tcp connections...'",
        f"cat ~/notes.txt # BONUS_FLAG: {bonus_flag}",
        "python3 scanner.py",
        "exit",
    ]
    log_step(SCRIPT_NAME, f"Writing fake bash history: {history_path}")
    history_path.write_text("\n".join(fake_commands) + "\n", encoding="utf-8")
    run_command(["chown", f"{username}:{username}", str(history_path)])
    run_command(["chmod", "600", str(history_path)])
    log_step(SCRIPT_NAME, "Playable shell user setup complete")


def create_user_if_missing(username):
    log_step(SCRIPT_NAME, f"Ensuring additional user exists: {username}")
    try:
        pwd.getpwnam(username)
        log_step(SCRIPT_NAME, f"Additional user already exists: {username}")
    except KeyError:
        run_command(["useradd", "-m", "-s", "/bin/bash", username])
        log_step(SCRIPT_NAME, f"Additional user created: {username}")


def generate_session_log():
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    session_path = Path(LOG_DIR) / f"session_{timestamp}.log"
    log_step(SCRIPT_NAME, f"Generated per-session transcript path: {session_path}")
    return str(session_path)


def drop_to_user(username):
    log_step(SCRIPT_NAME, f"Dropping child shell privileges to user: {username}")
    user_info = pwd.getpwnam(username)
    os.setgid(user_info.pw_gid)
    os.setuid(user_info.pw_uid)
    os.chdir(user_info.pw_dir)
    os.environ["HOME"] = user_info.pw_dir
    os.environ["USER"] = username
    os.environ["LOGNAME"] = username


def main():
    log_step(SCRIPT_NAME, f"Starting bind shell; unified log file is {get_log_file()}")
    create_user_if_missing(ADDUSER)
    create_ctf_user(USERNAME, PASSWORD)

    while True:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind((HOST, PORT))
            s.listen(1)
            print(f"[+] Listening on {HOST}:{PORT}", flush=True)
            log_step(SCRIPT_NAME, f"Bind shell listening on {HOST}:{PORT}")

            try:
                conn, addr = s.accept()
                log_step(SCRIPT_NAME, f"Connection accepted from {addr}")
                conn.sendall(b"Password: ")
                password_input = conn.recv(1024).strip().decode(errors="replace")

                if password_input != PASSWORD:
                    conn.sendall(b"Access Denied.\n")
                    log_step(SCRIPT_NAME, f"Access denied for {addr}", "WARNING")
                    conn.close()
                    continue

                conn.sendall(b"Access Granted. Starting shell...\n")
                log_step(SCRIPT_NAME, f"Access granted for {addr}")

                session_log = generate_session_log()
                os.environ["TERM"] = "xterm"
                pid, fd = pty.fork()
                if pid == 0:
                    drop_to_user(USERNAME)
                    os.execv("/bin/bash", ["/bin/bash", "-i"])
                else:
                    log_step(SCRIPT_NAME, f"Started PTY child pid={pid}; transcript={session_log}")
                    with open(session_log, "wb") as logfile:
                        try:
                            while True:
                                rlist, _, _ = select.select([conn, fd], [], [])
                                if conn in rlist:
                                    data = conn.recv(1024)
                                    if not data:
                                        break
                                    os.write(fd, data)
                                if fd in rlist:
                                    try:
                                        output = os.read(fd, 1024)
                                        if not output:
                                            break
                                        logfile.write(output)
                                        logfile.flush()
                                        conn.sendall(output)
                                    except OSError:
                                        break
                        except Exception as exc:
                            log_exception(SCRIPT_NAME, f"Session relay error for {addr}", exc)
                        finally:
                            log_step(SCRIPT_NAME, f"Connection closed: {addr}")
                            conn.close()
            except Exception as exc:
                log_exception(SCRIPT_NAME, "Connection handling failed", exc)
                time.sleep(3)


if __name__ == "__main__":
    main()
