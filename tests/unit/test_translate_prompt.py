"""Phase 6f-5 — translate system prompt branch tests.

Locks in the v2_ko Korean-instruction prompt for en→ko, the generic
English prompt for all other language pairs, and the lang-code
normalization (Codex debate §2) so casing/whitespace differences do
not silently disable the Korean branch.
"""

from __future__ import annotations

from ht_lens.llm.openai_compat import OpenAICompatibleClient


def _prompt(src: str, tgt: str) -> str:
    return OpenAICompatibleClient._translate_system(src, tgt)


def _korean_ratio(text: str) -> float:
    ko = sum(1 for c in text if "가" <= c <= "힣")
    en = sum(1 for c in text if c.isascii() and c.isalpha())
    total = ko + en
    return ko / total if total > 0 else 0.0


# ---------------------------------------------------------------------------
# en → ko branch (v2_ko Korean-instruction prompt)
# ---------------------------------------------------------------------------


def test_en_to_ko_returns_korean_instruction_prompt() -> None:
    """en→ko must use the v2_ko Korean-instruction prompt that A/B
    measurement validated against the prior generic English prompt."""
    p = _prompt("en", "ko")
    assert "한국어로 번역" in p, "missing Korean translate instruction"
    assert "기술 용어" in p, "missing technical-term rule"
    # 영어로 보존해야 하는 항목들 (rule §3) 명시
    assert "고유명사" in p, "missing proper-noun keep rule"
    assert "수식" in p, "missing math keep rule"
    assert "URL" in p, "missing URL keep rule"
    assert "arXiv" in p, "missing arXiv keep rule"
    # 출력 통제
    assert "번역문만 출력" in p, "missing output-only rule"


def test_en_to_ko_prompt_has_no_qwen_era_english_signature() -> None:
    """The legacy generic English prompt MUST NOT appear in the
    en→ko branch. Catches accidental revert (e.g., copy-paste of the
    old prompt back into the if-arm)."""
    p = _prompt("en", "ko")
    forbidden = [
        "You translate",
        "Output only the translation",
        "Preserve technical terms",
        "Do not add explanations",
    ]
    for f in forbidden:
        assert f not in p, f"v2_ko prompt must not contain legacy English signature: {f!r}"


def test_en_to_ko_prompt_is_majority_korean() -> None:
    """The prompt itself is in Korean (A/B showed Korean instructions
    outperform English instructions on Gemma 4: 0.671 → 0.755). Lock
    a floor on Korean character ratio so a partial re-translation of
    the prompt back to English would fail this test."""
    p = _prompt("en", "ko")
    ratio = _korean_ratio(p)
    assert ratio > 0.6, f"Korean character ratio too low: {ratio:.2f}"


# ---------------------------------------------------------------------------
# Other directions — generic English prompt preserved
# ---------------------------------------------------------------------------


def test_ko_to_en_uses_generic_english_prompt() -> None:
    """Reverse direction must NOT use the Korean-instruction prompt.
    The generic English prompt is the documented backward-compat path
    for non-Korean targets (challenge §1)."""
    p = _prompt("ko", "en")
    assert "한국어로 번역" not in p, "Korean prompt must not leak to ko→en path"
    assert "You translate" in p, "ko→en must use the generic English prompt"
    assert "Output only the translation" in p


def test_en_to_ja_uses_generic_english_prompt() -> None:
    """A third language (Japanese) hits the same else-branch."""
    p = _prompt("en", "ja")
    assert "한국어로 번역" not in p
    assert "You translate English to Japanese" in p


def test_generic_branch_also_normalizes_lang_codes() -> None:
    """Phase 6f-5 R2 fix (Codex verify-cross R1 §4): the else-branch
    must use the normalized lang codes too, otherwise sloppy input
    like ``" KO "`` / ``"EN"`` for a ko→en doc renders as
    ``You translate  KO  to EN.`` with stray spaces and ALL-CAPS that
    bypass the ``_LANG_NAMES`` lookup."""
    p = _prompt(" KO ", "EN ")
    # Must NOT contain the raw, un-normalized fragment.
    assert "  KO  " not in p, f"raw whitespace leaked: {p!r}"
    assert "EN " not in p
    # Must contain the normalized lookup result.
    assert "You translate Korean to English" in p, (
        f"normalized lang names not used in generic branch: {p!r}"
    )


