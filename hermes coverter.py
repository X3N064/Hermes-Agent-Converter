#!/usr/bin/env python3
"""
Hermes OS Migrator GUI

A small cross-platform Tkinter app for exporting/importing a Hermes ~/.hermes
folder between Linux/WSL and macOS.

Main goals:
- GUI: choose direction, choose .hermes path, click Convert.
- Export creates a portable .zip archive.
- Original source folder is never modified.
- Import extracts to a target .hermes folder with optional backup.
- Optional path rewriting for common Linux/WSL <-> macOS path differences.

Tested design target:
- Python 3.8+
- Linux / WSL / macOS
- No third-party packages required.
"""

from __future__ import annotations

import datetime as _dt
import os
import re
import shutil
import sys
import tempfile
import zipfile
from pathlib import Path
from typing import Iterable, List, Tuple

import tkinter as tk
from tkinter import filedialog, messagebox, ttk

APP_NAME = "Hermes OS Migrator"
ARCHIVE_MARKER = "HERMES_MIGRATOR_ARCHIVE.txt"

# File/folder names that are usually not worth migrating.
DEFAULT_EXCLUDES = {
    ".venv",
    "venv",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "node_modules",
    ".DS_Store",
    "logs",
    "cache",
    "tmp",
    "temp",
    "sessions",
}

# Common text/config extensions safe enough to rewrite paths in.
TEXT_EXTENSIONS = {
    ".txt",
    ".md",
    ".yaml",
    ".yml",
    ".json",
    ".toml",
    ".ini",
    ".conf",
    ".cfg",
    ".env",
    ".sh",
    ".py",
    ".js",
    ".ts",
    ".mjs",
    ".cjs",
    ".plist",
}

DIRECTIONS = {
    "linux_to_macos": "Linux / WSL → macOS",
    "macos_to_linux": "macOS → Linux / WSL",
}


def timestamp() -> str:
    return _dt.datetime.now().strftime("%Y%m%d-%H%M%S")


def is_probably_binary(path: Path, sample_size: int = 4096) -> bool:
    try:
        data = path.read_bytes()[:sample_size]
    except Exception:
        return True
    if b"\x00" in data:
        return True
    try:
        data.decode("utf-8")
        return False
    except UnicodeDecodeError:
        return True


def should_exclude(path: Path) -> bool:
    return any(part in DEFAULT_EXCLUDES for part in path.parts)


def ensure_hermes_dir(path: Path) -> bool:
    if not path.exists() or not path.is_dir():
        return False
    # Do not be too strict. Some Hermes dirs may not contain all these files.
    if path.name == ".hermes":
        return True
    likely = ["config.yaml", "config.yml", "SOUL.md", "MEMORY.md", "skills"]
    return any((path / item).exists() for item in likely)


def copy_portable_tree(source: Path, dest: Path) -> List[str]:
    copied: List[str] = []
    source = source.resolve()
    dest.mkdir(parents=True, exist_ok=True)

    for root, dirs, files in os.walk(source):
        root_path = Path(root)
        rel_root = root_path.relative_to(source)

        # Mutate dirs in-place to prevent walking excluded folders.
        dirs[:] = [d for d in dirs if not should_exclude(rel_root / d)]

        target_root = dest / rel_root
        target_root.mkdir(parents=True, exist_ok=True)

        for filename in files:
            rel_file = rel_root / filename
            if should_exclude(rel_file):
                continue
            src_file = root_path / filename
            dst_file = target_root / filename
            try:
                shutil.copy2(src_file, dst_file)
                copied.append(str(rel_file))
            except Exception as exc:
                copied.append(f"SKIPPED {rel_file}: {exc}")
    return copied


