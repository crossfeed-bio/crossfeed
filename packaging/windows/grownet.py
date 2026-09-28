"""PyInstaller entry for the Windows build: see grownet.app."""
import sys

from grownet.app import run

if __name__ == "__main__":
    sys.exit(run())
