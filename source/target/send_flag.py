#!/usr/bin/env python3
# PATCH_VERSION: v3

import socket
import time
from challenge_logging import log_exception, log_step

SCRIPT_NAME = "send_flag.py"
FLAG = "AUTH::success|sid=0x1337|token=QWN0dWFsX0ZsYWc6Q1RGe3NuMWZmM2RfZnIwbV90aDNfdzFyM30="
PASSWORD = "Password: ArmyCyberRocks"
BONUS = "CTF{N1c3_C@tcH}"
BROADCAST_IP = "255.255.255.255"
DEST_PORT = 8333
SOURCE_PORT = 8333


def send_message(sock, label, payload, delay_seconds):
    log_step(SCRIPT_NAME, f"Sending {label} to {BROADCAST_IP}:{DEST_PORT}")
    sock.sendto(payload.encode(), (BROADCAST_IP, DEST_PORT))
    print(f"Sent {label}: {payload}", flush=True)
    log_step(SCRIPT_NAME, f"Sent {label}; sleeping {delay_seconds} seconds")
    time.sleep(delay_seconds)


def main():
    log_step(SCRIPT_NAME, f"Starting UDP broadcaster on source port {SOURCE_PORT}")
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    sock.bind(("", SOURCE_PORT))
    log_step(SCRIPT_NAME, "Socket created, broadcast enabled, and source port bound")

    cycle = 0
    while True:
        cycle += 1
        log_step(SCRIPT_NAME, f"Broadcast cycle {cycle} started")
        schedule = [
            ("bonus flag", BONUS, 6),
            ("bonus flag", BONUS, 6),
            ("bonus flag", BONUS, 6),
            ("password", PASSWORD, 6),
            ("bonus flag", BONUS, 6),
            ("bonus flag", BONUS, 6),
            ("bonus flag", BONUS, 6),
            ("password", PASSWORD, 6),
            ("bonus flag", BONUS, 6),
            ("bonus flag", BONUS, 3),
            ("actual flag", FLAG, 3),
            ("bonus flag", BONUS, 6),
            ("password", PASSWORD, 6),
        ]
        for label, payload, delay in schedule:
            send_message(sock, label, payload, delay)
        log_step(SCRIPT_NAME, f"Broadcast cycle {cycle} complete")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        log_exception(SCRIPT_NAME, "UDP broadcaster failed", exc)
        raise
