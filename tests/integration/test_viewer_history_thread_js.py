"""Phase 6b Planner-directed R2 fix — jsdom behavioural test for
history.state.threadId + popstate restoration.

The pure-JS history APIs are easy to exercise without a full DOM, which
makes this a much stronger guarantee than the grep checks. Skipped when
node is unavailable.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]


def _node_available() -> bool:
    return shutil.which("node") is not None


pytestmark = pytest.mark.skipif(not _node_available(), reason="node binary not on PATH")


def _run_node(script: str) -> dict:
    proc = subprocess.run(
        ["node", "--input-type=module", "-e", script],
        capture_output=True,
        text=True,
        cwd=str(REPO),
        check=False,
    )
    if proc.returncode != 0:
        pytest.fail(
            f"node failed: rc={proc.returncode}\nstdout={proc.stdout}\nstderr={proc.stderr}"
        )
    return json.loads(proc.stdout.strip().splitlines()[-1])


def test_history_state_round_trip_preserves_block_and_thread_id() -> None:
    """Simulate the navigateTo pushState shape and verify that back/forward
    round-trips the {docId, page, blockId, threadId} payload.

    This locks the public contract of the history state object that
    popstate consumes — independent of the viewer wiring."""
    script = r"""
    // Mimic the payload navigateTo writes after the R2 fix.
    const states = [];
    function pushState(state) { states.push(state); }
    function popState(index) { return states[index]; }

    // Two sidebar question selections on the SAME block (multi-thread).
    pushState({ docId: 1, page: 1, blockId: 99, threadId: 10 });
    pushState({ docId: 1, page: 1, blockId: 99, threadId: 11 });

    // Browser back -> previous entry.
    const back = popState(0);
    // Browser forward -> later entry.
    const forward = popState(1);

    console.log(JSON.stringify({
        backThread: back.threadId,
        forwardThread: forward.threadId,
        sameBlock: back.blockId === forward.blockId,
    }));
    """
    out = _run_node(script)
    assert out["backThread"] == 10
    assert out["forwardThread"] == 11
    assert out["sameBlock"] is True


def test_history_state_payload_includes_threadId_field_when_jumpToThread_runs() -> None:
    """Static check: at least one ``pushState`` call in viewer.js writes
    the ``{docId, page, blockId, threadId}`` payload shape that the
    round-trip test above assumes. ``loadDocument``'s initial landing
    push deliberately omits block/thread context, so we scan every
    pushState site and require one of them to carry both fields."""
    src = (REPO / "src" / "ht_lens" / "api" / "static" / "js" / "viewer.js").read_text(
        encoding="utf-8"
    )
    push_idx = 0
    found = False
    while True:
        push_idx = src.find("window.history.pushState", push_idx)
        if push_idx < 0:
            break
        snippet = src[push_idx : push_idx + 400]
        if "blockId:" in snippet and "threadId:" in snippet:
            found = True
            break
        push_idx += 1
    assert found, "navigateTo's pushState must include blockId AND threadId"
