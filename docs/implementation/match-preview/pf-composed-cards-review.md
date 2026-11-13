# PF-R-CARDS — 새 구성본 run의 카드 복구 **독립 확인**

작성: 2026-11-12 KST. 담당: DeepSeek 독립 검토 워커(PF-R-CARDS). 실제 모델 `deepseek-ai/deepseek-v4.1-flash-1017`(dsh-tui, Max 유지).
범위: 지시대로 `frontend/src/lib/api/preview.ts`·`previewView.ts`의 구성본 선택행 연결과 `MatchPreviewBody.test.ts` 신규 4건만. 다른 frontend 4파일은 별도 검토자 담당이라 보지 않았다. 이전 배당 검토는 되풀이하지 않았다.

## 판정: **요구사항 위반 없음**

| 수용 기준 | 판정 | 근거 |
|---|---|---|
| 새 run(reader 5섹션·자기 section-results는 odds 1행·구성본 items는 원 run 4행)에서 **선택된 result_id/run_id만** 연결 | 충족 | `loadComposedSections`가 `local`에 이 실행 `workflow_id`만 담고, `wanted`는 `result_id`·`run_id`가 있고 `!local.has(section_id)`인 항목만 고른다(`preview.ts:129-152`). 원 실행 행에서 `candidate.section_result_id === item.result_id`인 행만 채택(`:172-179`) |
| **같은 source run 1회 GET** | 충족 | `new Set(wanted.map(item => item.run_id))` → 실행별 1회, `sourceRunId === runId`는 건너뛴다(`:155-168`). 검사가 `filter(call[0]===OLD_RUN).length === 1`로 고정(`test:483`) |
| **임의 최신·선택 밖 행 0** | 충족 | 최신/최대 버전을 고르는 `reduce`·`sort` 없음. 선택 행 미발견 시 `missing`에 사유만 남기고 그 섹션은 fallback(`:181-189`). 병합도 `merged[row.workflow_id]`가 있으면 건너뛰어 이 실행 행을 덮지 않는다(`previewView.ts:617-630`) |
| **조회 실패 = 본문 fallback + 진단** | 충족 | 통신/HTTP 실패 → `composed_error`(`preview.ts:139-141`), 구성본 없음 → `reason`(`:143-148`), 행 미발견 → 사유 문장(`:181-189`). 화면은 `MISSING_COMPOSED_PREFIX` + 사유를 `missing`에 넣고(`previewView.ts:683-684`) 본문은 reader 블록 유지(`:495-521`). 실제 렌더 자리는 기존 `preview-missing`(`PreviewPanel.vue:658-659`, 무변경 파일) |
| **사진·카드·AI 제목 1회·배당 3행 유지** | 충족 | 신규 검사 1건이 사진 URL 2건·`mpv-prediction__score`=`2:0`·`mpv-odds__cells` 3개·제목 `AI 경기 전망`/`주목 선수` 각 1회를 고정(`test:457-484`). 인용한 클래스는 실제 템플릿에 존재(`MatchPreviewBody.vue:199,331`) |
| **불필요 조회 0** | 충족 | reader 섹션 중 이 실행 행이 없는 것이 있을 때만 구성본을 부른다(`preview.ts:135-136`). 4번째 신규 검사가 `composition` 미호출을 고정(`test:525-533`) |

## 보고서 주장 ↔ 실제 대조

| 보고서 | 확인 |
|---|---|
| `PreviewRunData`에 `composed_sections`·`composed_error` 추가 | 사실(`preview.ts:63-65`). 두 필드 참조는 이 2파일 안에만 있고 `.vue` 참조 0 → 다른 4파일 미편집 주장과 일치 |
| `getPreviewRun`은 GET만 | 사실. `preview.ts`에 `method:` 지정 0(기본 GET), 추가 호출은 `composition`·`sectionResults`뿐이며 둘 다 GET(`api.ts:136,236-240`) |
| 응답 키 정합 | 사실. 구성본 item 키(`section_id`/`result_id`/`run_id`)와 섹션 행 키(`section_result_id`/`run_id`/`workflow_id`)가 backend 투영(`store.py:516`,`bundle_pipeline.py:1849-1863`)과 일치. `structured`는 `include_structured=true` 기본으로 source run 응답에 실린다(`preview_admin.py:1115-1125`) |
| 검사 37건(8+21+8) | `it()` 개수 8/21/8로 일치. 파일 mtime(21:55~21:58)이 보고 이후 그대로라 실행 증거를 재사용했다 — 새 vitest 0 |
| typecheck 오류 8건은 기존 | `preview.ts(16,10)` 미사용 import는 이번 추가 줄이 아니라 원래 있던 줄이며, 직전 라운드 기록(`pf-reuse-ui-report.md:92`)과 같은 항목이다. 새 typecheck 0 |

## 참고(비차단, 이번 수정의 결함 아님)

1. **정확성 검사는 단일 후보 위에서만 성립**: 원 실행 대역이 섹션당 행 1개만 주므로, "최신 행을 고르지 않는다"를 **반증으로** 고정하진 않는다. 코드상 분기는 명확하다(위 표 참조).
2. **reader가 없으면 구성본 조회를 건너뛴다**(`preview.ts:135`). 이번 관측 run은 reader가 5섹션이라 해당 없음. 지시대로 가상 조합을 확장하지 않고 기록만 한다.
3. **진단 펼침 시 구성본 GET 1회 추가**: `toggleDiagnostics`가 기존 `getPreviewComposition`을 따로 부른다(`PreviewPanel.vue:441-442`, 무변경 파일). 이는 source run GET이 아니며 이전 동작 그대로다.

## 실행하지 않은 것

추가 vitest·typecheck·실제 HTTP·DB·서버·브라우저·모델·제품 편집·새 재현 코드 **0**. 전체 재검토·범용 강화·과거 backend 후보 재개 0. 실제 화면 확인은 root 담당이다.

READ-ONLY CONFIRMED — 제품·테스트 파일을 수정하지 않았다.
EDITING STOPPED
