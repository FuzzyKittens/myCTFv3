#!/usr/bin/env python3
# PATCH_VERSION: v3
"""
Run:
    CTF_BIND_HOST=0.0.0.0 CTF_PORT=65000 CTF_ADMIN_TOKEN='change-me' CTF_LOGFILE=/var/log/ctfuser/bitstorm_ctf.log python3 challenge_listener.py

Endpoints:
    GET  /health
    GET  /api/quiz
    POST /api/submit-quiz     {"answers": [{"id": 1, "answer": "C"}, ...]}
    POST /api/submit-flag     {"flag": "CTF{...}"}
    POST /api/admin/restart   Authorization: Bearer <token>
                              {"action": "restart_bind"}
                              {"action": "restart_send"}
                              {"action": "restart_all", "resume_to_id": 3}
"""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

HOST = os.environ.get("CTF_BIND_HOST", "0.0.0.0")
PORT = int(os.environ.get("CTF_PORT", "65000"))
LOGFILE = Path(os.environ.get("CTF_LOGFILE", "/var/log/ctfuser/bitstorm_ctf.log"))
STORY_FILE = Path(os.environ.get("CTF_STORY_FILE", "challenges.json"))
ADMIN_TOKEN = os.environ.get("CTF_ADMIN_TOKEN", "")
PYTHON = os.environ.get("CTF_PYTHON", sys.executable or "python3")
MAX_REQUEST_BYTES = 32 * 1024


def load_story_data() -> dict[str, Any]:
    with STORY_FILE.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, list):
        return {"challenges": data, "bonus_flags": [], "initial_quiz": {"questions": []}}
    data.setdefault("challenges", [])
    data.setdefault("bonus_flags", [])
    data.setdefault("initial_quiz", {"questions": []})
    return data


def safe_script_name(script: str | None) -> str | None:
    """Allow only simple local .py filenames, not paths or shell fragments."""
    if not script:
        return None
    if os.path.basename(script) != script:
        return None
    if not script.endswith(".py"):
        return None
    if any(ch in script for ch in ["/", "\\", "\x00"]):
        return None
    return script


def get_challenges() -> list[dict[str, Any]]:
    return load_story_data().get("challenges", [])


def get_initial_quiz() -> dict[str, Any]:
    quiz = load_story_data().get("initial_quiz", {})
    if not isinstance(quiz, dict):
        return {"questions": []}
    return quiz


def public_quiz_payload() -> dict[str, Any]:
    """Return quiz questions while stripping server-side answer keys."""
    quiz = get_initial_quiz()
    public_questions: list[dict[str, Any]] = []
    for index, q in enumerate(quiz.get("questions", []), start=1):
        public_questions.append(
            {
                "id": int(q.get("id", index)),
                "narrative": str(q.get("narrative", "")),
                "question": str(q.get("question", "")),
                "hint": str(q.get("hint", "")),
                "options": list(q.get("options", [])),
            }
        )
    return {"ok": True, "questions": public_questions, "count": len(public_questions)}


def validate_initial_quiz(answers: Any, source_ip: str = "unknown") -> dict[str, Any]:
    """Validate all quiz answers server-side and return the first flag only on success."""
    quiz = get_initial_quiz()
    questions = quiz.get("questions", [])
    completion_flag = str(quiz.get("completion_flag", "CTF{aced_that_test}"))

    if not isinstance(answers, list):
        return {"ok": False, "message": "answers must be a list", "display_text": "❌ Invalid quiz submission."}

    expected = {int(q.get("id", i)): str(q.get("answer", "")).strip().upper() for i, q in enumerate(questions, start=1)}
    submitted: dict[int, str] = {}
    for item in answers:
        if not isinstance(item, dict):
            continue
        try:
            qid = int(item.get("id"))
        except (TypeError, ValueError):
            continue
        submitted[qid] = str(item.get("answer", "")).strip().upper()

    missing = [qid for qid in expected if qid not in submitted]
    incorrect = [qid for qid, answer in expected.items() if submitted.get(qid) != answer]

    if missing or incorrect:
        log_event(f"Initial quiz failed from {source_ip}. missing={missing} incorrect={incorrect} submitted_question_ids={sorted(submitted.keys())}", "WARNING")
        return {
            "ok": False,
            "message": "One or more answers were incorrect.",
            "display_text": "❌ Incorrect! Try again from the beginning.",
            "reset": True,
        }

    log_event(f"Initial quiz completed successfully from {source_ip}")
    return {
        "ok": True,
        "message": "Quiz complete",
        "flag": completion_flag,
        "display_text": f"🎉 Quiz Complete! Your first flag is {completion_flag}",
    }


def get_all_scripts() -> set[str]:
    scripts: set[str] = set()
    for entry in get_challenges():
        script = safe_script_name(entry.get("python_script_to_run"))
        if script:
            scripts.add(script)
    scripts.update({"bind_shell.py", "send_flag.py", "game_over.py"})
    return scripts


