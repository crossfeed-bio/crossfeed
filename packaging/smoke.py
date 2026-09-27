"""Start the local page from an installed or built grownet, check it answers, and stop it.

Usage: python packaging/smoke.py COMMAND [ARGS...], for example `grownet.exe --no-browser` or
`crossfeed gui --no-browser`. Used by CI on the clean install and on the Windows build (#26, #27).
"""
import re
import subprocess
import sys
import threading
import time
import urllib.request


def main(command) -> int:
    proc = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    found = {}

    def read():
        for line in proc.stdout:
            print(line, end="")
            m = re.search(r"(http://127\.0\.0\.1:\d+/\?token=\S+)", line)
            if m:
                found["url"] = m.group(1)

    threading.Thread(target=read, daemon=True).start()
    try:
        for _ in range(120):
            if "url" in found or proc.poll() is not None:
                break
            time.sleep(0.5)
        if "url" not in found:
            print("smoke: the program printed no address", file=sys.stderr)
            return 1
        with urllib.request.urlopen(found["url"], timeout=30) as response:
            page = response.read().decode("utf-8")
        if "grow<b>net</b>" not in page or 'class="version"' not in page:
            print("smoke: the page is not the grownet page", file=sys.stderr)
            return 1
        version = re.search(r'class="version">([^<]+)<', page).group(1)
        print(f"smoke: the page answers, version {version}")
        return 0
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
