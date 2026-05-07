#!/usr/bin/env python3

import subprocess
import sys


PACKAGES = [
    "numpy",
    "pandas",
    "openai",
    "pydantic",
    "pydantic-ai",
]


def install(packages: list[str]) -> None:
    print(f"Installing {len(packages)} package(s) with pip...\n")
    cmd = [sys.executable, "-m", "pip", "install", *packages]
    result = subprocess.run(cmd, check=False)
    if result.returncode != 0:
        print("\n[ERROR] One or more packages failed to install.", file=sys.stderr)
        sys.exit(result.returncode)
    print("\n[OK] All packages installed successfully.")


if __name__ == "__main__":
    install(PACKAGES)
