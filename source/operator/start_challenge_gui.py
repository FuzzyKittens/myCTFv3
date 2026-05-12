#!/usr/bin/env python3
# PATCH_VERSION: v2_quiz_api_server_side_answers
import tkinter as tk
from tkinter import messagebox, scrolledtext
import json
import random
import subprocess
import urllib.error
import urllib.request
import webbrowser

# ============================== CONFIG ==============================
SERVER_HOST = '192.168.1.165'
SERVER_PORT = 65000
SERVER_SCHEME = 'http'
API_TIMEOUT_SECONDS = 5
TOTAL_FLAGS = 6
# ====================================================================

TOOL_COMMANDS = {
    "Wireshark": {
        "cmd": "wireshark",
        "desc": "Wireshark is a network protocol analyzer that lets you capture and interactively browse traffic."
    },
    "Netcat": {
        "cmd": "nc",
        "desc": "Netcat is a powerful networking utility for reading/writing data over TCP or UDP."
    },
    "CyberChef": {
        "cmd": "https://gchq.github.io/CyberChef/",
        "desc": "CyberChef is a browser-based tool for encoding, decoding, and analyzing data."
    },
    "Nmap": {
        "cmd": "nmap",
        "desc": "Nmap is a security scanner used to discover hosts and services on a computer network."
    },
    "Burp Suite": {
        "cmd": "burpsuite",
        "desc": "Burp Suite is an integrated platform for testing web application security."
    }
}

unlocked_flags = set()


class CTFApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Cyber CTF: Bitstorm")
        self.geometry("800x600")
        self.configure(bg="#1e1e2f")
        self.current_q = 0
        self.questions = []
        self.quiz_answers = []
        self.flag_response_cache = {}
        self.total_score = 0

        self.matrix_canvas = tk.Canvas(self, height=200, bg="black", highlightthickness=0)
        self.matrix_canvas.pack(side="bottom", fill="x", expand=True)
        self.matrix = MatrixEffect(self.matrix_canvas)
        self.matrix.draw()

        self.load_quiz_from_server()
        self.init_quiz_frame()

    def api_url(self, path):
        return f"{SERVER_SCHEME}://{SERVER_HOST}:{SERVER_PORT}{path}"

    def api_get(self, path):
        request = urllib.request.Request(
            self.api_url(path),
            headers={"Accept": "application/json"},
            method="GET",
        )
        try:
            with urllib.request.urlopen(request, timeout=API_TIMEOUT_SECONDS) as response:
                raw = response.read().decode("utf-8", errors="replace")
                return json.loads(raw)
        except urllib.error.HTTPError as e:
            try:
                raw = e.read().decode("utf-8", errors="replace")
                return json.loads(raw)
            except Exception:
                return {"ok": False, "display_text": f"[!] Server error: HTTP {e.code}"}
        except urllib.error.URLError as e:
            return {"ok": False, "display_text": f"[!] Connection error: {e.reason}"}
        except TimeoutError:
            return {"ok": False, "display_text": "[!] Connection timed out."}
        except json.JSONDecodeError:
            return {"ok": False, "display_text": "[!] Server returned invalid JSON."}
        except Exception as e:
            return {"ok": False, "display_text": f"[!] Connection error: {e}"}

    def api_post(self, path, payload):
        body = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            self.api_url(path),
            data=body,
            headers={"Content-Type": "application/json", "Accept": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=API_TIMEOUT_SECONDS) as response:
                raw = response.read().decode("utf-8", errors="replace")
                return json.loads(raw)
        except urllib.error.HTTPError as e:
            try:
                raw = e.read().decode("utf-8", errors="replace")
                return json.loads(raw)
            except Exception:
                return {"ok": False, "display_text": f"[!] Server error: HTTP {e.code}"}
        except urllib.error.URLError as e:
            return {"ok": False, "display_text": f"[!] Connection error: {e.reason}"}
        except TimeoutError:
            return {"ok": False, "display_text": "[!] Connection timed out."}
        except json.JSONDecodeError:
            return {"ok": False, "display_text": "[!] Server returned invalid JSON."}
        except Exception as e:
            return {"ok": False, "display_text": f"[!] Connection error: {e}"}

    def load_quiz_from_server(self):
        response = self.api_get("/api/quiz")
        if not response.get("ok"):
            messagebox.showerror("Quiz Load Error", response.get("display_text") or response.get("message") or "Could not load quiz from server.")
            self.questions = []
            return
        self.questions = response.get("questions", [])

    def init_quiz_frame(self):
        self.quiz_frame = tk.Frame(self, bg="#1e1e2f")
        self.quiz_frame.pack(fill='both', expand=True)
        self.show_question()

    def show_question(self):
        for widget in self.quiz_frame.winfo_children():
            widget.destroy()

        if not self.questions:
            tk.Label(
                self.quiz_frame,
                text="Could not load challenge questions from the server.",
                font=("Courier New", 12, "bold"),
                fg="#ff5555",
                bg="#1e1e2f",
            ).pack(pady=20)
            tk.Button(self.quiz_frame, text="Retry", command=self.retry_load_quiz, bg="#00ff88", fg="#1e1e2f").pack(pady=10)
            return

        if self.current_q >= len(self.questions):
            self.submit_quiz_answers()
            return

        q = self.questions[self.current_q]
        narrative_text = tk.Text(self.quiz_frame, wrap=tk.WORD, height=8, font=("Arial", 11), bg="black", fg="white")
        narrative_text.insert(tk.END, q.get("narrative", ""))
        narrative_text.config(state=tk.DISABLED)
        narrative_text.pack(pady=10, padx=10, fill='x')

        for tool, info in TOOL_COMMANDS.items():
            start = "1.0"
            while True:
                start = narrative_text.search(tool, start, tk.END)
                if not start:
                    break
                end = f"{start}+{len(tool)}c"
                narrative_text.tag_add(tool, start, end)
                narrative_text.tag_config(tool, foreground="#00ff88", underline=True)
                narrative_text.tag_bind(tool, "<Button-1>", lambda e, t=tool: self.launch_tool(t))
                narrative_text.tag_bind(tool, "<Enter>", lambda e, t=tool: self.show_tooltip(e, t))
                narrative_text.tag_bind(tool, "<Leave>", lambda e: self.hide_tooltip())
                start = end

        self.tooltip = None

        tk.Label(
            self.quiz_frame,
            text=q.get("question", ""),
            font=("Courier New", 12, "bold"),
            fg="#00ff88",
            bg="#1e1e2f",
        ).pack(pady=(10, 5))

        answer_var = tk.StringVar()
        for opt in q.get("options", []):
            value = opt[0] if opt else ""
            tk.Radiobutton(
                self.quiz_frame,
                text=opt,
                variable=answer_var,
                value=value,
                font=("Courier New", 11),
                fg="#f0f0f0",
                bg="#1e1e2f",
                selectcolor="#004422",
                activeforeground="#00ff88",
                highlightbackground="#1e1e2f",
                activebackground="#1e1e2f",
            ).pack(anchor='w', padx=30)

        def record_answer_and_continue():
            selected = answer_var.get().strip().upper()
            if not selected:
                messagebox.showwarning("Choose an Answer", "Please select an answer before continuing.")
                return
            self.quiz_answers.append({"id": q.get("id"), "answer": selected})
            self.current_q += 1
            self.show_question()

        tk.Button(
            self.quiz_frame,
            text="💡 Show Hint",
            font=("Courier New", 10),
            bg="#1e1e2f",
            fg="#00ff88",
            command=lambda: messagebox.showinfo("Hint", q.get("hint", "")),
        ).pack(pady=(5, 0))
        tk.Button(self.quiz_frame, text="Submit", command=record_answer_and_continue, bg="#00ff88", fg="#1e1e2f", font=("Arial", 12)).pack(pady=10)

    def retry_load_quiz(self):
        self.current_q = 0
        self.quiz_answers = []
        self.load_quiz_from_server()
        self.show_question()

    def submit_quiz_answers(self):
        response = self.api_post("/api/submit-quiz", {"answers": self.quiz_answers})
        if not response.get("ok"):
            messagebox.showerror("Incorrect", response.get("display_text") or response.get("message") or "Incorrect! Try again from the beginning.")
            self.current_q = 0
            self.quiz_answers = []
            self.show_question()
            return

        first_flag = response.get("flag", "")
        self.show_flag_screen(first_flag=first_flag, intro_text=response.get("display_text"))

    def launch_tool(self, tool_name):
        cmd = TOOL_COMMANDS.get(tool_name, {}).get("cmd")
        if not cmd:
            return
        try:
            if cmd.startswith("http"):
                webbrowser.open(cmd)
            else:
                subprocess.Popen(cmd.split())
        except Exception as e:
            messagebox.showerror("Error", f"Failed to launch {tool_name}: {e}")

    def show_tooltip(self, event, tool_name):
        if self.tooltip:
            self.tooltip.destroy()
        desc = TOOL_COMMANDS.get(tool_name, {}).get("desc", "")
        self.tooltip = tk.Toplevel(self)
        self.tooltip.overrideredirect(True)
        self.tooltip.geometry(f"+{event.x_root + 10}+{event.y_root + 10}")
        label = tk.Label(self.tooltip, text=desc, bg="#222", fg="white", font=("Arial", 9), relief="solid", borderwidth=1)
        label.pack()

    def hide_tooltip(self):
        if self.tooltip:
            self.tooltip.destroy()
            self.tooltip = None

    def show_flag_screen(self, first_flag=None, intro_text=None):
        self.quiz_frame.destroy()
        self.flag_frame = tk.Frame(self, bg="#1e1e2f")
        self.flag_frame.pack(fill='both', expand=True)

        intro = intro_text or "🎉 Quiz Complete! Enter the first flag to continue."
        if first_flag and first_flag not in intro:
            intro = f"{intro}\n\nYour first flag is {first_flag}"

        self.intro_label = tk.Label(
            self.flag_frame,
            text=intro,
            font=("Courier New", 12, "bold"),
            fg="#00ff88",
            bg="#1e1e2f",
            wraplength=760,
            justify="center",
        )
        self.intro_label.pack(pady=10)

        tk.Label(self.flag_frame, text="🔐 Enter Flag", font=("Courier New", 12), fg="#00ff88", bg="#1e1e2f").pack(pady=10)
        self.flag_entry = tk.Entry(self.flag_frame, font=("Courier New", 12), width=40, bg="black", fg="#00ff88", insertbackground="#00ff88")
        self.flag_entry.pack(pady=5)
        if first_flag:
            self.flag_entry.insert(0, first_flag)
        tk.Button(self.flag_frame, text="Submit Flag", command=self.submit_flag, font=("Courier New", 11), bg="#00ff88", fg="#1e1e2f").pack(pady=5)

        self.story_output = scrolledtext.ScrolledText(self.flag_frame, wrap=tk.WORD, font=("Courier", 10))
        self.story_output.pack(expand=True, fill='both', padx=10, pady=10)

        self.status_frame = tk.Frame(self.flag_frame, bg="#1e1e2f")
        self.status_frame.pack(side='right', fill='y', padx=10)

        self.level_var = tk.StringVar(value="Level: 0")
        self.stage_var = tk.StringVar(value="Stage: 0")
        self.score_var = tk.StringVar(value="Score: 0")

        tk.Label(self.status_frame, text="📊 STATUS", font=("Courier New", 12, "bold"), fg="#00ff88", bg="#1e1e2f").pack(pady=(5, 5))
        tk.Label(self.status_frame, textvariable=self.level_var, font=("Courier New", 11), fg="#00ff88", bg="#1e1e2f").pack()
        tk.Label(self.status_frame, textvariable=self.stage_var, font=("Courier New", 11), fg="#00ff88", bg="#1e1e2f").pack()
        tk.Label(self.status_frame, textvariable=self.score_var, font=("Courier New", 11), fg="#00ff88", bg="#1e1e2f").pack()

    def mission_complete_screen(self, final_story):
        for widget in self.flag_frame.winfo_children():
            widget.destroy()
        self.flag_frame.configure(bg="black")

        self.fade_label = tk.Label(self.flag_frame, text="🎖️ MISSION COMPLETE 🎖️", font=("Arial", 28, "bold"), fg="black", bg="black")
        self.fade_label.pack(pady=40)

        self.score_label = tk.Label(self.flag_frame, text=f"Final Score: {self.total_score}", font=("Arial", 18), fg="white", bg="black")
        self.score_label.pack(pady=10)

        story_text = scrolledtext.ScrolledText(self.flag_frame, wrap=tk.WORD, font=("Courier", 12), bg="black", fg="lightgray")
        story_text.insert(tk.END, final_story)
        story_text.configure(state='disabled')
        story_text.pack(padx=20, pady=20, fill='both', expand=True)

        exit_button = tk.Button(self.flag_frame, text="Exit", font=("Arial", 12), command=self.quit)
        exit_button.pack(pady=10)

        self.fade_counter = 0
        self.fade_in_label()
        self.pulse_brightness = 0
        self.glow_up = True
        self.pulse_glow()

    def fade_in_label(self):
        colors = ["#101010", "#202020", "#303030", "#404040", "#505050", "#606060", "#707070", "#808080", "#909090", "#a0a0a0", "#b0b0b0", "#c0c0c0", "#d0d0d0", "#e0e0e0", "#ffffff"]
        if self.fade_counter < len(colors):
            self.fade_label.config(fg=colors[self.fade_counter])
            self.fade_counter += 1
            self.after(100, self.fade_in_label)

    def pulse_glow(self):
        green_levels = [hex(x)[2:].zfill(2) for x in range(100, 256, 5)]
        if not hasattr(self, 'glow_index'):
            self.glow_index = 0

        if self.glow_up:
            self.glow_index += 1
            if self.glow_index >= len(green_levels) - 1:
                self.glow_up = False
        else:
            self.glow_index -= 1
            if self.glow_index <= 0:
                self.glow_up = True

        green = green_levels[self.glow_index]
        glow_color = f"#00{green}00"
        self.fade_label.config(fg=glow_color)
        self.after(100, self.pulse_glow)

    def send_flag(self, flag):
        return self.api_post("/api/submit-flag", {"flag": flag})

    def handle_client_action(self, action):
        """Run only allowlisted local actions from the server. Never use shell=True here."""
        if not action:
            return

        action_type = action.get("type")

        if action_type == "sequence":
            for child_action in action.get("actions", []):
                if isinstance(child_action, dict):
                    self.handle_client_action(child_action)
            return

        if action_type == "message":
            messagebox.showinfo("Message", str(action.get("text", "")))
            return

        if action_type == "open_url":
            url = str(action.get("url", ""))
            if url.startswith(("https://", "http://")):
                webbrowser.open(url)
            else:
                messagebox.showerror("Blocked Action", f"Refused to open non-HTTP URL: {url}")
            return

        if action_type == "set_volume":
            muted = bool(action.get("muted", False))
            volume_percent = int(action.get("volume_percent", 100))
            volume_percent = max(0, min(volume_percent, 100))
            try:
                subprocess.Popen(["pactl", "set-sink-mute", "@DEFAULT_SINK@", "1" if muted else "0"])
                subprocess.Popen(["pactl", "set-sink-volume", "@DEFAULT_SINK@", f"{volume_percent}%"])
            except Exception as e:
                messagebox.showerror("Action Error", f"Failed to adjust volume: {e}")
            return

        messagebox.showwarning("Unknown Action", f"Server requested an unknown safe action: {action_type}")

    def submit_flag(self):
        flag = self.flag_entry.get().strip()
        if not flag:
            return

        if flag in unlocked_flags:
            messagebox.showinfo("Duplicate", "⚠️ Flag already submitted.")
            return

        response_data = self.send_flag(flag)
        response_text = response_data.get("display_text") or response_data.get("message") or str(response_data)

        if hasattr(self, "intro_label"):
            self.intro_label.destroy()

        if not response_data.get("ok", False):
            self.story_output.insert(tk.END, f"🔴 {flag} rejected.\n{response_text}\n{'='*60}\n")
            self.flag_entry.delete(0, tk.END)
            return

        self.flag_response_cache[flag] = response_data
        unlocked_flags.add(flag)

        level_value = str(response_data.get("level", "")).strip()
        is_bonus = (level_value.lower() == "bonus")

        try:
            self.total_score += int(response_data.get("points", 0))
            self.score_var.set(f"Score: {self.total_score}")
        except (TypeError, ValueError):
            pass

        if not is_bonus:
            self.level_var.set(f"Level: {level_value}")
            real_flags = self.get_non_bonus_flags()
            self.stage_var.set(f"Stage: {len(real_flags)}")

            if len(real_flags) >= TOTAL_FLAGS:
                self.handle_client_action(response_data.get("client_action"))
                self.mission_complete_screen(response_text)
                return

        self.story_output.insert(tk.END, f"🟢 {flag} accepted!\n{response_text}\n{'='*60}\n")
        self.flag_entry.delete(0, tk.END)
        self.handle_client_action(response_data.get("client_action"))

    def get_non_bonus_flags(self):
        results = []
        for flag in unlocked_flags:
            response = self.flag_response_cache.get(flag)
            if response:
                level_value = str(response.get("level", "")).strip().lower()
                if level_value and level_value != "bonus":
                    results.append(flag)
        return results


class MatrixEffect:
    def __init__(self, canvas):
        self.canvas = canvas
        self.width = canvas.winfo_width()
        self.height = canvas.winfo_height()
        self.columns = max(1, int(self.width / 10))
        self.drops = [0 for _ in range(self.columns)]
        self.canvas.bind("<Configure>", self.on_resize)

    def on_resize(self, event):
        self.width = event.width
        self.height = event.height
        new_columns = max(1, int(self.width / 10))
        if new_columns != len(self.drops):
            self.columns = new_columns
            self.drops = [0 for _ in range(self.columns)]

    def draw(self):
        self.canvas.delete("matrix")
        for i in range(self.columns):
            char = random.choice(["0", "1"])
            x = i * 10
            y = self.drops[i] * 10

            self.canvas.create_text(x, y, text=char, fill="#00FF00", font=("Courier", 10), tags="matrix")

            if y > self.height and random.random() > 0.975:
                self.drops[i] = 0
            self.drops[i] += 1
        self.canvas.after(33, self.draw)


if __name__ == "__main__":
    app = CTFApp()
    app.mainloop()
