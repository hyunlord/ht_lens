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
# Behaviour:
#   * iterates every document returned by GET /documents and runs the
#     read-only path (GET /documents/{id}, scan pages for a text block,
#     GET /documents/{id}/pages/{n}, GET /documents/{id}/pages/{n}/image)
#     against each one.
#   * runs the LLM-driven path (POST /threads, /explain, /messages,
#     GET /threads/{id}/messages) only against the FIRST document that
#     contains at least one text block — explain/follow-up live LLM calls
#     are expensive and one document is enough to cover the contract.
#
# Exits non-zero on the first failure.

set -euo pipefail

BASE="${1:-http://127.0.0.1:8080}"
need() {
  command -v "$1" >/dev/null 2>&1 || { echo "ERROR: $1 not installed" >&2; exit 1; }
}
need curl
need jq

TMP_PNG=$(mktemp --suffix=.png)
trap 'rm -f "${TMP_PNG}"' EXIT

echo "[1] GET /documents"
DOCS=$(curl -sf "${BASE}/documents")
COUNT=$(echo "${DOCS}" | jq 'length')
[[ "${COUNT}" -ge 1 ]] || { echo "FAIL: no documents"; exit 1; }
echo "    count=${COUNT}"

CHAT_DOC_ID=""
CHAT_BLOCK_ID=""

# Read-only pass over every document
DOC_IDS=$(echo "${DOCS}" | jq -r '.[].id')
for DOC_ID in ${DOC_IDS}; do
  echo "[2:${DOC_ID}] GET /documents/${DOC_ID}"
  DOC=$(curl -sf "${BASE}/documents/${DOC_ID}")
  NUM_PAGES=$(echo "${DOC}" | jq -r '.num_pages')
  [[ "${NUM_PAGES}" -ge 1 ]] || { echo "FAIL: doc=${DOC_ID} num_pages=${NUM_PAGES}"; exit 1; }
  echo "    num_pages=${NUM_PAGES}"

  echo "[3:${DOC_ID}] scan pages for a text block"
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

  if [[ -z "${BLOCK_ID}" ]]; then
    echo "    no text block — skipping page+image checks for doc=${DOC_ID}"
    continue
  fi
  echo "    block_id=${BLOCK_ID} page=${TEXT_PAGE}"

  echo "[4:${DOC_ID}] GET /documents/${DOC_ID}/pages/${TEXT_PAGE}"
  PAGE=$(curl -sf "${BASE}/documents/${DOC_ID}/pages/${TEXT_PAGE}")
  PAGE_NUM=$(echo "${PAGE}" | jq -r '.page_num')
  BLOCKS=$(echo "${PAGE}" | jq '.blocks | length')
  [[ "${PAGE_NUM}" == "${TEXT_PAGE}" ]] || { echo "FAIL: page_num=${PAGE_NUM}"; exit 1; }
  [[ "${BLOCKS}" -ge 1 ]] || { echo "FAIL: empty page"; exit 1; }
  echo "    blocks=${BLOCKS}"

  echo "[5:${DOC_ID}] GET /documents/${DOC_ID}/pages/${TEXT_PAGE}/image"
  HTTP_STATUS=$(curl -s -o "${TMP_PNG}" -w "%{http_code}" \
    "${BASE}/documents/${DOC_ID}/pages/${TEXT_PAGE}/image")
  [[ "${HTTP_STATUS}" == "200" ]] || { echo "FAIL: image status=${HTTP_STATUS}"; exit 1; }
  head -c8 "${TMP_PNG}" | xxd | grep -q '8950 4e47' || {
    echo "FAIL: response is not PNG"; exit 1; }
  SIZE=$(wc -c <"${TMP_PNG}")
  echo "    png bytes=${SIZE}"

  # Remember the first document that has a text block for the chat path.
  if [[ -z "${CHAT_DOC_ID}" ]]; then
    CHAT_DOC_ID="${DOC_ID}"
    CHAT_BLOCK_ID="${BLOCK_ID}"
  fi
done

[[ -n "${CHAT_DOC_ID}" ]] || { echo "FAIL: no document has any text block"; exit 1; }

# Chat path — only against CHAT_DOC_ID. The contract is exercised once;
# repeating live LLM calls for every doc would be costly with no extra signal.
echo "[6] POST /threads (doc=${CHAT_DOC_ID} block_id=${CHAT_BLOCK_ID})"
THREAD=$(curl -sf -X POST "${BASE}/threads" \
  -H 'Content-Type: application/json' \
  -d "{\"block_id\": ${CHAT_BLOCK_ID}}")
THREAD_ID=$(echo "${THREAD}" | jq -r '.id')
[[ -n "${THREAD_ID}" && "${THREAD_ID}" != "null" ]] || {
  echo "FAIL: thread create"; exit 1; }
echo "    thread_id=${THREAD_ID}"

echo "[7] POST /threads/${THREAD_ID}/explain"
EXPLAIN=$(curl -sf -X POST "${BASE}/threads/${THREAD_ID}/explain")
EXPLAIN_ROLE=$(echo "${EXPLAIN}" | jq -r '.role')
EXPLAIN_LEN=$(echo "${EXPLAIN}" | jq -r '.content | length')
[[ "${EXPLAIN_ROLE}" == "assistant" ]] || { echo "FAIL: explain role=${EXPLAIN_ROLE}"; exit 1; }
[[ "${EXPLAIN_LEN}" -gt 0 ]] || { echo "FAIL: explain empty"; exit 1; }
echo "    explain len=${EXPLAIN_LEN}"

echo "[8] POST /threads/${THREAD_ID}/messages"
FOLLOWUP=$(curl -sf -X POST "${BASE}/threads/${THREAD_ID}/messages" \
  -H 'Content-Type: application/json' \
  -d '{"content": "한 문장으로 더 짧게 요약해줘."}')
F_ROLE=$(echo "${FOLLOWUP}" | jq -r '.role')
F_LEN=$(echo "${FOLLOWUP}" | jq -r '.content | length')
[[ "${F_ROLE}" == "assistant" ]] || { echo "FAIL: followup role"; exit 1; }
[[ "${F_LEN}" -gt 0 ]] || { echo "FAIL: followup empty"; exit 1; }
echo "    followup len=${F_LEN}"

echo "[9] GET /threads/${THREAD_ID}/messages"
HISTORY=$(curl -sf "${BASE}/threads/${THREAD_ID}/messages")
MSG_COUNT=$(echo "${HISTORY}" | jq 'length')
ROLES=$(echo "${HISTORY}" | jq -r '[.[].role] | join(",")')
[[ "${MSG_COUNT}" == "4" ]] || { echo "FAIL: msg count=${MSG_COUNT}"; exit 1; }
[[ "${ROLES}" == "user,assistant,user,assistant" ]] || {
  echo "FAIL: roles=${ROLES}"; exit 1; }
echo "    messages=${MSG_COUNT} roles=${ROLES}"

echo
echo "verify_api.sh OK (documents checked: ${COUNT})"
