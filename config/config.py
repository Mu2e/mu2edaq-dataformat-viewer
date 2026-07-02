"""
Mu2e viewer/sender configuration loader.

Config files are YAML.  The loader merges user values on top of
the built-in defaults, so only the keys you care about need to be
specified.  Relative paths inside the config file are resolved
relative to the directory that contains the config file itself.
"""

from __future__ import annotations

import copy
import os
from pathlib import Path

try:
    import yaml
except ImportError:
    raise ImportError("PyYAML is required.  Install with:  pip install pyyaml")

# ── Built-in defaults ──────────────────────────────────────────────────────

DEFAULTS: dict = {
    # Directory that contains the packet-format *.yaml files.
    "formats_dir": ".",

    # Name of the format to select on startup (must match a format name
    # exactly, e.g. "Heartbeat Packet").  Empty string → first in list.
    "default_format": "",

    # Viewer-specific settings
    "viewer": {
        "port": 7755,           # TCP port the viewer listens on
    },

    # Sender-specific settings
    "sender": {
        "host": "localhost",    # Default destination host
        "port": 7755,           # Default destination port
    },

    # Appearance
    "font_size": 11,            # Base font size in points (7–24)
    "qt_style":  "Fusion",      # Qt style name: Fusion, Windows, macOS, …
}

# Config file names searched in each candidate directory
_SEARCH_NAMES = ("mu2e-viewer.yaml", "config.yaml")

# Directories searched (relative to cwd) when no explicit path is given,
# in priority order: current directory first, then ./config/
_SEARCH_DIRS = (Path("."), Path("config"))


# ── Public API ─────────────────────────────────────────────────────────────

def load(config_path: str | None = None, script_dir: str | None = None) -> dict:
    """
    Load and return a configuration dict.

    *config_path*
        Path to a YAML config file.  If *None*, the loader searches the
        following locations in order until a file is found:
          1. ./<name>          (current working directory)
          2. ./config/<name>   (config sub-directory of cwd)
        where <name> is tried as ``mu2e-viewer.yaml`` then ``config.yaml``.

    *script_dir*
        Fallback base directory used to resolve a relative ``formats_dir``
        when no config file is found.  Defaults to the directory that
        contains this module.
    """
    if script_dir is None:
        script_dir = os.path.dirname(os.path.abspath(__file__))

    cfg = copy.deepcopy(DEFAULTS)

    # Locate config file
    resolved_path: Path | None = None
    if config_path:
        resolved_path = Path(config_path)
        if not resolved_path.exists():
            raise FileNotFoundError(f"Config file not found: {config_path}")
    else:
        for search_dir in _SEARCH_DIRS:
            for name in _SEARCH_NAMES:
                candidate = search_dir / name
                if candidate.exists():
                    resolved_path = candidate
                    break
            if resolved_path:
                break

    # Load and merge user values
    if resolved_path:
        with open(resolved_path) as fh:
            user_cfg = yaml.safe_load(fh)
        if isinstance(user_cfg, dict):
            _deep_merge(cfg, user_cfg)
        config_dir = resolved_path.parent
    else:
        config_dir = Path(script_dir)

    # Resolve formats_dir relative to the config file (or script dir)
    fd = Path(cfg["formats_dir"])
    if not fd.is_absolute():
        cfg["formats_dir"] = str((config_dir / fd).resolve())

    # Control-room port override: CRS_PORT_LISTEN (exported by crs-app from
    # apps.yaml) takes precedence over the viewer listen port in the config.
    crs_listen = os.environ.get("CRS_PORT_LISTEN")
    if crs_listen:
        cfg["viewer"]["port"] = int(crs_listen)

    return cfg


def save_defaults(path: str) -> None:
    """Write a fully-commented default config file to *path*."""
    content = """\
# Mu2e Data Format Viewer / Sender — configuration file
# All settings are optional; omitted keys use built-in defaults.

# Directory containing the packet-format *.yaml files.
# Relative paths are resolved relative to this config file.
formats_dir: "."

# Packet format selected on startup.
# Must match a format name exactly (e.g. "Heartbeat Packet").
# Leave empty to select the first format alphabetically.
default_format: ""

# ── Viewer settings ───────────────────────────────────────────────────────
viewer:
  port: 7755          # TCP port the viewer listens on for incoming data

# ── Sender settings ───────────────────────────────────────────────────────
sender:
  host: localhost     # Default destination host
  port: 7755          # Default destination port

# ── Appearance ────────────────────────────────────────────────────────────
font_size: 11         # Base font size in points (range 7–24)
qt_style:  Fusion     # Qt style: Fusion | Windows | macOS
"""
    with open(path, "w") as fh:
        fh.write(content)


# ── Internal helpers ───────────────────────────────────────────────────────

def _deep_merge(base: dict, override: dict) -> None:
    """Recursively merge *override* into *base* in place."""
    for key, val in override.items():
        if key in base and isinstance(base[key], dict) and isinstance(val, dict):
            _deep_merge(base[key], val)
        else:
            base[key] = val
