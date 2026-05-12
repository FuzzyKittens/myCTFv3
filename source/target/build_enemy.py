#!/usr/bin/env python3
# PATCH_VERSION: v3

import subprocess
from pathlib import Path
from PIL import Image, PngImagePlugin
from challenge_logging import log_command, log_exception, log_step

SCRIPT_NAME = "build_enemy.py"
nuclear_png_path = Path("nuclear.png")
flag_path = Path("/tmp/flag.txt")
zip_path = Path("/tmp/flag.zip")
combined_path = Path("/tmp/combined_nuclear.png")
enemy_docs_dir = Path("/home/enemy/documents")
final_file_path = enemy_docs_dir / "nuclear.png"


def run_command(cmd):
    log_command(SCRIPT_NAME, cmd)
    subprocess.run(cmd, check=True)
    log_step(SCRIPT_NAME, f"Command completed: {' '.join(str(x) for x in cmd)}")


def main():
    log_step(SCRIPT_NAME, "Enemy steganography challenge setup started")

    log_step(SCRIPT_NAME, "Creating enemy user if missing")
    subprocess.run(["id", "enemy"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
    result = subprocess.run(["id", "enemy"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
    if result.returncode != 0:
        run_command(["sudo", "useradd", "-m", "enemy"])
    else:
        log_step(SCRIPT_NAME, "User enemy already exists; skipping useradd")

    log_step(SCRIPT_NAME, "Granting ctfuser read/execute ACL on /home/enemy")
    run_command(["sudo", "setfacl", "-m", "u:ctfuser:rx", "/home/enemy"])

    log_step(SCRIPT_NAME, f"Writing temporary flag file: {flag_path}")
    flag_path.write_text("CTF{1nfo_hidd3n_w1th1N}", encoding="utf-8")

    log_step(SCRIPT_NAME, f"Creating password-protected zip: {zip_path}")
    run_command(["zip", "-j", "-P", "P@ssw0rd1", str(zip_path), str(flag_path)])

    log_step(SCRIPT_NAME, f"Opening source image: {nuclear_png_path}")
    img = Image.open(nuclear_png_path)
    meta = PngImagePlugin.PngInfo()
    meta.add_text("Comment", "password = P@ssw0rd1")
    img_with_comment_path = Path("/tmp/nuclear_with_comment.png")
    log_step(SCRIPT_NAME, f"Saving image with PNG comment: {img_with_comment_path}")
    img.save(img_with_comment_path, "PNG", pnginfo=meta)

    log_step(SCRIPT_NAME, f"Combining PNG and ZIP into {combined_path}")
    with open(img_with_comment_path, "rb") as img_file, open(zip_path, "rb") as zf:
        combined_path.write_bytes(img_file.read() + zf.read())

    log_step(SCRIPT_NAME, f"Moving final challenge file to {final_file_path}")
    run_command(["sudo", "mkdir", "-p", str(enemy_docs_dir)])
    run_command(["sudo", "mv", str(combined_path), str(final_file_path)])
    run_command(["sudo", "chown", "enemy:enemy", str(final_file_path)])

    for path in [flag_path, zip_path, img_with_comment_path]:
        if path.exists():
            log_step(SCRIPT_NAME, f"Removing temporary file: {path}")
            path.unlink()

    log_step(SCRIPT_NAME, f"Enemy steganography challenge setup complete: {final_file_path}")
    print(f"✅ Final file with PNG comment and embedded zip is at: {final_file_path}")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        log_exception(SCRIPT_NAME, "Enemy challenge setup failed", exc)
        raise
