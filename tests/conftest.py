from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NANOBOT_CORE = ROOT / "third_party" / "nanobot-core"

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

if str(NANOBOT_CORE) not in sys.path:
    sys.path.insert(0, str(NANOBOT_CORE))
