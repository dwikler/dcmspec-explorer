"""Script to build a native app with pyside6-deploy."""

import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main():
    """Build the native app from a copy of the spec, since pyside6-deploy rewrites the spec it is given."""
    deploy_path = shutil.which("pyside6-deploy")
    if not deploy_path:
        raise RuntimeError("pyside6-deploy not found in PATH. Make sure your Poetry environment is active.")

    build_dir = ROOT / "build"
    build_dir.mkdir(exist_ok=True)
    spec_copy = build_dir / "pysidedeploy.spec"
    shutil.copy(ROOT / "pysidedeploy.spec", spec_copy)

    cmd = [deploy_path, "-c", str(spec_copy), "-f"]
    print("Running:", " ".join(cmd))
    subprocess.run(cmd, check=True, cwd=ROOT)


if __name__ == "__main__":
    main()
