"""Windows compatibility tests.

Added in the windows-compat sweep. mu2edaq-dataformat-viewer is a PyQt6 GUI with
no prior pytest suite. This locks in:
  * the config module imports and loads on Windows,
  * the source keeps `from __future__ import annotations` so the 3.9 floor holds
    with PEP 604-style hints (the phase-1 AL9 fix), and
  * the control-room scripts ship PowerShell ports.
"""
import pathlib
import shutil
import subprocess
import sys

import pytest

REPO = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

PWSH = shutil.which("pwsh") or shutil.which("powershell")

SCRIPT_STEMS = [
    "bootstrap",
    "start-mu2edaq-dataformat-viewer",
    "stop-mu2edaq-dataformat-viewer",
]


def test_config_imports_and_loads():
    from config import config
    # load() with no path returns a dict of defaults; must not raise on Windows.
    result = config.load()
    assert isinstance(result, dict)


@pytest.mark.parametrize("name", [
    "config/config.py",
    "mu2edaq-dataformat-sender.py",
    "mu2edaq-dataformat-viewer.py",
])
def test_future_annotations_present(name):
    # Keeps the Python 3.9 floor working with modern type hints (phase-1 fix).
    text = (REPO / name).read_text(encoding="utf-8")
    assert "from __future__ import annotations" in text


def test_scripts_have_both_forms():
    for stem in SCRIPT_STEMS:
        assert (REPO / f"{stem}.sh").is_file(), f"missing bash script: {stem}.sh"
        assert (REPO / f"{stem}.ps1").is_file(), f"missing PowerShell port: {stem}.ps1"


@pytest.mark.skipif(not PWSH, reason="PowerShell not available")
@pytest.mark.parametrize("stem", SCRIPT_STEMS)
def test_powershell_scripts_parse(stem):
    path = (REPO / f"{stem}.ps1").as_posix()
    code = (
        "$e=$null;"
        f"[System.Management.Automation.Language.Parser]::ParseFile('{path}',[ref]$null,[ref]$e)|Out-Null;"
        "if($e){$e|ForEach-Object{Write-Error $_};exit 1}else{exit 0}"
    )
    result = subprocess.run(
        [PWSH, "-NoProfile", "-NonInteractive", "-Command", code],
        capture_output=True, text=True, timeout=60,
    )
    assert result.returncode == 0, result.stderr
