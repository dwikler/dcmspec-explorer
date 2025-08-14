# Contributing

Thank you for considering contributing to this project! Please follow the guidelines below to help keep the codebase consistent and maintainable.

## Pre-commit Hooks

This project uses **pre-commit hooks** to automate checks and code generation before each commit. These help maintain code quality and consistency across the team.

### 🛠️ Qt Designer `.ui` Files

A pre-commit hook ensures that all `.ui` files (created/edited with Qt Designer) are compiled to their corresponding Python helper files before each commit. This prevents out-of-sync UI code and ensures the application reflects the latest UI design.

### 🧹 Ruff Linting and Formatting

We also use [Ruff](https://github.com/astral-sh/ruff) via the [`ruff-pre-commit`](https://github.com/astral-sh/ruff-pre-commit) remote hook to automatically check and format Python code. This ensures fast and consistent linting and formatting across the project.

Ruff is configured in `pyproject.toml` under the `[tool.ruff]` section:

```toml
[tool.ruff]
line-length = 120
select = ["E", "F", "D"]  # E includes line-too-long (E501), F includes runtime errors, D includes docstring checks
```

This configuration helps enforce clean, readable, and well-documented code.

### 🔧 Setting up the Pre-commit Hooks

To enable the pre-commit hooks, run:

```bash
poetry run pre-commit install
```

This installs the hooks into your local `.git` configuration. From now on, every time you commit:

- The UI compiler will update generated Python files if any `.ui` files have changed.
- Ruff will lint and format your Python code automatically.

### Workflow for Editing UI Files

1. Open and edit the relevant `.ui` file(s) in Qt Designer (found in `src/dcmspec_explorer/resources/`).
2. Save your changes in Qt Designer.
3. **Always recompile all `.ui` files to Python helpers by running:**

   ```
   poetry run compile-ui
   ```

   This ensures you see any changes and can test them before committing.

4. Test your application to verify the UI changes work as expected.
5. Stage and commit your changes as usual. The pre-commit hook will automatically recompile `.ui` files and update the generated Python files if needed.
6. If the hook updates any generated files, you will need to add them to your commit and re-commit.

> **Note:**  
> Always make sure that both the `.ui` files and their generated Python helpers (e.g., `main_window_ui.py`) are committed and pushed together. This ensures that all contributors and CI environments have the correct, up-to-date UI code.

### Troubleshooting

- If you see a message about unstaged changes to generated Python files after a commit attempt, **do not just add and commit them blindly**.  
  Instead, review the changes, recompile if necessary, and **test the UI application** to ensure everything works as expected.  
  Only then should you stage and commit the updated files.
- If you have issues with the pre-commit hook, you can always manually run:

  ```
  poetry run compile-ui
  ```

  to update all generated UI helpers.

### Why do we commit both `.ui` and generated Python files?

- The `.ui` files are the source of truth for the UI and are editable in Qt Designer.
- The generated Python files are required for running the application and for environments (like CI) that may not have Qt Designer or the UI compiler installed.
- Committing both ensures a smooth workflow for all contributors and reliable builds.

## Why We Use the UI Compiler Approach

We use the UI compiler (`pyside6-uic`) to convert Qt Designer `.ui` files into Python modules, instead of loading `.ui` files at runtime. This approach:

- Ensures all UI properties and widgets are set automatically and consistently.
- Supports a clean MVP pattern.
- Avoids runtime ui file loader issues.
- Makes development, testing, and CI/CD more robust and maintainable.

---

Thank you for helping keep the project clean and consistent!
