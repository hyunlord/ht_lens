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
#     with at least one ``text`` block on any page (not just page 1).
#
# Exits non-zero on the first failure.

set -euo pipefail

BASE="${1:-http://127.0.0.1:8080}"
need() {
  command -v "$1" >/dev/null 2>&1 || { echo "ERROR: $1 not installed" >&2; exit 1; }
}
need curl
need jq

echo "[1/9] GET /documents"
DOCS=$(curl -sf "${BASE}/documents")
COUNT=$(echo "${DOCS}" | jq 'length')
[[ "${COUNT}" -ge 1 ]] || { echo "FAIL: no documents"; exit 1; }
DOC_ID=$(echo "${DOCS}" | jq -r '.[0].id')
echo "    doc_id=${DOC_ID} count=${COUNT}"

echo "[2/9] GET /documents/${DOC_ID}"
DOC=$(curl -sf "${BASE}/documents/${DOC_ID}")
NUM_PAGES=$(echo "${DOC}" | jq -r '.num_pages')
[[ "${NUM_PAGES}" -ge 1 ]] || { echo "FAIL: num_pages=${NUM_PAGES}"; exit 1; }
echo "    num_pages=${NUM_PAGES}"

# Scan all pages for the first 'text' block. The DoD does not require page 1
# to be text-only; an image-only cover page is still a valid document.
echo "[3/9] scan pages for a text block"
BLOCK_ID=""
TEXT_PAGE=""
for ((p=1; p<=NUM_PAGES; p++)); do
  PAGE=$(curl -sf "${BASE}/documents/${DOC_ID}/pages/${p}")
  CANDIDATE=$(echo "${PAGE}" | jq '[.blocks[] | select(.type=="text")][0].id // empty')
  if [[ -n "${CANDIDATE}" ]]; then
    BLOCK_ID="${CANDIDATE}"
    TEXT_PAGE="${p}"
    break
  fi
done
[[ -n "${BLOCK_ID}" ]] || { echo "FAIL: no text block in any page"; exit 1; }
echo "    block_id=${BLOCK_ID} page=${TEXT_PAGE}"

echo "[4/9] GET /documents/${DOC_ID}/pages/${TEXT_PAGE}"
PAGE=$(curl -sf "${BASE}/documents/${DOC_ID}/pages/${TEXT_PAGE}")
PAGE_NUM=$(echo "${PAGE}" | jq -r '.page_num')
BLOCKS=$(echo "${PAGE}" | jq '.blocks | length')
[[ "${PAGE_NUM}" == "${TEXT_PAGE}" ]] || { echo "FAIL: page_num=${PAGE_NUM}"; exit 1; }
[[ "${BLOCKS}" -ge 1 ]] || { echo "FAIL: empty page"; exit 1; }
echo "    blocks=${BLOCKS}"

echo "[5/9] GET /documents/${DOC_ID}/pages/${TEXT_PAGE}/image"
TMP_PNG=$(mktemp --suffix=.png)
trap 'rm -f "${TMP_PNG}"' EXIT
HTTP_STATUS=$(curl -s -o "${TMP_PNG}" -w "%{http_code}" \
  "${BASE}/documents/${DOC_ID}/pages/${TEXT_PAGE}/image")
[[ "${HTTP_STATUS}" == "200" ]] || { echo "FAIL: image status=${HTTP_STATUS}"; exit 1; }
head -c8 "${TMP_PNG}" | xxd | grep -q '8950 4e47' || {
  echo "FAIL: response is not PNG"; exit 1; }
SIZE=$(wc -c <"${TMP_PNG}")
echo "    png bytes=${SIZE}"

echo "[6/9] POST /threads (block_id=${BLOCK_ID})"
THREAD=$(curl -sf -X POST "${BASE}/threads" \
  -H 'Content-Type: application/json' \
  -d "{\"block_id\": ${BLOCK_ID}}")
THREAD_ID=$(echo "${THREAD}" | jq -r '.id')
[[ -n "${THREAD_ID}" && "${THREAD_ID}" != "null" ]] || {
  echo "FAIL: thread create"; exit 1; }
echo "    thread_id=${THREAD_ID}"

echo "[7/9] POST /threads/${THREAD_ID}/explain"
EXPLAIN=$(curl -sf -X POST "${BASE}/threads/${THREAD_ID}/explain")
EXPLAIN_ROLE=$(echo "${EXPLAIN}" | jq -r '.role')
EXPLAIN_LEN=$(echo "${EXPLAIN}" | jq -r '.content | length')
[[ "${EXPLAIN_ROLE}" == "assistant" ]] || { echo "FAIL: explain role=${EXPLAIN_ROLE}"; exit 1; }
[[ "${EXPLAIN_LEN}" -gt 0 ]] || { echo "FAIL: explain empty"; exit 1; }
echo "    explain len=${EXPLAIN_LEN}"

echo "[8/9] POST /threads/${THREAD_ID}/messages"
FOLLOWUP=$(curl -sf -X POST "${BASE}/threads/${THREAD_ID}/messages" \
  -H 'Content-Type: application/json' \
  -d '{"content": "한 문장으로 더 짧게 요약해줘."}')
F_ROLE=$(echo "${FOLLOWUP}" | jq -r '.role')
F_LEN=$(echo "${FOLLOWUP}" | jq -r '.content | length')
[[ "${F_ROLE}" == "assistant" ]] || { echo "FAIL: followup role"; exit 1; }
[[ "${F_LEN}" -gt 0 ]] || { echo "FAIL: followup empty"; exit 1; }
echo "    followup len=${F_LEN}"

echo "[9/9] GET /threads/${THREAD_ID}/messages"
HISTORY=$(curl -sf "${BASE}/threads/${THREAD_ID}/messages")
MSG_COUNT=$(echo "${HISTORY}" | jq 'length')
ROLES=$(echo "${HISTORY}" | jq -r '[.[].role] | join(",")')
[[ "${MSG_COUNT}" == "4" ]] || { echo "FAIL: msg count=${MSG_COUNT}"; exit 1; }
[[ "${ROLES}" == "user,assistant,user,assistant" ]] || {
  echo "FAIL: roles=${ROLES}"; exit 1; }
echo "    messages=${MSG_COUNT} roles=${ROLES}"

echo
echo "verify_api.sh OK"
