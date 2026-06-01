# Phase 8e-2 — BLOCKER #2 (Stage 4, Aggarwal translation)

## 막힌 지점
Aggarwal(doc 5, 3338 chunk) 번역 중 **qwen 엔드포인트(`localhost:8081`)가 다운**.
- 결과: translated 530 + passthrough 411 + cached 5 = **946 성공**, **2392 failed**.
- 번역이 ~20분만에 끝남(2330 text chunk엔 너무 빠름) → 중간부터 전부 즉시 실패.

## 원인 (확정 진단 — 코드/math 문제 아님)
- **엔드포인트 사망 시그니처**: order_idx band별 성공/실패 —
  - 0–799: 583 성공 / 217 실패 (초반 정상)
  - 800–1599: 111 / 689
  - 1600–2399: 119 / 681
  - 2400+: 133 / 805
  - → 초반은 잘 되다 ~800부터 실패 폭증 = 서버가 중간에 죽음.
- **health_check 2회 연속 실패**: `LLMHealthCheckFailed: Connection error` (`localhost:8081`).
- 8e-1 math 강건화는 정상: 4 small doc(501 chunk) 0 실패 + Aggarwal 초반 583 성공. failed row는 전부 empty text(fail-preserve, 무손상).
- 추정: 518p 교과서(2330 text chunk) 연속 부하로 vLLM/qwen 서버 OOM/crash.

## 영향 (안전 — 손실 0)
- doc 1–4 완료(501 chunk, 0 failed) 불변.
- doc 5: **946 성공분은 cache 보존** → 재시도 시 cache hit(재호출 안 함). **2392만 재번역** 필요.
- prod 1.x 무손상. v2 DB 백업 보관.

## Human 필요 (LLM 서버는 사용자 인프라)
1. **qwen 서버(`localhost:8081`) 재시작.** (OOM이면 동시성↓ 고려.)
2. 재시작 후 health 확인되면 알려주세요 → 제가 즉시 재개:
   ```
   uv run python -m ht_lens.cli translate-chunks --doc-id 5 --retry-failed --db data/ht_lens_v2.db
   ```
   - `--retry-failed`는 **status='failed' 2392개만** 재처리. 946 성공분은 건드리지 않음.
   - 대용량 재시도라 OOM 재발 막으려면 `--concurrency 3` 정도로 낮춰 재개 가능(원하시면).
3. (대안) Aggarwal을 이번 배치에서 빼고 4-doc로 8e-2 마무리 → Aggarwal은 cutover 후 follow-up. (4-doc도 cross-doc RAG·multi-doc 입증 충분.)

## 비고
- `localhost:8081`은 제가 통제하지 않는 사용자 LLM 서버라 재시작은 Human이 해야 합니다.
- 재개는 idempotent(`--retry-failed` + cache)이라 안전하게 여러 번 가능.