def load_flag_actions() -> dict[str, dict[str, Any]]:
    data = load_story_data()
    challenges = data.get("challenges", [])
    bonuses = data.get("bonus_flags", [])

    actions: dict[str, dict[str, Any]] = {}

    for entry in challenges:
        flag = entry.get("flag")
        if not flag:
            continue
        actions[flag] = {
            "script": safe_script_name(entry.get("python_script_to_run")),
            "story": entry.get("story", ""),
            "level": entry.get("level", ""),
            "points": int(entry.get("points", 0)),
            "client_action": entry.get("client_action"),
        }

    for bonus in bonuses:
        flag = bonus.get("flag")
        if not flag:
            continue
        actions[flag] = {
            "script": None,
            "story": bonus.get("message", ""),
            "level": "Bonus",
            "points": int(bonus.get("points", 0)),
            "client_action": bonus.get("client_action"),
        }

    return actions


def log_event(msg: str, level: str = "INFO") -> None:
    """Write listener and challenge orchestration events into the unified CTF log."""
    import datetime

    timestamp = datetime.datetime.now(datetime.timezone.utc).astimezone().isoformat(timespec="seconds")
    line = f"[{timestamp}] [{level.upper()}] [challenge_listener] [pid={os.getpid()}] {msg}"
    try:
        LOGFILE.parent.mkdir(parents=True, exist_ok=True)
        with LOGFILE.open("a", encoding="utf-8") as log:
            log.write(f"{line}\n")
    except PermissionError:
        pass
    print(line, flush=True)


def launch_python_script(script: str) -> bool:
    script = safe_script_name(script) or ""
    if script not in get_all_scripts():
        log_event(f"⚠️ Refused non-allowlisted script: {script}")
        return False

    script_path = Path.cwd() / script
    if not script_path.is_file():
        log_event(f"⚠️ Script not found: {script}")
        return False

    env = os.environ.copy()
    env["CTF_LOG_FILE"] = str(LOGFILE)
    env["CTF_LOGFILE"] = str(LOGFILE)
    env["CTF_SCRIPT_NAME"] = script

    LOGFILE.parent.mkdir(parents=True, exist_ok=True)
    log_handle = LOGFILE.open("a", encoding="utf-8", buffering=1)
    try:
        subprocess.Popen(
            [PYTHON, str(script_path)],
            cwd=str(Path.cwd()),
            stdout=log_handle,
            stderr=log_handle,
            env=env,
            start_new_session=True,
        )
    finally:
        log_handle.close()
    log_event(f"→ Triggered script: {script} with unified log {LOGFILE}")
    return True


def kill_processes_matching_script(script: str) -> None:
    """Avoid shell=True/pkill -f. Enumerate processes with ps and signal matching Python script commands."""
    script = safe_script_name(script) or ""
    if not script:
        return

    current_pid = os.getpid()
    try:
        ps = subprocess.run(["ps", "-eo", "pid=,args="], check=False, text=True, capture_output=True)
    except Exception as exc:
        log_event(f"[!] Unable to inspect process list for {script}: {exc}")
        return

    for line in ps.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            pid_str, args = line.split(None, 1)
            pid = int(pid_str)
        except ValueError:
            continue

        if pid == current_pid:
            continue
        if "python" in args and script in args:
            try:
                os.kill(pid, signal.SIGTERM)
                log_event(f"⛔ Stopped PID {pid}: {script}")
            except ProcessLookupError:
                pass
            except PermissionError:
                log_event(f"[!] No permission to stop PID {pid}: {script}")


def restart_bind_shell() -> dict[str, Any]:
    log_event("🛠️ Admin requested bind_shell restart")
    kill_processes_matching_script("bind_shell.py")
    started = launch_python_script("bind_shell.py")
    return {"ok": started, "message": "bind_shell.py restarted" if started else "bind_shell.py not started"}


def restart_send_flag() -> dict[str, Any]:
    log_event("🛠️ Admin requested send_flag restart")
    kill_processes_matching_script("send_flag.py")
    started = launch_python_script("send_flag.py")
    return {"ok": started, "message": "send_flag.py restarted" if started else "send_flag.py not started"}


def kill_all_scripts_and_cleanup(resume_to_id: int | None = None) -> dict[str, Any]:
    log_event("🛠️ Admin issued restart_all")
    stopped: list[str] = []
    started: list[str] = []

    for script in sorted(get_all_scripts()):
        if script == "game_over.py":
            continue
        kill_processes_matching_script(script)
        stopped.append(script)

    if "game_over.py" in get_all_scripts():
        if launch_python_script("game_over.py"):
            started.append("game_over.py")

    if resume_to_id is not None:
        for entry in get_challenges():
            if int(entry.get("id", 0)) <= resume_to_id:
                script = safe_script_name(entry.get("python_script_to_run"))
                if script and script != "game_over.py" and launch_python_script(script):
                    started.append(script)

    return {"ok": True, "message": "restart_all complete", "stopped": stopped, "started": started, "resume_to_id": resume_to_id}


def build_display_text(result: dict[str, Any]) -> str:
    if not result.get("ok"):
        return "❌ Invalid flag."

    lines = [
        "✅ Correct flag!",
        "",
        f"🎯 Level: {result.get('level', '')} | 🏅 Points Earned: {result.get('points', 0)}",
        "",
        "📖 STORY:",
        result.get("story", ""),
    ]
    return "\n".join(lines).strip()


