from __future__ import annotations

import os
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parent
TMPDIR = ROOT / ".tmp-pytest-local"
TMPDIR.mkdir(exist_ok=True)

tempfile.tempdir = str(TMPDIR)
os.environ.setdefault("TMPDIR", str(TMPDIR))
os.environ.setdefault("TEMP", str(TMPDIR))
os.environ.setdefault("TMP", str(TMPDIR))

