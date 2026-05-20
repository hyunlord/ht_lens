# ht_lens — Development Workflow

이 문서는 매 phase가 따라야 하는 작업 사이클을 정의한다.
**핵심 특징**: plan은 Claude Code가, debate/verify cross-check은 **Codex CLI**가 자동으로 담당한다. 두 모델이 서로의 사각지대를 보완한다.

## Roles

| Role     | 위치                | 책임                                                     |
| -------- | ------------------- | -------------------------------------------------------- |
| Human    | chat (web)          | 의사결정, 최종 승인, repo push                           |
| Planner  | Claude web          | phase prompt 작성, evidence 검토, 최종 PASS 판정         |
| Worker   | Claude Code         | plan/challenge/code/verify/summary 산출, 자동화 트리거    |
| Critic   | **Codex CLI**       | debate, verify cross-check (스크립트로 자동 호출)        |

## Cycle Overview

```
Planner ──prompt──► Worker (Claude Code)
                       │
                       ├─ 1. plan.md
                       │
                       ├─ 2. [auto] bash scripts/run_debate.sh N
                       │     └─► Critic (Codex) ─► debate.md
                       │
                       ├─ 3. challenge.md  (debate에 응답 + DoD 매핑)
                       │     └─ FAIL → back to 1
                       │
                       ├─ 4. code  (small commits)
                       │
                       ├─ 5a. verify.md  (self-score)
                       │
                       ├─ 5b. [auto] bash scripts/run_verify_cross.sh N
                       │     └─► Critic (Codex) ─► verify-cross.md
                       │
                       ├─ 5c. 두 verify 종합 판정 (cross-verify 라운드 상한 적용)
                       │     ├─ both PASS → next
                       │     └─ disagreement → RE-CODE / Planner escalation
                       │
                       └─ 6. summary.md ──► Planner (web)
                                              │
                                              └─ review → next phase or rework
```

모든 산출물은 `.claude/phases/phase-N/`에 저장되고 git에 커밋된다.

---

## Stage 1 — Plan (Worker)

**산출물**: `.claude/phases/phase-N/plan.md`

**필수 섹션**
- **Goal**: 한 줄 (ROADMAP의 Deliverable과 일치)
- **Scope**: 들어가는 것 / 안 들어가는 것
- **Approach**: 핵심 설계 결정
- **File-level changes**: 어떤 파일을 만들고/수정하는지
- **Dependencies**: 추가하려는 package + 정당화
- **Test strategy**: 어떻게 검증할지
- **DoD mapping**: ROADMAP Phase DoD를 항목별로 어떻게 만족할지

**금기**
- 모호한 문장 금지 ("적절히 처리한다" → 구체적 결정)
- ROADMAP에 없는 기능 추가 금지

---

## Stage 2 — Debate (자동, Codex)

Worker는 plan.md 작성 직후 **반드시 호출**:

```bash
bash scripts/run_debate.sh <phase-num>
```

이 스크립트가:
1. ROADMAP.md, plan.md를 컨텍스트로 모음
2. `prompts/codex_debate.md`를 instruction으로 Codex에 전달
3. `codex exec --sandbox read-only --ephemeral --output-last-message`로 실행
4. 결과를 `.claude/phases/phase-N/debate.md`에 저장

Worker는 결과를 읽고 다음 stage로 진행한다. **debate.md를 직접 작성하지 않는다.**

Codex가 다음 5개 섹션을 강제로 채운다 (prompt로 강제):
1. Over-engineering
2. Hidden assumptions
3. Edge cases
4. Alternative approaches
5. Missing tests

---

## Stage 3 — Challenge (Worker)

**산출물**: `.claude/phases/phase-N/challenge.md`

debate.md를 읽고 종합 검증.

- **Debate responses**: debate의 각 항목에 대해 `accept / partial / reject + 근거`
- **Plan revisions**: debate 결과 plan에 어떤 변경이 있었는지
- **DoD checklist**: ROADMAP Phase N의 DoD를 표로 (항목 / 만족 방법 / evidence 계획)
- **Risk register**: 남은 위험 + 완화 방안
- **Decision**: `PASS` (코드 단계로) / `RE-PLAN` (Stage 1로, 이유 명시)

**경고**: debate critique를 3개 이상 reject한다면 의심하라. 정말 모두 기각할 정도인지 다시 검토.

---

## Stage 4 — Code (Worker)

- 작은 커밋 (한 컴포넌트, 한 기능)
- Conventional Commits (`feat:`, `fix:`, `test:`, `refactor:`)
- 매 커밋 후 `make test-fast` 통과 유지
- plan/challenge에 명시된 dependency만 사용
- mypy strict / ruff clean 유지

plan에서 벗어나는 결정이 생기면:
- 작은 일탈: `summary.md`의 "deviations"에 기록
- 큰 일탈: 코드 멈추고 plan을 patch + challenge에 추가 검증

---

## Stage 5 — Verify

### 5-A. Self-verify (Worker)

