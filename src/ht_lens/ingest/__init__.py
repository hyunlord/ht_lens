"""Phase 2a ingest pipeline — extract_dir → SQLite rows."""

from ht_lens.ingest.pipeline import IngestStats, ingest_extract_dir

__all__ = ["IngestStats", "ingest_extract_dir"]
