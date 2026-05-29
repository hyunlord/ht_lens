# Phase 8a — Challenge (debate 대응)

**Decision: PASS** (계획 정제 후 진행, RE-PLAN 아님). 핵심 접근(MinerU subprocess + item-level chunk + content_list ingest)은 건전. Codex 13개 지적 중 9개 수용(계획 수정), 1개 보류(사용자 결정), 3개 부분수용.

## Debate responses

### 1. Over-engineering
- **1.1 ChunkTranslation/ChunkEmbedding 8a 생성 = blast radius** → **accept**. 8a 마이그레이션은 `chunks` + `documents.extractor`/`markdown_path` 만. translation/embedding 테이블은 8b로 연기. 모델도 Chunk만. additive 면적 축소 → guardrail 유리.
- **1.2 동일 DB additive가 마스터플랜 '병행 DB'와 모순** → **보류 (사용자 결정 유지)**. 8a plan 결정에서 사용자가 동일 DB additive 명시 선택 + additive-only guardrail. Planner 결정이라 유지. 격리 우려는 #5.6 마이그레이션 additive-only 테스트로 완화(분리 DB 없이 1.x 무접촉 증명).
- **1.3 extract-mineru sandbox 경로 하드코딩** → **accept**. baked-in 제거; env `HT_LENS_MINERU_BIN` → PATH `mineru` 순 탐색, 없으면 명확 에러.

### 2. Hidden assumptions
- **2.1 Page 재사용 위반 (non-null cols)** → **accept (핵심)**. 8a는 **Page 행 생성 안 함**. `chunks.page_idx`=plain int(pages FK 없음). Page+render는 8c. non-null 위반 회피 + 8a 최소화.
- **2.2 MinerU 출력 경로 하드코딩** → **accept**. out 디렉토리에서 `*_content_list.json` glob 탐색, images dir 상대 발견.
- **2.3 heading=type=header 가정** → **partial (검증 기반)**. sandbox 3.2.1 실측: type=header=running 헤더, 섹션 제목=text+text_level≥2. 매핑 유지 + fixture 잠금 + 방어 처리.
- **2.4 magic number(49850) 검증** → **accept**. pre/post 카운트 스냅샷 delta=0으로 변경.

### 3. Edge cases
- **3.1 malformed "키 부재 graceful" 모호** → **accept**. typed 파서(dataclass) + 명시 동작: page_idx 부재→문서 거부, bbox 부재→`[]`+로그, text None→skip, unknown type→`type='unknown'` 보존(silent drop 금지).
- **3.2 figure 다중 caption/중복 basename/missing** → **accept**. caption 전체 join 보존, dest=`<doc>/images/<basename>`(doc 스코프 격리), 복사 실패 시 문서 롤백.
- **3.3 chrome 필터 오분류 위험** → **partial**. Murphy 실측 근거 유지 + fixture로 필터 집합 잠금 + 튜닝 주석. 과설계 회피.
- **3.4 bbox provenance** → **partial**. 8a는 bbox_json verbatim(MinerU 원좌표)+page_idx=raw provenance 보존. 좌표계 정합은 8c. 저장 좌표공간 docstring 명시.
- **3.5 subprocess 실패 모드** → **accept**. runner: exit code+timeout+content_list 존재·파싱 검증 후 성공 선언, partial=실패.

### 4. Alternative approaches
- 분리 v2 DB → #1.2 보류와 동일(사용자 결정). minimal 8a schema(chunks만) → #1.1 수용. Page 렌더 즉시 → #2.1로 Page 미생성 채택. **typed 파서 경계** → **accept** (dataclass ContentItem in content_list.py).

### 5. Missing tests — **전부 accept**
1. invalid-page-rows → 8a는 page 미생성이므로 "Page 0건 생성" assert.
2. unknown-type 보존(silent drop 금지).
3. missing bbox/caption/None text 처리.
4. runner 경로 discovery(가짜 출력 트리).
5. missing-image 롤백.
6. **migration additive-only diff** (schema pre/post 비교, chunks+documents 컬럼 외 변경 0).

## Plan revisions (after debate)
- 마이그레이션 0005 = `CREATE TABLE chunks` + `documents ADD extractor` + `ADD markdown_path`. 그 외 0 (translation/embedding 8b).
- 모델: Chunk만 추가. Document에 2컬럼. Page 무변경·무생성.
- chunks: id, doc_id(FK documents), page_idx(int, FK 없음), order_idx, type, text_level, bbox_json, content, text_format, img_path, caption.
- runner: env/PATH 탐색 + 경로 glob + subprocess 견고성.
- 파서: dataclass 정규화 + 명시 malformed 동작 + unknown 보존.
- ingest: figure 전체 caption + 격리 경로 + 롤백.
- 테스트: 6종 + additive-only diff + pre/post 스냅샷.

## DoD checklist
| DoD item (ROADMAP 8a) | Status | Evidence (계획) |
| -------- | ------ | -------- |
| doc7 챕터 MinerU 추출 → chunk ingest | planned | sandbox content_list 재사용 ingest → `SELECT COUNT(*) FROM chunks` |
| chunk가 bbox/page/type/latex/caption 보존 | planned | unit+integration assert (verbatim bbox, latex `$$`, caption, page_idx, text_level) |
| figure 이미지 분리 + 경로 | planned | `data/extracts_v2/<doc>/images/` + img_path, 롤백 테스트 |
| 1.x DB 무손상 (병행) | planned | additive-only diff 테스트 + pre/post 카운트 delta=0 |

## Risk register
| Risk | Likelihood | Impact | Mitigation |
| ---- | ---------- | ------ | ---------- |
| 0005가 실수로 1.x 테이블 ALTER | 낮음 | 높음 | additive-only diff 테스트(#5.6) + verify schema diff |
| MinerU 출력 스키마 버전 변동 | 중 | 중 | dataclass 파서 방어 + glob 경로 탐색 + fixture 3.2.1 기준 |
| chrome 오분류(학술 변형) | 중 | 낮음 | fixture 필터 잠금 + 튜닝 가능, unknown 보존 |
| subprocess 부분 실패 | 중 | 중 | exit/timeout/출력 검증 후 성공 선언 |

## Decision
- [x] **PASS → proceed to code** (계획 정제 반영)
- [ ] RE-PLAN
