#!/usr/bin/env python3
# PATCH_VERSION: v3
"""
Shared logging helper for Bitstorm CTF challenge scripts.

The challenge listener defines the canonical log file path and passes it to each
challenge script through the CTF_LOG_FILE environment variable. Scripts can also
be run manually; in that case this helper falls back to the same default path.
"""

from __future__ import annotations

import datetime
import fcntl
import os
import sys
import traceback
from pathlib import Path
from typing import Iterable, Optional

DEFAULT_LOG_FILE = "/var/log/ctfuser/bitstorm_ctf.log"


def get_log_file() -> Path:
    return Path(os.environ.get("CTF_LOG_FILE") or os.environ.get("CTF_LOGFILE") or DEFAULT_LOG_FILE)


def _write_line(line: str) -> None:
    log_file = get_log_file()
    try:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        with log_file.open("a", encoding="utf-8") as f:
            try:
                fcntl.flock(f.fileno(), fcntl.LOCK_EX)
            except OSError:
                pass
            f.write(line + "\n")
            f.flush()
            try:
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)
            except OSError:
                pass
    except Exception as exc:
        print(f"[logging-failed] {exc}: {line}", file=sys.stderr, flush=True)


def log_step(script: str, message: str, level: str = "INFO") -> None:
    timestamp = datetime.datetime.now(datetime.timezone.utc).astimezone().isoformat(timespec="seconds")
    pid = os.getpid()
    _write_line(f"[{timestamp}] [{level.upper()}] [{script}] [pid={pid}] {message}")


def log_exception(script: str, message: str, exc: BaseException) -> None:
    log_step(script, f"{message}: {exc}", "ERROR")
    for line in traceback.format_exception(type(exc), exc, exc.__traceback__):
        for subline in line.rstrip().splitlines():
            log_step(script, subline, "ERROR")


def log_command(script: str, cmd: Iterable[str], note: Optional[str] = None) -> None:
    joined = " ".join(str(part) for part in cmd)
    if note:
        log_step(script, f"{note}: {joined}")
    else:
        log_step(script, f"Running command: {joined}")
