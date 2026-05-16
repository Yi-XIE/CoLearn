"""Small local development utilities for the CoLearn workspace."""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path
from typing import Iterable


DEFAULT_RESET_PATHS = [
    ".colearn/state",
    ".colearn/test-state",
    ".colearn/pytest-cache",
    "web/test-results",
    "web/playwright-report",
]


def workspace_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _resolve_targets(
    *,
    root: Path,
    include_env: bool,
) -> list[Path]:
    targets = [root / relative for relative in DEFAULT_RESET_PATHS]
    if include_env:
        targets.append(root / ".env")
    return [target.resolve() for target in targets]


def _ensure_within_workspace(*, root: Path, target: Path) -> None:
    resolved_root = root.resolve()
    resolved_target = target.resolve()
    try:
        resolved_target.relative_to(resolved_root)
    except ValueError as exc:
        raise ValueError(f"Refusing to touch path outside workspace: {resolved_target}") from exc


def _format_targets(targets: Iterable[Path], *, root: Path) -> list[str]:
    lines: list[str] = []
    for target in targets:
        _ensure_within_workspace(root=root, target=target)
        relative = target.resolve().relative_to(root.resolve())
        lines.append(str(relative).replace("\\", "/"))
    return lines


def reset_state(
    *,
    root: Path | None = None,
    include_env: bool = False,
    dry_run: bool = False,
) -> list[str]:
    resolved_root = (root or workspace_root()).resolve()
    targets = _resolve_targets(root=resolved_root, include_env=include_env)
    formatted = _format_targets(targets, root=resolved_root)
    if dry_run:
        return formatted
    for target in targets:
        _ensure_within_workspace(root=resolved_root, target=target)
        if target.is_dir():
            shutil.rmtree(target, ignore_errors=True)
        elif target.exists():
            target.unlink()
    return formatted


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Local development helpers for CoLearn.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    reset_parser = subparsers.add_parser("reset-state", help="Remove local state and test artifacts.")
    reset_parser.add_argument("--dry-run", action="store_true", help="List targets without deleting them.")
    reset_parser.add_argument(
        "--include-env",
        action="store_true",
        help="Also remove the workspace .env file.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command != "reset-state":
        parser.error(f"Unsupported command: {args.command}")
    targets = reset_state(
        include_env=bool(args.include_env),
        dry_run=bool(args.dry_run),
    )
    action = "Would remove" if args.dry_run else "Removed"
    print(action)
    for target in targets:
        print(f"- {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
