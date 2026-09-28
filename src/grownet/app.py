"""The entry point of the self-contained program (the Windows build, #26).

Double-clicked, with no arguments, it opens the local page in the browser, as `grownet gui` does, and the
console window it runs in shows the address and stops the tool when it is closed. Given arguments it is
the command line: `grownet.exe derive ...`, `grownet.exe gui --port 8765`, and options alone go to the page
(`grownet.exe --no-browser`). A message that stops it, such as a port already in use, stays on screen until
Enter is pressed, since a double-clicked window would otherwise close before it could be read.
"""
from __future__ import annotations

import sys
import traceback

from .__main__ import main

COMMANDS = ("derive", "style", "validate", "gui", "schema")


def arguments(argv) -> list:
    """The command line to run: the local page unless a command is named."""
    args = list(argv)
    if not args or args[0] not in COMMANDS and args[0] not in ("-h", "--help"):
        return ["gui", *args]
    return args


def run(argv=None, wait=input) -> int:
    argv = sys.argv[1:] if argv is None else list(argv)
    double_clicked = not argv
    try:
        code = main(arguments(argv))
    except SystemExit as e:
        code = e.code
        if isinstance(code, str):
            print(code)
            code = 1
    except Exception:                       # noqa: BLE001 - shown to the person, not lost with the window
        traceback.print_exc()
        code = 1
    if code and double_clicked:
        wait("Press Enter to close this window.")
    return int(code or 0)


if __name__ == "__main__":
    sys.exit(run())
