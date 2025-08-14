# DCMspec Explorer (PySide6 Edition)

A modern PySide6-based GUI application for exploring DICOM specifications, powered by the [DCMspec](https://github.com/dwikler/dcmspec) library.

## Features

- Browse and search DICOM IODs
- Download and cache DICOM standard documents
- Creates JSON specification models

## Requirements

- Python 3.8+
- [DCMspec](https://github.com/dwikler/dcmspec)
- PySide6

## Installation

1. **Install Python 3.8+**  
   Download from [python.org](https://www.python.org/downloads/) or use your OS package manager.

2. **(Recommended) Create and activate a virtual environment:**

   On macOS/Linux:

   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   ```

   On Windows:

   ```cmd
   python -m venv .venv
   .venv\Scripts\activate
   ```

3. **Install the PySide6 application (dcmspec will be installed automatically as a dependency):**

   ```bash
   git clone https://github.com/yourusername/dcmspec-explorer.git
   cd dcmspec-explorer
   pip install .
   ```

4. **Run the app:**
   ```bash
   dcmspec-explorer-qt
   ```
