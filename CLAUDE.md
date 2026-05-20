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
9. **Stage 5b**: `bash scripts/run_verify_cross.sh N` → verify-cross.md → commit (`chore(phase-N): verify-cross`)
10. **Stage 5c**: 두 verify 종합 판정. FAIL이면 RE-CODE or RE-PLAN.
11. **Stage 6**: summary.md → commit (`chore(phase-N): summary`)
12. `git push` → 작업 종료. summary 내용을 Human에게 보고.

## 커밋 메시지 규칙 (Conventional Commits)

- `chore(phase-N): plan` — Stage 1 직후
- `chore(phase-N): debate` — Stage 2 직후 (Codex 결과 + 너의 commit)
- `chore(phase-N): challenge` — Stage 3 직후
- `feat(phase-N): <기능>` — Stage 4 본 구현
- `test(phase-N): <대상>` — 테스트 추가
- `chore(phase-N): verify` — Stage 5a
- `chore(phase-N): verify-cross` — Stage 5b
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
- **debate.md, verify-cross.md 직접 작성** — 이건 Codex의 산출물이다
- `bash scripts/run_*.sh` 호출 생략
- self-score를 95+로 매기되 evidence가 부실한 경우 (Planner가 reject한다)
