#!/usr/bin/env bash
#
# verify_api.sh — Phase 3 end-to-end API scenario.
#
# Usage: bash scripts/verify_api.sh [BASE_URL]
#   default BASE_URL = http://127.0.0.1:8080
#
# Assumes:
#   * a server is already running at BASE_URL
#   * the DB at HT_LENS_DB_URL (or data/ht_lens.db) has at least one document
#     (doc_id=1) with at least one translated text block on page 1.
#
# Exits non-zero on the first failure.

set -euo pipefail

BASE="${1:-http://127.0.0.1:8080}"
need() {
  command -v "$1" >/dev/null 2>&1 || { echo "ERROR: $1 not installed" >&2; exit 1; }
}
need curl
need jq

echo "[1/7] GET /documents"
DOCS=$(curl -sf "${BASE}/documents")
COUNT=$(echo "${DOCS}" | jq 'length')
[[ "${COUNT}" -ge 1 ]] || { echo "FAIL: no documents"; exit 1; }
DOC_ID=$(echo "${DOCS}" | jq -r '.[0].id')
echo "    doc_id=${DOC_ID} count=${COUNT}"

echo "[2/7] GET /documents/${DOC_ID}/pages/1"
PAGE=$(curl -sf "${BASE}/documents/${DOC_ID}/pages/1")
PAGE_NUM=$(echo "${PAGE}" | jq -r '.page_num')
BLOCKS=$(echo "${PAGE}" | jq '.blocks | length')
[[ "${PAGE_NUM}" == "1" ]] || { echo "FAIL: page_num=${PAGE_NUM}"; exit 1; }
[[ "${BLOCKS}" -ge 1 ]] || { echo "FAIL: page has no blocks"; exit 1; }
echo "    blocks=${BLOCKS}"

# pick first text block
BLOCK_ID=$(echo "${PAGE}" | jq '[.blocks[] | select(.type=="text")][0].id')
[[ "${BLOCK_ID}" != "null" && -n "${BLOCK_ID}" ]] || {
  echo "FAIL: no text block on page 1"; exit 1; }
echo "    block_id=${BLOCK_ID}"

echo "[3/7] GET /documents/${DOC_ID}/pages/1/image"
TMP_PNG=$(mktemp --suffix=.png)
trap 'rm -f "${TMP_PNG}"' EXIT
HTTP_STATUS=$(curl -s -o "${TMP_PNG}" -w "%{http_code}" "${BASE}/documents/${DOC_ID}/pages/1/image")
[[ "${HTTP_STATUS}" == "200" ]] || { echo "FAIL: image status=${HTTP_STATUS}"; exit 1; }
# verify PNG magic
head -c8 "${TMP_PNG}" | xxd | grep -q '8950 4e47' || {
  echo "FAIL: response is not PNG"; exit 1; }
SIZE=$(wc -c <"${TMP_PNG}")
echo "    png bytes=${SIZE}"

echo "[4/7] POST /threads (block_id=${BLOCK_ID})"
THREAD=$(curl -sf -X POST "${BASE}/threads" \
  -H 'Content-Type: application/json' \
  -d "{\"block_id\": ${BLOCK_ID}}")
THREAD_ID=$(echo "${THREAD}" | jq -r '.id')
[[ -n "${THREAD_ID}" && "${THREAD_ID}" != "null" ]] || {
  echo "FAIL: thread create"; exit 1; }
echo "    thread_id=${THREAD_ID}"

echo "[5/7] POST /threads/${THREAD_ID}/explain"
EXPLAIN=$(curl -sf -X POST "${BASE}/threads/${THREAD_ID}/explain")
EXPLAIN_ROLE=$(echo "${EXPLAIN}" | jq -r '.role')
EXPLAIN_LEN=$(echo "${EXPLAIN}" | jq -r '.content | length')
[[ "${EXPLAIN_ROLE}" == "assistant" ]] || { echo "FAIL: explain role=${EXPLAIN_ROLE}"; exit 1; }
[[ "${EXPLAIN_LEN}" -gt 0 ]] || { echo "FAIL: explain empty"; exit 1; }
echo "    explain len=${EXPLAIN_LEN}"

echo "[6/7] POST /threads/${THREAD_ID}/messages"
FOLLOWUP=$(curl -sf -X POST "${BASE}/threads/${THREAD_ID}/messages" \
  -H 'Content-Type: application/json' \
  -d '{"content": "한 문장으로 더 짧게 요약해줘."}')
F_ROLE=$(echo "${FOLLOWUP}" | jq -r '.role')
F_LEN=$(echo "${FOLLOWUP}" | jq -r '.content | length')
[[ "${F_ROLE}" == "assistant" ]] || { echo "FAIL: followup role"; exit 1; }
[[ "${F_LEN}" -gt 0 ]] || { echo "FAIL: followup empty"; exit 1; }
echo "    followup len=${F_LEN}"

echo "[7/7] GET /threads/${THREAD_ID}"
DETAIL=$(curl -sf "${BASE}/threads/${THREAD_ID}")
MSG_COUNT=$(echo "${DETAIL}" | jq '.messages | length')
ROLES=$(echo "${DETAIL}" | jq -r '[.messages[].role] | join(",")')
[[ "${MSG_COUNT}" == "4" ]] || { echo "FAIL: msg count=${MSG_COUNT}"; exit 1; }
[[ "${ROLES}" == "user,assistant,user,assistant" ]] || {
  echo "FAIL: roles=${ROLES}"; exit 1; }
echo "    messages=${MSG_COUNT} roles=${ROLES}"

echo
echo "verify_api.sh OK"
