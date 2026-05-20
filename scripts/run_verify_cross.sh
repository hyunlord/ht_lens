#!/usr/bin/env bash
#
# run_verify_cross.sh — Codex CLI를 호출해 phase verify에 대한 cross-check를 생성
#
# Usage: bash scripts/run_verify_cross.sh <phase-num>
# Output: .claude/phases/phase-<N>/verify-cross.md
#
set -euo pipefail

# -------- args --------
PHASE_NUM="${1:?usage: $0 <phase-num>}"
PHASE_DIR=".claude/phases/phase-${PHASE_NUM}"
VERIFY_FILE="${PHASE_DIR}/verify.md"
OUT_FILE="${PHASE_DIR}/verify-cross.md"
PROMPT_FILE="prompts/codex_verify.md"

# -------- prerequisite checks --------
command -v codex >/dev/null 2>&1 || {
  echo "ERROR: codex CLI not found. Install: npm install -g @openai/codex" >&2
  exit 1
}

[[ -f "ROADMAP.md" ]]       || { echo "ERROR: ROADMAP.md not found in $(pwd)" >&2; exit 1; }
[[ -f "${PROMPT_FILE}" ]]   || { echo "ERROR: ${PROMPT_FILE} not found" >&2; exit 1; }
[[ -f "${VERIFY_FILE}" ]]   || { echo "ERROR: ${VERIFY_FILE} not found — run Stage 5a first" >&2; exit 1; }

mkdir -p "${PHASE_DIR}"

# -------- gather git context --------
# git log/diff은 verify cross-check에 중요한 evidence
GIT_LOG=$(git log --oneline -n 50 2>/dev/null || echo "(git history unavailable)")
GIT_STAT=$(git diff --stat HEAD~10..HEAD 2>/dev/null || echo "(git diff unavailable)")

# -------- assemble prompt --------
PROMPT_TEXT=$(cat <<EOF
$(cat "${PROMPT_FILE}")

---

# Phase ${PHASE_NUM} — Verify to cross-check

Files to read yourself:
- ${VERIFY_FILE} (the self-verify report you are auditing)
- ${PHASE_DIR}/plan.md (the plan from Stage 1)
- ${PHASE_DIR}/debate.md (the debate you produced earlier — does verify address those points?)
- ROADMAP.md (the DoD)
- Actual source under src/ (inspect what was built)

# Recent git log (last 50 commits)
\`\`\`
${GIT_LOG}
\`\`\`

# Recent diff stat (last 10 commits)
\`\`\`
${GIT_STAT}
\`\`\`

Now produce the cross-verify document per the format above.
EOF
)

# -------- invoke codex --------
echo "[run_verify_cross] invoking codex for phase ${PHASE_NUM}..." >&2

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
echo "[run_verify_cross] OK — wrote ${LINES} lines to ${OUT_FILE}" >&2

# Verdict 추출 (참고용)
if grep -qE "^(CONFIRM_PASS|DOWNGRADE|REJECT)" "${OUT_FILE}"; then
  VERDICT=$(grep -oE "(CONFIRM_PASS|DOWNGRADE|REJECT)" "${OUT_FILE}" | head -1)
  echo "[run_verify_cross] verdict: ${VERDICT}" >&2
fi