def handle_flag(flag: str) -> dict[str, Any]:
    actions = load_flag_actions()
    action = actions.get(flag)

    if not action:
        log_event(f"Invalid flag: {flag}")
        return {"ok": False, "message": "Invalid flag", "display_text": "❌ Invalid flag."}

    script = action.get("script")
    launched = False
    if script:
        launched = launch_python_script(script)

    result = {
        "ok": True,
        "message": "Correct flag",
        "level": action.get("level", ""),
        "points": action.get("points", 0),
        "story": action.get("story", ""),
        "script_launched": launched,
        "client_action": action.get("client_action"),
    }
    result["display_text"] = build_display_text(result)
    log_event(f"Correct flag received: {flag}")
    return result


class CTFRequestHandler(BaseHTTPRequestHandler):
    server_version = "BitstormCTF/3.0"

    def log_message(self, fmt: str, *args: Any) -> None:
        log_event(f"{self.client_address[0]} - {fmt % args}")

    def send_json(self, status: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def read_json_body(self) -> dict[str, Any] | None:
        length_header = self.headers.get("Content-Length", "0")
        try:
            length = int(length_header)
        except ValueError:
            self.send_json(HTTPStatus.BAD_REQUEST, {"ok": False, "message": "Invalid Content-Length"})
            return None

        if length <= 0 or length > MAX_REQUEST_BYTES:
            self.send_json(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, {"ok": False, "message": "Invalid request size"})
            return None

        raw = self.rfile.read(length)
        try:
            data = json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError:
            self.send_json(HTTPStatus.BAD_REQUEST, {"ok": False, "message": "Invalid JSON body"})
            return None

        if not isinstance(data, dict):
            self.send_json(HTTPStatus.BAD_REQUEST, {"ok": False, "message": "JSON body must be an object"})
            return None
        return data

    def require_admin_token(self) -> bool:
        if not ADMIN_TOKEN:
            self.send_json(HTTPStatus.SERVICE_UNAVAILABLE, {"ok": False, "message": "Admin API disabled. Set CTF_ADMIN_TOKEN to enable it."})
            return False

        auth = self.headers.get("Authorization", "")
        expected = f"Bearer {ADMIN_TOKEN}"
        if auth != expected:
            self.send_json(HTTPStatus.UNAUTHORIZED, {"ok": False, "message": "Unauthorized"})
            return False
        return True

    def do_GET(self) -> None:
        if self.path == "/health":
            self.send_json(HTTPStatus.OK, {"ok": True, "service": "Bitstorm CTF", "port": PORT})
            return
        if self.path == "/api/quiz":
            self.send_json(HTTPStatus.OK, public_quiz_payload())
            return
        self.send_json(HTTPStatus.NOT_FOUND, {"ok": False, "message": "Not found"})

    def do_POST(self) -> None:
        if self.path == "/api/submit-quiz":
            data = self.read_json_body()
            if data is None:
                return
            self.send_json(HTTPStatus.OK, validate_initial_quiz(data.get("answers"), self.client_address[0]))
            return

        if self.path == "/api/submit-flag":
            data = self.read_json_body()
            if data is None:
                return
            flag = str(data.get("flag", "")).strip()
            if not flag:
                self.send_json(HTTPStatus.BAD_REQUEST, {"ok": False, "message": "Missing flag"})
                return
            self.send_json(HTTPStatus.OK, handle_flag(flag))
            return

        if self.path == "/api/admin/restart":
            if not self.require_admin_token():
                return
            data = self.read_json_body()
            if data is None:
                return

            action = str(data.get("action", "")).strip().lower()
            if action == "restart_bind":
                self.send_json(HTTPStatus.OK, restart_bind_shell())
                return
            if action == "restart_send":
                self.send_json(HTTPStatus.OK, restart_send_flag())
                return
            if action == "restart_all":
                resume_to_id = data.get("resume_to_id")
                if resume_to_id is not None:
                    try:
                        resume_to_id = int(resume_to_id)
                    except (TypeError, ValueError):
                        self.send_json(HTTPStatus.BAD_REQUEST, {"ok": False, "message": "resume_to_id must be an integer"})
                        return
                self.send_json(HTTPStatus.OK, kill_all_scripts_and_cleanup(resume_to_id=resume_to_id))
                return

            self.send_json(HTTPStatus.BAD_REQUEST, {"ok": False, "message": f"Unknown admin action: {action}"})
            return

        self.send_json(HTTPStatus.NOT_FOUND, {"ok": False, "message": "Not found"})


def main() -> None:
    # Validate JSON at startup so config mistakes fail early.
    load_story_data()
    log_event(f"CTF HTTP API listening on {HOST}:{PORT}")
    if not ADMIN_TOKEN:
        log_event("⚠️ Admin API is disabled until CTF_ADMIN_TOKEN is set")

    httpd = ThreadingHTTPServer((HOST, PORT), CTFRequestHandler)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        log_event("Server interrupted, shutting down")
    finally:
        httpd.server_close()


if __name__ == "__main__":
    main()
