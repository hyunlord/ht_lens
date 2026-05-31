# Phase 8e-2 — BLOCKER (Stage 4, extraction)

## 막힌 지점
첫 문서(sample_mixed 6p) `extract-mineru` 실행 시 MinerU 3.2.1이 즉시 실패:

```
cannot import name 'find_pruneable_heads_and_indices'
from 'transformers.pytorch_utils'
```

## 원인 (확정 진단)
- `~/mineru_test/venv`의 **transformers == 5.9.0**. 이 심볼은 transformers 5.x에서 제거됨(4.x에는 존재).
- MinerU 3.2.1 모델 로딩(pipeline backend)이 이 심볼에 의존 → import 실패 → 추출 0건.
- 타임라인: doc7 추출 = 2026-05-29 02:55(성공). transformers 재설치 = 2026-05-29 22:37(이후). → 그 사이 transformers가 5.9.0으로 업그레이드되며 MinerU가 깨짐.
- ht_lens repo 코드/PDF 문제 아님. **MinerU 샌드박스 venv의 의존성 회귀**.

## 영향 범위
- **8e-1(math 강건화)는 완료·push(`f60b338`), 영향 없음.** prod 1.x 무손상.
- 8e-2의 **추출 단계만 차단**. ingest/translate/embed는 추출 산출물이 있어야 진행 가능.
- DB 미변경(추출이 ingest 전에 실패). v2 DB 백업 `data/ht_lens_v2.db.pre8e2.bak` 보관 중.

## Human 필요 (택1)
1. **(권장) MinerU venv의 transformers 다운그레이드**: `~/mineru_test/venv`에서 MinerU 3.2.1 호환 버전으로
   - 예: `~/mineru_test/venv/bin/pip install 'transformers<5'` (정확 핀은 MinerU 3.2.1 테스트 버전; 4.4x~4.5x대 권장)
   - 다운그레이드 후 `~/mineru_test/venv/bin/mineru -p tests/fixtures/sample_mixed.pdf -o /tmp/t` 1회 성공 확인되면 알려주세요 → 배치 재개.
2. MinerU venv 재생성(3.2.1 pinned deps대로).
3. 다른 MinerU 설치/바이너리 경로 제공(`HT_LENS_MINERU_BIN`).

## 비고
- 이 venv는 repo 밖 사용자 환경이라 제가 임의로 의존성 변경하지 않았습니다(다른 용도로 transformers 5.9.0을 의도적으로 올렸을 수 있어 위험).
- 해결되면 8e-2 Stage 4(extract→ingest→translate(+neighbor)→embed, smallest-first + manifest + doc별 verify)를 즉시 재개합니다.
