"""``python -m ht_lens.extract <pdf> -o <out_dir>`` entry point.

Injects the ``extract`` subcommand so users can call this module without
typing the subcommand name.
"""

from __future__ import annotations

import sys

from ht_lens.cli import main

if __name__ == "__main__":
    raise SystemExit(main(["extract", *sys.argv[1:]]))
