# Phase 8e-2 — Plan (7-doc 배치 마이그레이션) — 8e 시리즈 2/3

## 8e 컨텍스트
8e-1(math 강건화 + 볼드 finding) ✅ push(`f60b338`). 이 phase(8e-2)는 실 문서들을 2.0 DB로 마이그레이션. 8e-3 = cutover + CI + debt.

## Goal
실 문서를 8a~8e-1 파이프라인(extract→ingest→translate(+neighbor)→embed)으로 2.0 DB에 적재. **incremental smallest-first**, 큰 추출은 백그라운드 + doc별 verify. 1.x prod 무손상.

## Stage 0 실측 (확정)
- 대상(사용자 확정): **sample_mixed(6p) → 2503.09642v2(21p) → 2603.03482v1(27p) → Aggarwal(518p, 백그라운드)**. **book2 = ch28(doc7, 이미 적재)** — full 1370p는 cutover 후 follow-up. phase6d_demo×2 = 소스 없음(skip).
- 현 2.0 DB `data/ht_lens_v2.db`: doc1=book2_ch28(translated, chunks103/tr103/emb56), alembic 0007.
- CLIs(8a/8b/8e-1): `extract-mineru`(CPU pipeline) / `ingest-mineru` / `translate-chunks`(신 math 강건화) / `translate-chunks --short-only`(8d-2c neighbor) / `embed-chunks`.
- MinerU 3.2.1 `~/mineru_test/venv/bin/mineru` (HT_LENS_MINERU_BIN). **볼드 defer**(사용자): CPU pipeline 그대로(볼드 메타데이터 없음, 8e-1 finding).

## Scope
**In (8e-2)**
- 4개 문서 마이그레이션(위 순서)을 **기존 `data/ht_lens_v2.db`에 추가** → 5-doc 2.0 DB(cutover 후보). 각 doc:
  1. `extract-mineru --pdf <p> --out <dir>` (CPU). 큰 doc(Aggarwal)는 백그라운드.
  2. `ingest-mineru` → chunks.
  3. `translate-chunks --doc-id N` (신 ASCII sentinel + 보존 지시 + retry).
  4. `translate-chunks --doc-id N --short-only` (neighbor 재번역, <25자 저문맥).
  5. `embed-chunks --doc-id N` (bge-m3).
  6. **doc별 verify**: chunks/tr/emb 카운트, failed 수(8e-1로 최소 기대), math byte-identical 표본, reflow 로드.
- **cross-doc RAG live 활성화**: ≥2 doc 임베딩 → 8d-2b 머신이 실제 cross-doc hit. (검증은 8e-3, 8e-2는 데이터 적재로 가능케 함.)

**Out**
- cutover/env 전환/CI/schema-head = 8e-3. book2 full 1370p = cutover 후. 볼드 = defer(별도). 웹 검색 = 8f. `scripts/` 신규(사람 영역) — 직접 CLI 오케스트레이션만.

## Approach
- **코드 변경 최소**: 기존 CLI 파이프라인 실행이 주. 실 문서(papers/textbook)가 ingest/extract 결함을 드러내면 그때 fix(작은 commit). 그 외 신규 코드 0 목표.
- **실행**: small 3개는 foreground 순차(빠름), Aggarwal(518p)는 `run_in_background` 추출 → 완료 후 ingest/translate/embed. 각 단계 exit code 확인(8a/8b fail-fast).
- **DB 격리**: 모든 작업 `--db data/ht_lens_v2.db`. prod `data/ht_lens.db` 절대 미접근(verify에서 0004/49850/0 재확인).
- **failed chunk**: 8e-1 math 강건화로 수식밀집도 번역 기대. 잔존 failed는 doc별 기록(영어 fallback 허용, 수 명시).

## File-level changes (예상)
| Path | Action | Note |
| ---- | ------ | ---- |
| (코드 0 목표) | — | 기존 CLI 실행. ingest/extract 결함 발견 시만 src fix |
| `data/ht_lens_v2.db` | 데이터 | 4 doc 추가(gitignore, 커밋 안 됨) |
| `.claude/phases/phase-8e-2/*` | 산출물 | plan/debate/challenge/verify/summary + 배치 로그 |

## Dependencies (new)
| Package | Why |
| ------- | --- |
| (없음) | MinerU/qwen/bge-m3 기존. |

## Test strategy
- **회귀**: 기존 768 fast green 유지(코드 변경 없으면 자동). 코드 fix 발생 시 해당 테스트 추가.
- **doc별 데이터 verify**(실측, 코드 테스트 아님): 각 doc chunks>0, tr 카운트=chunks(passthrough 포함), emb>0(text/heading), failed 수 기록, math byte-identical 표본(2-3 chunk), reflow API 200 + 본문 로드.
- **cross-doc RAG**: 한 doc 섹션 질문 → 다른 doc chunk가 related_chunks에 등장(8d-2b 머신, 실 데이터).
- **1.x 무손상**: prod 0004/blocks=49850/chunk_tables=0.

## DoD mapping
| DoD item | How | Evidence |
| --- | --- | --- |
| 다중 doc 2.0 DB | 4 doc extract→ingest→translate→embed | doc별 카운트 + 5-doc 총계 |
| reflow 전체 읽기 | 각 doc reflow 로드 | API 200 + chunk 렌더 |
| math 강건화 실효 | 신 파이프라인 적용 | doc별 failed 수(최소) + byte-identical 표본 |
| cross-doc RAG live | ≥2 doc 임베딩 | cross-doc related_chunks 등장 |
| 1.x 무손상 | 별 DB | prod 0004/49850/0 |

## 위험 / 완화
- **Aggarwal 518p 추출 시간(시간 단위)** → 백그라운드 + 진행 로그, small 3개 먼저 완료. 실패 시 격리(doc별 checkpoint).
- **실 PDF extract/ingest 결함**(encrypted/corrupt/대용량 layout) → 8a runner fail-fast(MineruError) + doc별 격리, 결함 시 src fix.
- **번역 시간/비용**(textbook 수백 chunk) → concurrency 기본 7, cache dedup(5.66x), 백그라운드.
- **disk**(이미지 추출물) → out 디렉토리 모니터링.
- **failed math 잔존** → 8e-1로 최소화 기대, 잔존은 영어 fallback(허용) + 수 기록.
- **1.x 오접근** → 모든 명령 `--db data/ht_lens_v2.db` 명시, prod 재확인.

## 결정 필요 (해결됨)
- 볼드 = defer(사용자 확정). book2 = ch28(확정). 대상 4 doc(확정). 진행=now(확정).
