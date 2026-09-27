"""PyInstaller entry for the Windows build: see crossfeed.app."""
import sys

from crossfeed.app import run

if __name__ == "__main__":
    sys.exit(run())
