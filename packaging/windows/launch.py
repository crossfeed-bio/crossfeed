"""PyInstaller entry for the Windows build: see grownet.app.

Not called grownet.py: a script of that name would itself be the module `grownet` inside the program, and
`from grownet.app import run` would then fail ("'grownet' is not a package"), as CI showed on the rename.
The program is still grownet.exe, from build.py's --name."""
import sys

from grownet.app import run

if __name__ == "__main__":
    sys.exit(run())
