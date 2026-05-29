"""MinerU extraction wrapper (ht_lens 2.0, Phase 8a).

MinerU is invoked as an **external subprocess tool**, not imported as a
library — this keeps torch/paddle out of the ht_lens core dependency tree
(extraction is a one-time batch). See ``runner.py``.
"""
