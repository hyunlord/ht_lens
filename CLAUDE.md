# Claude Code Instructions for ht_lens

이 프로젝트는 **엄격한 워크플로우**를 따른다. 모든 작업 전에 다음을 읽어라.

## 필독 문서 (우선순위 순)

1. **`WORKFLOW.md`** — 매 phase의 작업 사이클. 임의 생략 금지.
2. **`ROADMAP.md`** — 전체 계획과 현 phase의 DoD.
3. **`.claude/phases/phase-N/`** — 현 phase의 누적 산출물.

## 핵심: 너는 혼자가 아니다

너는 **Worker** 역할이다. **Codex CLI**는 **Critic** 역할로, 너의 plan과 verify를 외부 검토한다.
- `bash scripts/run_debate.sh N` → Codex가 debate.md 생성
- `bash scripts/run_verify_cross.sh N` → Codex가 verify-cross.md 생성

이 두 명령은 **워크플로우상 필수**다. 건너뛰지 마라.

작업 시작 전 Codex 가용성 확인:
```bash
codex --version || { echo "Codex CLI not installed"; exit 1; }
```
없으면 작업 멈추고 Human에게 알려라.

## 절대 원칙

- **추측 금지**: 모호하면 작업 멈추고 질문.
- **스코프 고정**: 사용자 prompt + ROADMAP 해당 Phase만. "이왕 하는 김에" 금지.
- **Phase 격리**: 다른 phase 영역 침범 금지.
- **Dependency 격리**: plan/challenge에 명시된 것만 추가. ROADMAP에 없는 큰 라이브러리는 plan에 정당화 + Planner 승인 필요.
- **품질 기준**: 매 커밋마다 mypy strict 위반 0, ruff clean, `make test-fast` green 유지.
- **산출물 추적**: plan/debate/challenge/verify/verify-cross/summary 모두 파일로 남김.

## verify.md 작성 타이밍 (Phase 1 stale verify 사후 추가)

verify.md는 **마지막 code commit 이후에 작성**한다. 다음을 반드시 지켜라:

1. verify 작성 직전 `git status` 가 clean이어야 함
2. verify 작성 후 코드를 수정하면 (RE-CODE, plan stale 정리 등) **verify를 새 버전으로 다시 작성**해야 한다
   - 같은 파일을 덮어쓰거나 (`verify.md` v2 등으로 history는 git이 추적)
   - 5-A의 모든 검사 명령을 **다시 실행**한 출력을 기준으로
3. "expected" 라는 단어를 verify의 결과 칸에 쓰지 마라. CI green은 push 후 확정되는 거고, 그 외엔 모두 실측값.

이 규칙을 어기면 cross-verify가 stale을 즉시 잡아낸다.

## Cross-verify round 상한 (Phase 1 사후 도입)

한 phase 안에서 `bash scripts/run_verify_cross.sh` 호출은 **최대 2회**. WORKFLOW.md Stage 5-B 참조.

- Round 1: 첫 verify 후 자동 호출
- Round 2: Round 1에서 REJECT/DOWNGRADE → RE-CODE 후 1회만 더
- Round 3 이상은 호출하지 마라. summary.md에 양측 의견 명시하고 Planner에게 escalate.

## RE-CODE regression 가드 (Phase 2b 사후 도입)

RE-CODE 라운드에서 **새 결함을 도입하는** 케이스가 실제로 발생했다. 이를 방지하기 위해:

1. **RE-CODE 후 verify.md는 반드시 "Regression check" 섹션을 포함**한다. 다음 내용:
   - Round 1에서 fix한 영역의 회귀 여부 (해당 영역의 테스트 명확히 통과 확인)
   - RE-CODE에서 새로 추가/수정한 코드 경로의 단위 테스트 존재 여부
   - 새 코드가 기존 contract (CLI exit code, public API 등)를 깨지 않았는지

2. **새 코드 경로는 반드시 테스트**: 특히 CLI exit code 분기, error handler, edge case branch는 subprocess 또는 unit test로 잠금. "수동 확인했다"는 evidence 부족.

3. **fix가 의도한 영역 외 추가 변경**: 작은 정합성 정리(예: exit code 통일)는 OK이지만 summary.md의 "Deviations from plan"에 명시.

## Phase 시작 시 절차

사용자가 `phase_N_prompt.md` 내용을 주면:

1. `ROADMAP.md`의 Phase N 섹션을 다시 읽고 DoD 확인.
2. `codex --version`으로 Codex 가용성 확인.
3. `.claude/phases/phase-N/` 디렉토리 생성, `_template/`에서 복사.
4. **Stage 1**: plan.md → commit (`chore(phase-N): plan`)
5. **Stage 2**: `bash scripts/run_debate.sh N` → debate.md 생성됨 → commit (`chore(phase-N): debate`)
6. **Stage 3**: debate 읽고 challenge.md → commit (`chore(phase-N): challenge`)
   - Decision `PASS`면 진행, `RE-PLAN`이면 Stage 1로
7. **Stage 4**: 코드 작업, 작은 commit들
8. **Stage 5a**: verify.md (self-score) → commit (`chore(phase-N): verify`)
   - `git status` clean 확인 필수
9. **Stage 5b**: `bash scripts/run_verify_cross.sh N` (Round 1) → commit
10. **Stage 5c**: round 1 결과 종합. DOWNGRADE/REJECT면 RE-CODE → 새 verify.md → Round 2 cross-verify (마지막). Round 2 이후엔 호출하지 마라.
11. **Stage 6**: summary.md → commit
12. Push 정책 (WORKFLOW.md Stage 6 참조):
    - 정상 PASS_CANDIDATE → `git push`
    - Round 2 REJECT/DOWNGRADE → push 보류, Planner escalate
    - Planner-directed fix → push 보류, Planner가 직접
13. summary 내용을 Human에게 보고. 작업 종료.

## 커밋 메시지 규칙 (Conventional Commits)

- `chore(phase-N): plan` — Stage 1 직후
- `chore(phase-N): debate` — Stage 2 직후 (Codex 결과 + 너의 commit)
- `chore(phase-N): challenge` — Stage 3 직후
- `feat(phase-N): <기능>` — Stage 4 본 구현
- `test(phase-N): <대상>` — 테스트 추가
- `chore(phase-N): verify` — Stage 5a (또는 verify v2, v3로 RE-CODE 후 재작성)
- `chore(phase-N): verify-cross` — Stage 5b Round 1
- `chore(phase-N): verify-cross r2` — Round 2 발생 시
- `fix(phase-N): <fix>` — RE-CODE 라운드
- `chore(phase-N): summary` — Stage 6

## 막힐 때

- 추측해서 진행하지 말 것.
- `.claude/phases/phase-N/questions.md`에 질문 적고 작업 멈춰라.
- Human이 답을 주면 그 후에 진행.

## 절대 하지 말 것

- `ROADMAP.md`, `WORKFLOW.md`, `CLAUDE.md`, `AGENTS.md` 수정 (사람이 한다)
- `prompts/`, `scripts/` 내용 임의 수정 (사람이 한다)
- 다른 phase 산출물 수정
- 사용자 prompt에 없는 기능 추가
- **debate.md, verify-cross.md 직접 작성** — Codex의 산출물이다
- `bash scripts/run_*.sh` 호출 생략
- cross-verify 3라운드 이상 자체 호출
- self-score를 95+로 매기되 evidence가 부실한 경우 (Planner가 reject한다)
- verify.md 작성 후 코드 수정하고 verify는 그대로 두는 행위 (stale)
