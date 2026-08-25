#!/usr/bin/env python3
"""Compatibility alias for capture emission; no command or exit status is replayed."""

from __future__ import annotations

try:
    from .emit_kimi_capture import main
except ImportError:  # direct ``python scripts/replay_kimi_evidence.py`` execution
    from emit_kimi_capture import main  # type: ignore[no-redef]


if __name__ == "__main__":
    raise SystemExit(main())
