"""Phase 6a — /documents/{id}/export.md endpoint tests."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from ht_lens.db.models import Message, Thread
from ht_lens.db.session import make_engine, make_session_factory

from ._api_helpers import make_test_client, seed_minimal_document


async def _add_thread_with_messages(
    factory, block_id: int, title: str, messages: list[tuple[str, str]]
) -> int:
    async with factory() as session:
        thread = Thread(
            block_id=block_id,
            title=title,
            created_at=datetime.utcnow(),
        )
        session.add(thread)
        await session.flush()
        for role, content in messages:
            session.add(
                Message(
                    thread_id=thread.id,
                    role=role,
                    content=content,
                    model="mock" if role == "assistant" else None,
                    created_at=datetime.utcnow(),
                )
            )
        await session.commit()
        return thread.id


@pytest.mark.asyncio
async def test_export_returns_404_for_unknown_doc(api_db_path: Path) -> None:
    with make_test_client(api_db_path) as client:
        resp = client.get("/documents/9999/export.md")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_export_header_only_when_no_threads(api_db_path: Path, tmp_path: Path) -> None:
    engine = make_engine(api_db_path)
    factory = make_session_factory(engine)
    async with factory() as session:
        seeded = await seed_minimal_document(session, tmp_dir=tmp_path)
    await engine.dispose()

    with make_test_client(api_db_path) as client:
        resp = client.get(f"/documents/{seeded.doc_id}/export.md")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/markdown")
    assert "sample.pdf" in resp.text
    assert "질문 수: 0" in resp.text


@pytest.mark.asyncio
async def test_export_includes_thread_messages_in_page_order(
    api_db_path: Path, tmp_path: Path
) -> None:
    engine = make_engine(api_db_path)
    factory = make_session_factory(engine)
    async with factory() as session:
        seeded = await seed_minimal_document(
            session, tmp_dir=tmp_path, blocks_per_page=2, num_pages=2
        )
    await engine.dispose()

    # Two threads on different pages — order should follow page_num.
    await _add_thread_with_messages(
        factory,
        seeded.block_ids[2],  # page 2 block
        "Q on page 2",
        [("user", "p2 q"), ("assistant", "p2 a")],
    )
    await _add_thread_with_messages(
        factory,
        seeded.block_ids[0],  # page 1 block
        "Q on page 1",
        [("user", "p1 q"), ("assistant", "p1 a")],
    )

    with make_test_client(api_db_path) as client:
        resp = client.get(f"/documents/{seeded.doc_id}/export.md")
    text = resp.text
    p1_idx = text.find("Q on page 1")
    p2_idx = text.find("Q on page 2")
    assert p1_idx >= 0 and p2_idx >= 0
    assert p1_idx < p2_idx
    assert "질문 수: 2" in text


@pytest.mark.asyncio
async def test_export_excludes_empty_threads(api_db_path: Path, tmp_path: Path) -> None:
    engine = make_engine(api_db_path)
    factory = make_session_factory(engine)
    async with factory() as session:
        seeded = await seed_minimal_document(session, tmp_dir=tmp_path)
    await engine.dispose()
    # One thread WITHOUT messages (empty)
    await _add_thread_with_messages(factory, seeded.block_ids[0], "Empty thread", [])
    await _add_thread_with_messages(
        factory, seeded.block_ids[1], "Real thread", [("user", "hi"), ("assistant", "hello")]
    )

    with make_test_client(api_db_path) as client:
        resp = client.get(f"/documents/{seeded.doc_id}/export.md")
    text = resp.text
    assert "Real thread" in text
    assert "Empty thread" not in text
    assert "질문 수: 1" in text


@pytest.mark.asyncio
async def test_export_blockquotes_assistant_markdown(api_db_path: Path, tmp_path: Path) -> None:
    """Phase 6a debate §5: an assistant message containing markdown
    (headings, fenced code blocks, raw HTML) must not break the outer
    structure. Every content line is prefixed with ``> ``."""
    engine = make_engine(api_db_path)
    factory = make_session_factory(engine)
    async with factory() as session:
        seeded = await seed_minimal_document(session, tmp_dir=tmp_path)
    await engine.dispose()

    rich = "# 큰 제목\n\n- 항목 1\n- 항목 2\n\n```python\nprint('inside fence')\n```\n"
    await _add_thread_with_messages(
        factory,
        seeded.block_ids[0],
        "Rich content",
        [("user", "explain"), ("assistant", rich)],
    )

    with make_test_client(api_db_path) as client:
        resp = client.get(f"/documents/{seeded.doc_id}/export.md")
    text = resp.text
    # Locate the assistant body.
    body_idx = text.index("**AI**")
    body_section = text[body_idx:]
    # Every non-empty line of the assistant content must start with "> ".
    for line in ["# 큰 제목", "- 항목 1", "```python", "print('inside fence')"]:
        # The literal occurrence inside the export must appear with the
        # blockquote prefix.
        assert f"> {line}" in body_section, f"missing quoted line: {line}"


@pytest.mark.asyncio
async def test_export_handles_multiline_block_text(api_db_path: Path, tmp_path: Path) -> None:
    """Multi-line ``original_text`` must be quoted properly so the outer
    structure stays intact."""
    engine = make_engine(api_db_path)
    factory = make_session_factory(engine)
    async with factory() as session:
        seeded = await seed_minimal_document(session, tmp_dir=tmp_path)
        # Patch original_text to have multiple lines via direct SQL update.
        from ht_lens.db.models import Block

        await session.execute(
            Block.__table__.update()
            .where(Block.id == seeded.block_ids[0])
            .values(original_text="첫째 줄\n둘째 줄\n셋째 줄")
        )
        await session.commit()
    await engine.dispose()

    await _add_thread_with_messages(
        factory, seeded.block_ids[0], "Multi line", [("user", "q"), ("assistant", "a")]
    )

    with make_test_client(api_db_path) as client:
        resp = client.get(f"/documents/{seeded.doc_id}/export.md")
    text = resp.text
    # Truncation may apply; we only need the first line to be present and
    # safely contained inside the > 원문 blockquote line.
    assert "> 원문: 첫째 줄" in text
