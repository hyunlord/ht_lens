"""Module entry point: ``python -m ht_lens.ingest``.

Delegates to the unified ``ht-lens`` typer app to keep argv handling identical
to the installed console script.
"""

from __future__ import annotations

import sys

from ht_lens.cli import app


def main() -> None:
    # Inject "ingest" so users can call `python -m ht_lens.ingest <dir>` without
    # also typing the subcommand. The unified ``ht-lens`` script still requires
    # the subcommand explicitly.
    argv = sys.argv[1:]
    if not argv or argv[0].startswith("-") or argv[0] != "ingest":
        argv = ["ingest", *argv]
    app(argv, standalone_mode=True)


if __name__ == "__main__":
    main()
