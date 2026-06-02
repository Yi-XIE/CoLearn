"""Pytest configuration: expose vendored NanoBot snapshot to tests."""
import sys
from pathlib import Path

NANOBOT_SNAPSHOT = Path(__file__).resolve().parents[1] / "third_party" / "nanobot-0.2.1"
if NANOBOT_SNAPSHOT.exists() and str(NANOBOT_SNAPSHOT) not in sys.path:
    sys.path.insert(0, str(NANOBOT_SNAPSHOT))
