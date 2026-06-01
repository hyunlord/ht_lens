# Phase 8e-2 — Migration manifest (R5, source traceability)

MinerU: `~/mineru_venv/bin/mineru` 3.2.1 (clean venv, transformers 4.57.6), backend=pipeline (CPU), lang=en.
Target DB: `data/ht_lens_v2.db` (alembic 0007). Backup: `data/ht_lens_v2.db.pre8e2.bak`.

| doc_id | filename | src PDF | sha256 (16) | pages | status |
| ------ | -------- | ------- | ----------- | ----- | ------ |
| 1 | book2_ch28.pdf | ~/mineru_test/doc7_chapter_990-1000.pdf (book2 ch28 slice) | (8a/8e-1) | 11 | translated+embedded (pre-8e-2) |
| 2 | sample_mixed.pdf | tests/fixtures/sample_mixed.pdf | 5c39a14a1c480d6b | 6 | ✅ chunks40 / tr40 (failed0) / emb22 / short-only N/A |
| 3 | 2503.09642v2.pdf | ~/pdfs_to_test/2503.09642v2.pdf | 52900e47452f0f39 | 21 | ✅ chunks196 / tr196 (failed0; 161 tr + 8 passthrough + 27 cached) / emb123 / short-only N/A |
| 4 | 2603.03482v1.pdf | ~/pdfs_to_test/2603.03482v1.pdf | e90622e9d705093c | 27 | ✅ chunks162 / tr162 (failed0; 154 tr + 6 passthrough + 2 cached) / emb96 / short-only N/A |
| 5 | aggarwal_textbook.pdf | ~/pdfs_to_test/1aggarwal_c_c_recommender_systems_the_textbook.pdf | 7d473bfb409be0fd | 518 | ✅ chunks3338 / tr3329 (failed9=0.27%) / emb2543 |

## 최종 (5-doc)
- **총 3839 chunk, 3830 translated(99.77%), 9 영어 fallback, 2840 embeddings.**
- doc 1–4: failed 0. doc 5(Aggarwal 518p): failed 9 (2 = 초대형 TOC/index >max_tokens 2048; 7 = 수식밀집 math-loss). 전부 empty text fail-preserve(무손상), reflow에서 영어 원문 노출.
- math byte-identical 표본: doc4 18/18, doc5 13/13.
- cross-doc 데이터: 5 doc 전부 임베딩(8d-2b 머신 cross-doc 가능; live 검증=8e-3).
- 1.x prod 무손상: alembic 0004, blocks 49850, chunk_tables 0.

## 배치 중 블로커 2건 (둘 다 환경, 코드 아님; 해결)
1. **MinerU venv transformers 5.9.0** → `find_pruneable_heads_and_indices` 제거로 추출 0. 해결: 격리 venv `~/mineru_venv`(transformers 4.57.6, mineru[all]). 기존 `~/mineru_test/venv` 불변.
2. **Aggarwal 518p OOM**: (a) MinerU 내부 task-result timeout 3600s → `MINERU_TASK_RESULT_TIMEOUT_SECONDS=14400`로 통째 완주. (b) qwen 서버(sglang-qwen-27b docker) 교과서 부하로 OOM 반복 crash → concurrency 7→2 낮추고 `--retry-failed` idempotent drain(2392→1804→1147→823→649→259→10→9 수렴, cache로 성공분 보존).

book2 full 1370p = cutover 후 follow-up. phase6d_demo×2 = 소스 없음(skip). 볼드 = defer(사용자).