def rewrite_text_paths(root: Path, direction: str, source_user: str, target_user: str) -> Tuple[int, int]:
    """Rewrite common absolute path patterns inside copied temp files only."""
    files_changed = 0
    replacements = 0

    if not source_user:
        source_user = "x3n064"
    if not target_user:
        target_user = os.environ.get("USER") or os.environ.get("USERNAME") or "user"

    linux_home = f"/home/{source_user}"
    mac_home = f"/Users/{target_user}"

    rules: List[Tuple[re.Pattern[str], str]] = []

    if direction == "linux_to_macos":
        rules = [
            (re.compile(re.escape(linux_home)), mac_home),
            (re.compile(r"/home/([A-Za-z0-9._-]+)"), mac_home),
            # WSL Windows home paths commonly point to user files. Convert to mac home as best effort.
            (re.compile(r"/mnt/c/Users/[^/\\]+"), mac_home),
            (re.compile(r"C:\\\\Users\\\\[^\\\"']+"), mac_home.replace("/", r"\\")),
        ]
    elif direction == "macos_to_linux":
        target_linux_home = f"/home/{target_user}"
        rules = [
            (re.compile(re.escape(mac_home)), target_linux_home),
            (re.compile(r"/Users/([A-Za-z0-9._-]+)"), target_linux_home),
        ]
    else:
        return files_changed, replacements

    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if path.suffix not in TEXT_EXTENSIONS and path.name not in {".env", "config"}:
            continue
        if is_probably_binary(path):
            continue
        try:
            original = path.read_text(encoding="utf-8")
        except Exception:
            continue

        updated = original
        local_replacements = 0
        for pattern, repl in rules:
            updated, count = pattern.subn(repl, updated)
            local_replacements += count

        if updated != original:
            path.write_text(updated, encoding="utf-8")
            files_changed += 1
            replacements += local_replacements

    return files_changed, replacements


def write_manifest(root: Path, direction: str, source_path: Path, files: Iterable[str]) -> None:
    manifest = root / ARCHIVE_MARKER
    manifest.write_text(
        "\n".join(
            [
                "Hermes OS Migrator archive",
                f"created_at={_dt.datetime.now().isoformat(timespec='seconds')}",
                f"direction={direction}",
                f"source_path={source_path}",
                "original_source_modified=false",
                "archive_format=zip",
                "",
                "files:",
                *[f"- {item}" for item in files],
            ]
        ),
        encoding="utf-8",
    )


def create_zip_from_folder(folder: Path, zip_path: Path) -> None:
    zip_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for path in folder.rglob("*"):
            if path.is_file():
                zf.write(path, path.relative_to(folder))


def safe_extract_zip(zip_path: Path, target_dir: Path) -> None:
    target_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path, "r") as zf:
        for member in zf.infolist():
            member_path = target_dir / member.filename
            resolved = member_path.resolve()
            if not str(resolved).startswith(str(target_dir.resolve())):
                raise RuntimeError(f"Unsafe zip path detected: {member.filename}")
        zf.extractall(target_dir)


def backup_existing_target(target: Path) -> Path | None:
    if not target.exists():
        return None
    backup = target.with_name(f"{target.name}.backup-{timestamp()}")
    shutil.copytree(target, backup)
    return backup


class HermesMigratorApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title(APP_NAME)
        self.geometry("760x560")
        self.minsize(720, 520)

        self.direction_var = tk.StringVar(value="linux_to_macos")
        self.source_var = tk.StringVar(value=str(Path.home() / ".hermes"))
        self.output_var = tk.StringVar(value=str(Path.home() / f"hermes-migration-{timestamp()}.zip"))
        self.source_user_var = tk.StringVar(value=os.environ.get("USER") or os.environ.get("USERNAME") or "x3n064")
        self.target_user_var = tk.StringVar(value=os.environ.get("USER") or os.environ.get("USERNAME") or "user")
        self.rewrite_var = tk.BooleanVar(value=True)

        self.import_zip_var = tk.StringVar(value="")
        self.import_target_var = tk.StringVar(value=str(Path.home() / ".hermes"))
        self.import_backup_var = tk.BooleanVar(value=True)
        self.import_rewrite_var = tk.BooleanVar(value=True)
        self.import_direction_var = tk.StringVar(value="linux_to_macos")
        self.import_source_user_var = tk.StringVar(value="x3n064")
        self.import_target_user_var = tk.StringVar(value=os.environ.get("USER") or os.environ.get("USERNAME") or "user")

        self._build_ui()

    def _build_ui(self) -> None:
        pad = {"padx": 12, "pady": 8}
        title = ttk.Label(self, text=APP_NAME, font=("TkDefaultFont", 18, "bold"))
        title.pack(anchor="w", **pad)

        subtitle = ttk.Label(
            self,
            text="Export/import Hermes ~/.hermes between Linux/WSL and macOS. Source folders are not modified.",
        )
        subtitle.pack(anchor="w", padx=12)

        notebook = ttk.Notebook(self)
        notebook.pack(fill="both", expand=True, padx=12, pady=12)

        export_frame = ttk.Frame(notebook)
        import_frame = ttk.Frame(notebook)
        notebook.add(export_frame, text="Export / Convert to ZIP")
        notebook.add(import_frame, text="Import ZIP")

        self._build_export_tab(export_frame)
        self._build_import_tab(import_frame)

        self.status = tk.Text(self, height=8, wrap="word")
        self.status.pack(fill="both", expand=False, padx=12, pady=(0, 12))
        self.log("Ready.")

    def _row(self, parent: ttk.Frame, label: str, row: int) -> ttk.Frame:
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", padx=10, pady=8)
        frame = ttk.Frame(parent)
        frame.grid(row=row, column=1, sticky="ew", padx=10, pady=8)
        parent.columnconfigure(1, weight=1)
        return frame

    def _build_export_tab(self, frame: ttk.Frame) -> None:
        frame.columnconfigure(1, weight=1)

        row = self._row(frame, "Direction", 0)
        ttk.Radiobutton(row, text=DIRECTIONS["linux_to_macos"], variable=self.direction_var, value="linux_to_macos").pack(anchor="w")
        ttk.Radiobutton(row, text=DIRECTIONS["macos_to_linux"], variable=self.direction_var, value="macos_to_linux").pack(anchor="w")

        row = self._row(frame, ".hermes folder", 1)
        ttk.Entry(row, textvariable=self.source_var).pack(side="left", fill="x", expand=True)
        ttk.Button(row, text="Browse", command=self.browse_source).pack(side="left", padx=(8, 0))

        row = self._row(frame, "Output ZIP", 2)
        ttk.Entry(row, textvariable=self.output_var).pack(side="left", fill="x", expand=True)
        ttk.Button(row, text="Save As", command=self.browse_output).pack(side="left", padx=(8, 0))

        row = self._row(frame, "Path users", 3)
        ttk.Label(row, text="Source user").pack(side="left")
        ttk.Entry(row, textvariable=self.source_user_var, width=14).pack(side="left", padx=(6, 16))
        ttk.Label(row, text="Target user").pack(side="left")
        ttk.Entry(row, textvariable=self.target_user_var, width=14).pack(side="left", padx=(6, 0))

        row = self._row(frame, "Options", 4)
        ttk.Checkbutton(row, text="Rewrite common absolute paths inside copied config files", variable=self.rewrite_var).pack(anchor="w")

        row = ttk.Frame(frame)
        row.grid(row=5, column=0, columnspan=2, sticky="ew", padx=10, pady=18)
        ttk.Button(row, text="Convert", command=self.export_zip).pack(side="right")

    def _build_import_tab(self, frame: ttk.Frame) -> None:
        frame.columnconfigure(1, weight=1)

        row = self._row(frame, "Direction", 0)
        ttk.Radiobutton(row, text=DIRECTIONS["linux_to_macos"], variable=self.import_direction_var, value="linux_to_macos").pack(anchor="w")
        ttk.Radiobutton(row, text=DIRECTIONS["macos_to_linux"], variable=self.import_direction_var, value="macos_to_linux").pack(anchor="w")

        row = self._row(frame, "Input ZIP", 1)
        ttk.Entry(row, textvariable=self.import_zip_var).pack(side="left", fill="x", expand=True)
        ttk.Button(row, text="Browse", command=self.browse_import_zip).pack(side="left", padx=(8, 0))

        row = self._row(frame, "Target .hermes", 2)
        ttk.Entry(row, textvariable=self.import_target_var).pack(side="left", fill="x", expand=True)
        ttk.Button(row, text="Browse", command=self.browse_import_target).pack(side="left", padx=(8, 0))

        row = self._row(frame, "Path users", 3)
        ttk.Label(row, text="Source user").pack(side="left")
        ttk.Entry(row, textvariable=self.import_source_user_var, width=14).pack(side="left", padx=(6, 16))
        ttk.Label(row, text="Target user").pack(side="left")
        ttk.Entry(row, textvariable=self.import_target_user_var, width=14).pack(side="left", padx=(6, 0))

        row = self._row(frame, "Options", 4)
        ttk.Checkbutton(row, text="Backup existing target before import", variable=self.import_backup_var).pack(anchor="w")
        ttk.Checkbutton(row, text="Rewrite common absolute paths after import", variable=self.import_rewrite_var).pack(anchor="w")

        row = ttk.Frame(frame)
        row.grid(row=5, column=0, columnspan=2, sticky="ew", padx=10, pady=18)
        ttk.Button(row, text="Import", command=self.import_zip).pack(side="right")

    def log(self, message: str) -> None:
        now = _dt.datetime.now().strftime("%H:%M:%S")
        self.status.insert("end", f"[{now}] {message}\n")
        self.status.see("end")
        self.update_idletasks()

    def browse_source(self) -> None:
        path = filedialog.askdirectory(title="Select Hermes .hermes folder", initialdir=str(Path.home()))
        if path:
            self.source_var.set(path)

    def browse_output(self) -> None:
        path = filedialog.asksaveasfilename(
            title="Save migration ZIP",
            defaultextension=".zip",
            filetypes=[("ZIP archive", "*.zip")],
            initialfile=f"hermes-migration-{timestamp()}.zip",
        )
        if path:
            self.output_var.set(path)

    def browse_import_zip(self) -> None:
        path = filedialog.askopenfilename(title="Select migration ZIP", filetypes=[("ZIP archive", "*.zip")])
        if path:
            self.import_zip_var.set(path)

    def browse_import_target(self) -> None:
        path = filedialog.askdirectory(title="Select target .hermes folder or parent location", initialdir=str(Path.home()))
        if path:
            # If user picks home, default to ~/.hermes. If they pick .hermes, use it directly.
            p = Path(path)
            self.import_target_var.set(str(p if p.name == ".hermes" else p / ".hermes"))

    def export_zip(self) -> None:
        source = Path(self.source_var.get()).expanduser()
        output = Path(self.output_var.get()).expanduser()
        direction = self.direction_var.get()

        if not ensure_hermes_dir(source):
            messagebox.showerror("Invalid source", "Please select a valid Hermes .hermes folder.")
            return
        if output.suffix.lower() != ".zip":
            output = output.with_suffix(".zip")
            self.output_var.set(str(output))

        try:
            self.log(f"Export started: {DIRECTIONS.get(direction, direction)}")
            self.log(f"Source: {source}")
            self.log(f"Output: {output}")
            with tempfile.TemporaryDirectory(prefix="hermes-migrator-") as tmp:
                tmp_root = Path(tmp) / ".hermes"
                copied = copy_portable_tree(source, tmp_root)
                self.log(f"Copied portable files: {len(copied)}")

                if self.rewrite_var.get():
                    changed, count = rewrite_text_paths(
                        tmp_root,
                        direction,
                        self.source_user_var.get().strip(),
                        self.target_user_var.get().strip(),
                    )
                    self.log(f"Path rewrite in temp copy: {changed} files, {count} replacements")

                write_manifest(tmp_root, direction, source, copied)
                create_zip_from_folder(tmp_root, output)

            self.log("Export finished. Original folder was not modified.")
            messagebox.showinfo("Done", f"Created ZIP:\n{output}\n\nOriginal folder was not modified.")
        except Exception as exc:
            self.log(f"ERROR: {exc}")
            messagebox.showerror("Export failed", str(exc))

    def import_zip(self) -> None:
        zip_path = Path(self.import_zip_var.get()).expanduser()
        target = Path(self.import_target_var.get()).expanduser()
        direction = self.import_direction_var.get()

        if not zip_path.exists() or zip_path.suffix.lower() != ".zip":
            messagebox.showerror("Invalid ZIP", "Please select a valid .zip archive.")
            return

        try:
            self.log(f"Import started: {zip_path}")
            backup = None
            if target.exists() and self.import_backup_var.get():
                backup = backup_existing_target(target)
                self.log(f"Backup created: {backup}")

            # Extract into target. Existing files may be overwritten only after backup.
            safe_extract_zip(zip_path, target)
            self.log(f"Extracted to: {target}")

            if self.import_rewrite_var.get():
                changed, count = rewrite_text_paths(
                    target,
                    direction,
                    self.import_source_user_var.get().strip(),
                    self.import_target_user_var.get().strip(),
                )
                self.log(f"Path rewrite after import: {changed} files, {count} replacements")

            self.log("Import finished.")
            extra = f"\nBackup: {backup}" if backup else ""
            messagebox.showinfo("Done", f"Imported to:\n{target}{extra}")
        except Exception as exc:
            self.log(f"ERROR: {exc}")
            messagebox.showerror("Import failed", str(exc))


def main() -> int:
    app = HermesMigratorApp()
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
