#!/usr/bin/env bash
#
# run_debate.sh — Codex CLI를 호출해 phase plan에 대한 debate.md를 생성
#
# Usage: bash scripts/run_debate.sh <phase-num>
# Output: .claude/phases/phase-<N>/debate.md
#
set -euo pipefail

# -------- args --------
PHASE_NUM="${1:?usage: $0 <phase-num>}"
PHASE_DIR=".claude/phases/phase-${PHASE_NUM}"
PLAN_FILE="${PHASE_DIR}/plan.md"
OUT_FILE="${PHASE_DIR}/debate.md"
PROMPT_FILE="prompts/codex_debate.md"

# -------- prerequisite checks --------
command -v codex >/dev/null 2>&1 || {
  echo "ERROR: codex CLI not found. Install: npm install -g @openai/codex" >&2
  exit 1
}

[[ -f "ROADMAP.md" ]]      || { echo "ERROR: ROADMAP.md not found in $(pwd)" >&2; exit 1; }
[[ -f "${PROMPT_FILE}" ]]  || { echo "ERROR: ${PROMPT_FILE} not found" >&2; exit 1; }
[[ -f "${PLAN_FILE}" ]]    || { echo "ERROR: ${PLAN_FILE} not found — run Stage 1 first" >&2; exit 1; }

mkdir -p "${PHASE_DIR}"

# -------- assemble prompt --------
# Codex가 AGENTS.md를 자동 로드하므로 일반적인 컨벤션은 그쪽이 처리.
# 여기서는 task-specific 컨텍스트만 인라인.
PROMPT_TEXT=$(cat <<EOF
$(cat "${PROMPT_FILE}")

---

# Phase ${PHASE_NUM} — Plan to critique

The plan you are critiquing lives at: ${PLAN_FILE}

Read it yourself (you have read access) plus ROADMAP.md.
Now produce the debate document per the format above.
EOF
)

# -------- invoke codex --------
echo "[run_debate] invoking codex for phase ${PHASE_NUM}..." >&2

codex exec \
  --ask-for-approval never \
  --sandbox read-only \
  --ephemeral \
  --output-last-message "${OUT_FILE}" \
  "${PROMPT_TEXT}"

# -------- verify output --------
if [[ ! -s "${OUT_FILE}" ]]; then
  echo "ERROR: codex produced empty output at ${OUT_FILE}" >&2
  exit 1
fi

LINES=$(wc -l < "${OUT_FILE}")
echo "[run_debate] OK — wrote ${LINES} lines to ${OUT_FILE}" >&2
