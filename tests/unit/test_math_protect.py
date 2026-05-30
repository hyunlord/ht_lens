"""Phase 8b — math placeholder protection unit tests.

Locks byte-identical round-trip, missing-placeholder detection, the
collision guard, and the known/intentional regex edges (debate §3/§5).
"""

from __future__ import annotations

from ht_lens.translate.math_protect import (
    has_math,
    protect_math,
    restore_math,
    source_has_placeholder_collision,
)


def _roundtrip(text: str) -> str:
    protected, store = protect_math(text)
    restored, missing = restore_math(protected, store)
    assert not missing
    return restored


def test_inline_protected_and_restored_byte_identical() -> None:
    src = "Pythagoras: $a^2 + b^2 = c^2$ holds."
    protected, store = protect_math(src)
    assert "$" not in protected and "⟦MATH0⟧" in protected
    assert store == ["$a^2 + b^2 = c^2$"]
    assert _roundtrip(src) == src


def test_display_protected_first() -> None:
    src = r"Before $$\sum_{k=1}^K z_k = 1$$ after."
    _, store = protect_math(src)
    assert store == [r"$$\sum_{k=1}^K z_k = 1$$"]
    assert _roundtrip(src) == src


def test_byte_identical_preserves_operatorname_and_textstyle() -> None:
    # The exact constructs the sandbox proved survive.
    src = r"$p(z) = \operatorname*{Dir}(z|\alpha)$ and $\textstyle\sum_k z_k$."
    assert _roundtrip(src) == src


def test_multiple_inline_and_display_mixed() -> None:
    src = r"$a$ text $$B$$ more $c_1$ end."
    protected, store = protect_math(src)
    assert len(store) == 3
    assert protected.count("⟦MATH") == 3
    assert _roundtrip(src) == src


def test_korean_text_with_math() -> None:
    src = "잠재 변수 $p(z)$ 를 사용하고 $$Z = WX$$ 로 둔다."
    assert _roundtrip(src) == src


def test_missing_placeholder_is_reported() -> None:
    _, store = protect_math("$x$ and $y$")
    # Simulate an LLM that dropped the second placeholder.
    restored, missing = restore_math("⟦MATH0⟧ and (gone)", store)
    assert missing == [1]
    assert "$x$" in restored  # the surviving one is restored


def test_single_currency_dollar_not_protected() -> None:
    # A lone $ (no closing) must not be treated as math.
    src = "It costs $5 today."
    protected, store = protect_math(src)
    assert store == []
    assert protected == src


def test_currency_pair_matches_but_roundtrip_is_safe() -> None:
    # "$5 to $10" matches as one run (known false positive) — but the
    # restore is byte-identical, so nothing is corrupted (debate §3).
    src = "Between $5 to $10 dollars."
    _, store = protect_math(src)
    assert len(store) == 1  # the run "$5 to $" was captured
    assert _roundtrip(src) == src  # byte-identical regardless


def test_escaped_dollar_roundtrip_safe() -> None:
    src = r"Math with escaped $x = \$5$ inside."
    # Whatever the regex captures, restoration is byte-identical.
    assert _roundtrip(src) == src


def test_source_placeholder_collision_detected() -> None:
    assert source_has_placeholder_collision("text with ⟦MATH0⟧ already")
    assert not source_has_placeholder_collision("normal text $x$")


def test_has_math() -> None:
    assert has_math("a $x$ b")
    assert has_math("$$D$$")
    assert not has_math("no math here")
    assert not has_math("lone $5 dollar")


def test_no_math_is_identity() -> None:
    src = "Plain Korean 본문, no formulas."
    protected, store = protect_math(src)
    assert protected == src and store == []
