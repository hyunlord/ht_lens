# ht_lens

PDF(한/영) 문서를 페이지 레이아웃과 이미지 위치를 유지하면서 번역하고, 블록 단위로
클릭해 AI 설명·질문·꼬리질문을 주고받으며, 그 대화를 핀과 함께 저장·관리할 수
있는 **로컬 도구**.

## Status

🟢 **Phase 0 (skeleton) 완료** — 도메인 코드 없음, CI green.

다음: Phase 1 (PDF Extractor).

## Documents

- [`ROADMAP.md`](ROADMAP.md) — 전체 phase 계획과 DoD
- [`WORKFLOW.md`](WORKFLOW.md) — 작업 사이클 (Worker / Critic)
- [`CLAUDE.md`](CLAUDE.md) — Claude Code 행동 원칙
- [`AGENTS.md`](AGENTS.md) — Codex CLI 행동 원칙

## Prerequisites

- Python 3.11
- [`uv`](https://docs.astral.sh/uv/) — 패키지/가상환경 매니저
- [`codex` CLI](https://github.com/openai/codex) — 워크플로우 cross-review 자동화
  ```bash
  npm install -g @openai/codex
  codex  # 첫 실행 시 인증
  ```

## Setup

```bash
make install   # uv sync + pre-commit hook
```

## Commands

| 명령              | 설명                                    |
| ----------------- | --------------------------------------- |
| `make install`    | 의존성 설치 + pre-commit hook           |
| `make fmt`        | ruff format                             |
| `make lint`       | ruff check + mypy strict                |
| `make test`       | pytest 전체                             |
| `make test-fast`  | pytest (`-m "not llm and not slow"`)    |
| `make check`      | fmt + lint + test-fast                  |
| `make clean`      | 캐시/커버리지 정리                       |

## Directory layout

```
ht_lens/
├── src/ht_lens/           # 패키지 본체 (Phase 1+에서 채워짐)
├── tests/                 # pytest (unit / integration / fixtures)
├── scripts/               # check.sh, run_debate.sh, run_verify_cross.sh
├── prompts/               # Codex 시스템 프롬프트
├── .claude/phases/        # phase별 산출물 (plan/debate/challenge/verify/summary)
├── docs/phases/           # phase별 스크린샷·문서
└── data/                  # 로컬 데이터 (gitignored)
```

## Workflow

각 phase는 다음 사이클을 따른다 (`WORKFLOW.md` 참조):

```
plan → debate(Codex) → challenge → code → verify → verify-cross(Codex) → summary
```

산출물은 `.claude/phases/phase-N/`에 누적된다.
