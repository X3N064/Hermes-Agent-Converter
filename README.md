# Hermes OS Migrator GUI

A small cross-platform Python/Tkinter app for exporting and importing a Hermes `~/.hermes` folder between Linux, WSL, and macOS.

The main goal is simple: choose a migration direction, select your `.hermes` folder, click **Convert**, and get a portable `.zip` archive. The original `.hermes` folder is never modified during export.

## Features

- GUI-based export/import workflow
- Linux/WSL to macOS migration mode
- macOS to Linux/WSL migration mode
- Creates a portable `.zip` archive
- Keeps the original source `.hermes` folder unchanged
- Excludes common non-portable or unnecessary folders such as `.venv`, `node_modules`, `logs`, `cache`, and `sessions`
- Optional path rewriting for common absolute path differences:
  - `/home/<user>` to `/Users/<user>`
  - `/Users/<user>` to `/home/<user>`
  - `/mnt/c/Users/<user>` to macOS-style home paths
- Import mode with optional backup of the existing target `.hermes` folder
- No third-party Python packages required

## Requirements

- Python 3.8+
- Tkinter
- Linux, WSL, or macOS

Tkinter is included with most Python installations. If it is missing on Ubuntu or WSL, install it with:

```bash
sudo apt update
sudo apt install python3-tk
```

On macOS, Python from the official Python installer usually includes Tkinter. If you use Homebrew Python and Tkinter is missing, install or reinstall Python with Tk support.

## Installation

Clone this repository or download the script directly:

```bash
git clone https://github.com/YOUR_USERNAME/hermes-os-migrator.git
cd hermes-os-migrator
```

Run the app:

```bash
python3 hermes_migrator_gui_english.py
```

## Usage

### Export / Convert to ZIP

Use this on the source machine.

1. Open the app.
2. Go to the **Export / Convert to ZIP** tab.
3. Select the migration direction:
   - `Linux / WSL → macOS`
   - `macOS → Linux / WSL`
4. Select your Hermes `.hermes` folder.
   - Linux/WSL default: `~/.hermes`
   - macOS default: `/Users/<username>/.hermes`
5. Choose the output `.zip` file path.
6. Keep **Rewrite common absolute paths inside copied config files** enabled unless you want a raw copy.
7. Click **Convert**.

The app copies portable files into a temporary directory, rewrites paths only inside that temporary copy, and then creates a `.zip` archive. Your original `.hermes` folder is not changed.

### Import ZIP

Use this on the target machine.

1. Install Hermes on the target OS first.
2. Open the app.
3. Go to the **Import ZIP** tab.
4. Select the migration direction.
5. Select the migration `.zip` file.
6. Select the target `.hermes` location.
7. Keep **Backup existing target before import** enabled if the target already has Hermes data.
8. Keep **Rewrite common absolute paths after import** enabled unless you want the archive imported exactly as-is.
9. Click **Import**.

If backup is enabled and the target `.hermes` folder already exists, the app creates a timestamped backup before importing.

## Recommended Migration Flow

### Linux/WSL to macOS

On Linux or WSL:

```bash
python3 hermes_migrator_gui_english.py
```

Export with:

```text
Direction: Linux / WSL → macOS
Source: ~/.hermes
Output: /path/to/usb/hermes-migration.zip
```

On macOS:

1. Install Hermes first.
2. Run the migrator.
3. Import the `.zip` into:

```text
/Users/<your_macos_username>/.hermes
```

Then verify Hermes:

```bash
hermes doctor
hermes model
hermes gateway setup
```

### macOS to Linux/WSL

On macOS:

```bash
python3 hermes_migrator_gui_english.py
```

Export with:

```text
Direction: macOS → Linux / WSL
Source: /Users/<your_macos_username>/.hermes
Output: /path/to/usb/hermes-migration.zip
```

On Linux or WSL:

1. Install Hermes first.
2. Run the migrator.
3. Import the `.zip` into:

```text
/home/<your_linux_username>/.hermes
```

Then verify Hermes:

```bash
hermes doctor
hermes model
hermes gateway setup
```

## What Gets Excluded

The migrator skips files and folders that are usually machine-specific, large, temporary, or not useful for migration:

```text
.venv
venv
__pycache__
.pytest_cache
.mypy_cache
.ruff_cache
node_modules
.DS_Store
logs
cache
tmp
temp
sessions
```

This keeps the archive smaller and reduces the chance of moving OS-specific runtime state.

## Path Rewriting

The migrator can rewrite common absolute paths inside copied text/config files.

Examples:

```text
/home/x3n064/project        -> /Users/ken/project
/Users/ken/project          -> /home/x3n064/project
/mnt/c/Users/Ken/Documents  -> /Users/ken/Documents
```

Only copied temporary files are rewritten during export. The original source folder is not modified.

During import, path rewriting is applied inside the imported target folder if the option is enabled.

Path rewriting is best-effort. You should still review important configuration files after migration, especially files that reference:

- WSL paths
- Windows paths
- Docker volume mounts
- local model paths
- local API keys or credentials
- system services
- shell scripts

## Safety Notes

- Export does not modify the source `.hermes` folder.
- Import may overwrite files in the target `.hermes` folder after creating a backup, if backup is enabled.
- The app validates ZIP extraction paths to reduce zip-slip risks.
- Secrets may be included if they exist inside your `.hermes` folder. Review the archive before sharing it publicly.
- Do not commit real tokens, API keys, OAuth files, or private memory files to GitHub.

## Files That May Need Manual Review

After importing, check these files if they exist:

```text
config.yaml
config.yml
.env
SOUL.md
MEMORY.md
skills/
cron/
auth.json
```

Also check any scripts or tool configs that call OS-specific commands such as:

```text
apt
systemctl
launchctl
powershell.exe
cmd.exe
wsl.exe
open
pbcopy
pbpaste
```

## Limitations

This tool does not convert the Hermes application itself. It migrates the portable `.hermes` data/config folder.

It does not automatically convert:

- Python virtual environments
- Node.js dependencies
- Docker images
- systemd services
- macOS LaunchAgents
- installed packages
- OS-specific shell commands
- expired or machine-bound authentication tokens

For best results, install Hermes cleanly on the target OS first, then import the migrated `.hermes` data.

## Development

Syntax check:

```bash
python3 -m py_compile hermes_migrator_gui_english.py
```

Run locally:

```bash
python3 hermes_migrator_gui_english.py
```

## License

MIT License. See `LICENSE` for details.
