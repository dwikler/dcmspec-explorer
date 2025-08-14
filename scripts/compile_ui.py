"""Script to compile Qt UI files into Python modules."""

import subprocess
import shutil
import os


def main():
    """Compile Qt UI files into Python modules."""
    ui_dir = "src/dcmspec_explorer/resources"
    out_dir = "src/dcmspec_explorer/view"
    uic_path = shutil.which("pyside6-uic")
    if not uic_path:
        raise RuntimeError("pyside6-uic not found in PATH. Make sure your Poetry environment is active.")

    for filename in os.listdir(ui_dir):
        if filename.endswith(".ui"):
            ui_path = os.path.join(ui_dir, filename)
            base = os.path.splitext(filename)[0]
            py_path = os.path.join(out_dir, f"{base}_ui.py")
            cmd = [uic_path, ui_path, "-o", py_path]
            print("Running:", " ".join(cmd))
            subprocess.run(cmd, check=True)
            print(f"Compiled {ui_path} to {py_path}")


if __name__ == "__main__":
    main()
