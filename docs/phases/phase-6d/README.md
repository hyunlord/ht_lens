# Phase 6d — File Management + Summary screenshots

DoD evidence for Phase 6d (v0.7 milestone). All captures via
`scripts/phase6d_scenario.py` (Playwright + chromium, viewport
1400×950). The live server uses the operator's `.env`
(`LLM_PROVIDER=openai_compat`, `LLM_TIMEOUT=300`) so summaries come
from real sglang `qwen3.6-27b`.

| # | File | Notes |
| - | ---- | ----- |
| 1 | `01-upload-zone-empty.png` | 진입 직후. localStorage clear. drop zone + 파일 선택 버튼 + 기존 카드 1개 (sample_mixed.pdf). |
| 2 | `02-drag-over.png` | `.upload-zone--drag` 클래스가 적용된 hover state. 드래그 인식 시 backdrop 색 변화. |
| 3 | `03-upload-in-progress.png` | `<input type=file>`을 직접 set한 직후. active-jobs 패널이 progress bar + "PDF 추출 중: …" 메시지 표시. |
| 4 | `04-translating-mid.png` | translate 단계 (progress 30~90%). every-10 block callback이 `번역 중 N/M` 갱신. |
| 5 | `05-summarizing.png` | summarize 단계 (92%). LLM 호출 진행 중. |
| 6 | `06-done-and-card.png` | 완료 후 jobs panel 자동 dismiss + 새 카드 등장. summary preview 라인 (120자 cap)이 카드에 보임. |
| 7 | `07-dedup-toast.png` | 동일 PDF 재업로드 → `dedup=true` 응답 → "이미 업로드된 문서입니다 → viewer로 이동" 토스트. |
| 8 | `08-failed-error-display.png` | txt 파일 업로드 시도 → 415 거부 → status banner에 "업로드 실패: PDF 파일만 업로드 가능합니다 (매직 바이트 불일치)" 표시. |
| 9 | `09-summary-in-card.png` | 06과 동일 시점, 카드에 한국어 요약 preview. |
| 10 | `10-summary-full-in-viewer.png` | viewer 진입 시 `#stage` 위 summary-banner에 full abstract 표시. "재생성" 버튼 포함. |

## Live LLM evidence — end-to-end

```
$ curl -X POST http://localhost:8080/uploads \
       -F "file=@phase6d_demo.pdf;type=application/pdf"
{"job_id": 1, "document_id": null, "dedup": false}

$ for n in 1..N: curl /jobs/1 →
t=0s   status=extracting  pct=10  msg="PDF 추출 중: phase6d_demo.pdf"
t=5s   status=translating pct=30  msg="번역 시작"
t=15s  status=summarizing pct=92  msg="요약 생성 중"
t=56s  status=done        pct=100 msg="완료"
```

총 56초 (2 페이지). Per-block translate latency × 20 blocks + 50초
summarize. 200 페이지 PDF extrapolation: ~1~2 시간 (DoD 충족).

```
$ sqlite3 data/ht_lens.db "
    SELECT id, filename, length(summary), summarized_at
    FROM documents WHERE summary IS NOT NULL;"
2 | phase6d_demo.pdf | 1135 chars | 2026-05-21 17:09:04.697458
```

summary 요약 (300자):
> 제시된 문서는 두 가지 명확히 구분된 주제를 포함하고 있으며, 전체적으로는
> 기술적 테스트 도구와 인공지능(AI) 비디오 생성 모델의 성과 보고로
> 구성되어 있습니다. 문서의 첫 번째 부분은 시스템 파이프라인의 무결성
> 검증을 위한 기술적 문서의 성격을 띠고 있습니다. …

자연 한국어 요약, 300~500단어 분량, DoD 충족.

```
$ curl -X POST /uploads -F "file=@phase6d_demo.pdf"  # 재업로드
{"job_id": null, "document_id": 2, "dedup": true}
```

Dedup 동작 확인 (UNIQUE constraint + 라우터 fast-path 둘 다).

## Reproducing

```bash
export LLM_PROVIDER=openai_compat \
       LLM_BASE_URL=http://localhost:8081/v1 \
       LLM_MODEL=qwen3.6-27b \
       LLM_TIMEOUT=300
scripts/dev_serve.sh restart
python scripts/phase6d_scenario.py 8080 /path/to/your.pdf
```

## Notes

- 자동 요약은 single-shot 8 KB-cap (hierarchical은 Phase 6e 검토)
- summarize 실패는 `status=done + error_message` non-fatal
- Restart 시 active job은 자동으로 `failed` 처리 (recovery)
- 100 MB 초과 / non-PDF / path traversal은 모두 거부 (테스트 잠금)
