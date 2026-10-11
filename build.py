"""Build a one-file executable with the dedicated project TLS certificate."""

from pathlib import Path
import subprocess
import sys


def main() -> None:
    root = Path(__file__).resolve().parent
    cert = root / "tls" / "fullchain.pem"
    key = root / "tls" / "privkey.pem"
    if not cert.is_file() or not key.is_file():
        raise SystemExit("Put the dedicated project certificate and key in tls/ before building")
    command = [
        sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--onefile",
        "--console", "--name", "GeelyGalaxyADBUnlocker",
        "--add-data", f"{cert}{';' if sys.platform == 'win32' else ':'}tls",
        "--add-data", f"{key}{';' if sys.platform == 'win32' else ':'}tls",
    ]
    if sys.platform == "win32":
        command.extend(["--hidden-import", "winrt.windows.networking.connectivity"])
        command.extend(["--hidden-import", "winrt.windows.networking.networkoperators"])
    command.append(str(root / "unlocker.py"))
    subprocess.run(command, cwd=root, check=True)


if __name__ == "__main__":
    main()