**산출물**: `.claude/phases/phase-N/verify.md`

**중요**: verify.md는 **마지막 code commit 이후에 작성**한다. verify 작성 후 코드를 더 수정하면 verify는 stale 상태가 된다. 그 경우 verify.md를 **새 버전으로 다시 작성**해야 한다 (예: `verify.md` v2로 덮어쓰기). 이 규칙은 Phase 1의 stale verify 사건 이후 추가.

검증 직전 체크:
```bash
git status   # working tree clean이어야 함
git log -1   # 마지막 commit이 code/test commit인지 확인
```

**Automated checks (전 phase 공통)**

| 항목     | 명령                                       | 통과 기준    |
| -------- | ------------------------------------------ | ------------ |
| Lint     | `uv run ruff check .`                      | 0 error      |
| Format   | `uv run ruff format --check .`             | 0 diff       |
| Type     | `uv run mypy src/`                         | 0 error      |
| Test     | `uv run pytest -m "not llm and not slow"`  | all pass     |
| Coverage | (위에 포함)                                | ≥ phase 목표 |
| CI       | GitHub Actions                             | green        |

**Functional checks (phase 종류별)**

| Phase     | 검증 방식                                              |
| --------- | ------------------------------------------------------ |
| 1 (CLI)   | sample PDF 3종으로 실행 + snapshot                     |
| 2a (CLI)  | extract 결과 3종 ingest, DB 행 검증, mock LLM 동작     |
| 2b (CLI)  | short fixture 실제 sglang 호출 번역 + 캐시 + 재시도    |
| 3 (API)   | `scripts/verify_api.sh` httpie 시나리오                |
| 4 (UI)    | 실문서 1권 + 스크린샷 3장 (`docs/phases/phase-4/`)     |
| 5 (UI)    | 10개 질문 시나리오 + 스크린샷                          |
| 6         | baseline 회귀 + 신규 기능 검증                         |

**Scoring (100점)**

| 항목       | 만점 | 평가 기준                                                |
| ---------- | ---: | -------------------------------------------------------- |
| 독창성     |   15 | 문제에 맞는 설계, 불필요한 일반화 없음                  |
| 완결성     |   35 | DoD 모든 항목 evidence와 함께 만족                      |
| 안정성     |   30 | 에러 처리, 엣지 케이스, 테스트 커버리지, 재현 가능성    |
| 확장성     |   20 | 다음 phase로 가는 길이 막히지 않음, 추상화 적절         |

**각 항목 점수에는 evidence 필수**. Worker self-score는 "통과 후보" 상태.

### 5-B. Cross-verify (자동, Codex) — round 상한 적용

Worker는 verify.md 작성 직후 **반드시 호출**:

```bash
bash scripts/run_verify_cross.sh <phase-num>
```

이 스크립트가:
1. ROADMAP.md, verify.md, 이전 라운드의 verify-cross.md (있으면), git diff/log를 컨텍스트로 모음
2. `prompts/codex_verify.md`를 instruction으로 Codex에 전달
3. Codex가 read-only로 코드 검사
4. 결과를 `.claude/phases/phase-N/verify-cross.md`에 저장 (라운드별 누적: `verify-cross-rN.md`)

Codex 출력 verdict:
- `CONFIRM_PASS`: self-assessment 신뢰
- `DOWNGRADE`: 점수 하향 + 사유
- `REJECT`: 심각한 이슈 + RE-CODE or RE-PLAN 추천

#### **Cross-verify 라운드 상한 (Phase 1 사후 도입)**

한 phase 안에서 **cross-verify 호출은 최대 2회**. 그 이상은 Planner에게 escalate.

- **Round 1**: 첫 verify 후 자동 호출
- **Round 2**: Round 1에서 REJECT/DOWNGRADE → RE-CODE 후 1회만 더 호출
- **Round 3 이상**: Worker가 호출하지 않는다. 다음 두 가지 중 하나:
  - Round 2에서 `CONFIRM_PASS` → 정상 진행
  - Round 2에서도 REJECT/DOWNGRADE → `summary.md`에 양쪽 의견 명시 + Planner에게 escalate (Worker는 Stage 6로 진행)

**이유**: Phase 1에서 cross-verify가 4라운드 돌면서 같은 영역을 다른 각도로 계속 지적. 무한 iteration 위험. 인간(Planner)이 끊어주는 게 시스템 정합성에 더 좋음.

### 5-C. Verdict (Worker)

두 verify 종합 (라운드 상한 내):

| Self (Worker) | Cross (Codex)        | Round | 결과                                              |
| ------------- | -------------------- | ----- | ------------------------------------------------- |
| ≥95           | CONFIRM_PASS         | any   | **PASS_CANDIDATE** → Stage 6 진입                 |
| ≥95           | DOWNGRADE            | 1     | RE-CODE → Round 2                                 |
| ≥95           | DOWNGRADE            | 2     | summary에 양측 명시 + Stage 6 진입 (Planner 판정) |
| ≥95           | REJECT               | 1     | RE-CODE or RE-PLAN (Codex 추천 따름)              |
| ≥95           | REJECT               | 2     | summary에 양측 명시 + Stage 6 진입 (Planner 판정) |
| <95           | -                    | any   | RE-CODE or RE-PLAN (Worker 판단)                  |

