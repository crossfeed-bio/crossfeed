"""Build the self-contained Windows program: a one-folder PyInstaller build in a zip (#26).

Karoline chose a one-folder build over a single file (on #63): a single-file build unpacks itself on every
start, which antivirus software is quicker to block. Usage, from the repository root on Windows:

    python packaging/windows/build.py grownet-windows.zip

It needs PyInstaller installed (a build tool only: nothing is added to what the program depends on).
"""
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
NAME = "grownet"


def main(zip_name: str) -> int:
    subprocess.run([sys.executable, "-m", "PyInstaller", "--noconfirm", "--onedir", "--console", "--name", NAME,
                    "--collect-submodules", "grownet", str(ROOT / "packaging" / "windows" / "grownet.py")],
                   check=True, cwd=ROOT)
    folder = ROOT / "dist" / NAME
    for extra in (ROOT / "packaging" / "windows" / "README.txt", ROOT / "LICENSE", ROOT / "NOTICE"):
        shutil.copy(extra, folder / extra.name)
    archive = shutil.make_archive(str(ROOT / Path(zip_name).stem), "zip", root_dir=ROOT / "dist", base_dir=NAME)
    print(f"built {archive}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else f"{NAME}-windows.zip"))