# ---------------------------------------------------------------------------
# Lang-code normalization (Codex debate §2)
# ---------------------------------------------------------------------------


def test_uppercase_lang_codes_hit_korean_branch() -> None:
    """``"EN"`` / ``"KO"`` (uppercase) must still trigger the v2_ko
    Korean-instruction prompt — Codex flagged that the original branch
    silently bypassed because the static method did no normalization.
    """
    p = _prompt("EN", "KO")
    assert "한국어로 번역" in p


def test_whitespace_lang_codes_hit_korean_branch() -> None:
    """Surrounding whitespace is stripped, so `" en "` and `"ko "`
    still match. Common when env vars are accidentally quoted with
    trailing newlines."""
    p = _prompt(" en ", "ko\n")
    assert "한국어로 번역" in p


def test_mixed_case_lang_codes_hit_korean_branch() -> None:
    """``"En"`` / ``"Ko"`` — title case from some loaders."""
    p = _prompt("En", "Ko")
    assert "한국어로 번역" in p


def test_empty_or_none_lang_codes_fall_through_to_generic() -> None:
    """Defensive: empty / None lang codes must NOT crash and must fall
    through to the generic prompt (no spurious Korean prompt for an
    unknown pair)."""
    # Empty string
    p = _prompt("", "ko")
    assert "한국어로 번역" not in p
    # None is technically out of type but worth defensive coverage
    # since the static method coerces ``src or ""``.
    p2 = _prompt(None, "ko")  # type: ignore[arg-type]
    assert "한국어로 번역" not in p2


# ---------------------------------------------------------------------------
# Phase 8e-1 — math placeholder-preservation rule (R-B)
# ---------------------------------------------------------------------------


def test_en_to_ko_prompt_has_placeholder_preservation_rule() -> None:
    """8e-1 R-B: live qwen mangled/hallucinated over the ⟦⟧ sentinel. The
    en→ko prompt now instructs the model to copy ``[[MATHn]]`` tokens verbatim
    and emit no LaTeX in their place — the difference-maker that recovered the
    6 doc7 failures (chunk 67: 0/6 → 6/6 with this rule + the ASCII sentinel)."""
    p = _prompt("en", "ko")
    assert "[[MATH" in p, "missing placeholder-preservation rule (en→ko)"
    assert "그대로 복사" in p


def test_generic_prompt_has_placeholder_preservation_rule() -> None:
    """The generic branch carries the same rule (English wording)."""
    p = _prompt("ko", "en")
    assert "[[MATHn]]" in p
    assert "verbatim" in p.lower()


# ---------------------------------------------------------------------------
# Cache-key invariance under prompt change (Phase 6f-5 policy lock)
# ---------------------------------------------------------------------------


def test_cache_key_does_not_include_system_prompt() -> None:
    """Phase 6f-5 policy: changing the translate system prompt does NOT
    invalidate existing translation cache rows. ``cache_key()`` keys on
    ``(text, src, tgt, model)`` — the prompt is intentionally not in
    that tuple. This is the cement for the user-acknowledged decision
    "기존 번역 보존 (자동 invalidate 안 함)" (challenge §2, debate cache
    critique). If a future phase ships prompt-versioned cache, this
    test must be updated together.
    """
    from ht_lens.translate.cache import cache_key

    text = "Machine learning is a subfield of AI."
    k_qwen_v1 = cache_key(text, "en", "ko", "qwen3.6-27b")
    k_qwen_v2 = cache_key(text, "en", "ko", "qwen3.6-27b")
    assert k_qwen_v1 == k_qwen_v2, (
        "cache_key must be deterministic for the same (text, src, tgt, model). "
        "Phase 6f-5 prompt change should NOT cause a cache miss."
    )
    # Different model name → different key (preserved Phase 6e invariant).
    k_gemma = cache_key(text, "en", "ko", "gemma-4-26b-a4b-it")
    assert k_qwen_v1 != k_gemma, (
        "different model names must produce different cache keys (the "
        "documented isolation between providers)"
    )