**최종 PASS 판정은 Planner(web)가 한다.** Worker의 "PASS_CANDIDATE"는 web 검토 대기 상태.

---

## Stage 6 — Summary (Worker)

**산출물**: `.claude/phases/phase-N/summary.md`

**필수 섹션**
- **Status**: PASS_CANDIDATE / FAIL
- **Score**: self 항목별 + 합계
- **Cross-verify verdict**: round별 (CONFIRM_PASS / DOWNGRADE / REJECT)
- **Round limit 도달 여부**: round 2 이후 양측 disagreement면 그 사유 정확히
- **What was built**: 3~5 bullet
- **Files changed**: `git diff --stat` 요약
- **Deviations from plan**: 있으면
- **Evidence index**: 산출물 파일 링크
- **Known issues / debt**: 다음 phase로 미루는 것들
- **Recommended next**: 다음 phase 시작 전 알아야 할 것

작성 후:
1. `git add . && git commit -m "feat(phase-N): <one-liner>"`
2. **Push 정책** (아래 표 참조)
3. 작업 중지, summary 내용을 Human에게 보고

#### Push 정책 (Phase 2b 사후 도입)

| 상황                                                | Worker push? |
| --------------------------------------------------- | ------------ |
| self ≥ 95 + cross CONFIRM_PASS (Round 1)            | **YES**      |
| self ≥ 95 + cross CONFIRM_PASS (Round 2)            | **YES**      |
| Round 2에서 cross-verify DOWNGRADE/REJECT          | **NO** (Planner escalate) |
| Planner-directed targeted fix 직후                  | **NO** (Planner가 직접 push) |
| self < 95                                           | **NO** (RE-CODE 또는 escalate) |

Worker가 push한 경우 `summary.md`에 명시 (예: "pushed to origin/main at <commit>").
Planner 검토가 필요한 경우 (Round 2 REJECT, targeted fix 등) push 보류 + 보고만.

---

## Minor Tasks (간이 사이클)

전체 phase가 아닌 작은 수정은 간이 사이클:

1. **mini-plan**: 채팅에서 3~5줄
2. **code**
3. **verify**: 자동 체크 + 기능 확인 (cross-verify 생략 가능)
4. **commit**: 단일

산출물 파일은 만들지 않는다. "사실 새 기능이다" 싶으면 풀 사이클로 승급.

---

## Phase 0 적용

Phase 0은 워크플로우를 **셋업하는 단계**이므로:
- plan/debate/challenge **생략**
- code = 셋업 자체
- verify.md, summary.md는 생성 (셋업 결과 검증)
- cross-verify는 **선택** (셋업이 단순하면 생략 가능)

Phase 1부터 풀 사이클 적용.

---

## Prerequisites

자동화가 동작하려면 다음이 갖춰져야 한다:

- **Claude Code** 설치 및 인증 (Anthropic)
- **Codex CLI** 설치 및 인증 (OpenAI)
  ```bash
  npm install -g @openai/codex
  codex  # 첫 실행 시 ChatGPT OAuth 또는 API key 인증
  ```
- 두 CLI 모두 `$PATH`에 있어야 함
- `scripts/*.sh`는 `chmod +x` 되어 있어야 함

Worker는 작업 시작 전에 `codex --version`으로 Codex 가용성을 확인한다. 없으면 작업 멈추고 Human에게 알린다.

**LLM endpoint (Phase 2b부터)**:
- OpenAI-compatible endpoint 필요 (기본: sglang Qwen3.6 27B at `http://localhost:8081/v1`)
- `.env`의 `LLM_BASE_URL`, `LLM_MODEL` 사용
- `enable_thinking=false` 필수 (chat template 변경 감지를 위해 회귀 체크 코드 포함)

---

## 산출물 디렉토리 구조

```
.claude/
  phases/
    _template/
      plan.md
      debate.md            # Codex 산출용 placeholder
      challenge.md
      verify.md
      verify-cross.md      # Codex 산출용 placeholder
      summary.md
    phase-N/
      plan.md
      debate.md            # 자동 생성 (Stage 2)
      challenge.md
      verify.md            # 마지막 code commit 이후 작성
      verify-cross.md      # 자동 생성 (Stage 5-B Round 1)
      verify-cross-r2.md   # Round 2 발생 시
      summary.md

prompts/
  codex_debate.md          # Codex debate 시스템 프롬프트
  codex_verify.md          # Codex verify cross-check 시스템 프롬프트

scripts/
  run_debate.sh            # Codex 호출 래퍼 (debate)
  run_verify_cross.sh      # Codex 호출 래퍼 (verify cross)

docs/
  phases/
    phase-4/screenshots/
    phase-5/screenshots/
```
