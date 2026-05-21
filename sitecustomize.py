from __future__ import annotations

import os
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parent
TMPDIR = ROOT / ".colearn" / "tmp"
TMPDIR.mkdir(parents=True, exist_ok=True)

tempfile.tempdir = str(TMPDIR)
os.environ.setdefault("TMPDIR", str(TMPDIR))
os.environ.setdefault("TEMP", str(TMPDIR))
os.environ.setdefault("TMP", str(TMPDIR))
