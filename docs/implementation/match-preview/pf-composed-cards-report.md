# PF-F-CARDS — 새 구성본 run의 카드 복구 (근거 보고)

작성: 2026-11-12 KST. 담당: DeepSeek 구현 워커(Orca `dsh-tui`, 실제 모델
`deepseek-ai/deepseek-v4.1-flash-1017`, 사용자 설정 추론 강도 Max 유지).

## 1. 관측된 결함

root가 실제 관리자 화면에서 확인한 새 run `493ef4a9-0e14-4436-8a97-d6de7ce034a7`:

| 항목 | 새 run 결과 |
|---|---|
| 배당 3행 + `observedAt` | 정상 |
| 나머지 네 섹션 | reader 본문만 남아 **사진 0장 · 일반 본문 fallback · AI 제목 중복** 재발 |
| `/section-results` | 새 배당 1행뿐 |
| 구성본의 다른 4행 | 원 run `d96fe824…`에서 선택됨 |
| 원 run 자체 | 사진 6장 정상 |

즉 재사용 재생성으로 만든 run은 **자기 새 결과 1건만** 저장하고 나머지 섹션은 구성본이
부모 실행 결과를 가리킨다. 화면은 `run_id`의 `/section-results`만 읽었으므로 그 섹션들의
`structured`(선수·부상·매체·전망)를 몰라 카드를 그리지 못했다. 카드가 없으니 본문 fallback이
그려지고 AI 제목이 다시 나왔다. **서버·저장 자료 문제가 아니라 읽기 연결 누락**이다.

## 2. 수정 (2파일 + 1 검사파일)

| 파일 | 변경 |
|---|---|
| `frontend/src/lib/api/preview.ts` | `PreviewRunData`에 `composed_sections`·`composed_error`(선택) 추가. `getPreviewRun`이 **이 실행 행이 없는 섹션이 있을 때만** 구성본을 조회하고, 선택된 결과 행을 원 실행에서 읽어 함께 돌려준다(`loadComposedSections`) |
| `frontend/src/lib/api/previewView.ts` | `withComposedRows()`로 구성본 행을 **이 실행 행이 없는 섹션에만** 합치고, 조회 실패·행 미발견은 `missing`(진단)에 `MISSING_COMPOSED_PREFIX`로 남긴다 |
| `frontend/src/components/home-preview/MatchPreviewBody.test.ts` | 대표 검사 4건 추가(카드 복구·행 미발견·조회 실패·불필요 조회 없음) |

`PreviewPanel.vue`·`PreviewPanel.test.ts`·`SectionRegenerationPanel.vue`(PF-REUSE 4파일)는
**이번 작업에서 편집하지 않았다**(아래 §5 참고). backend·API 계약 신설·캐시·범용 리팩터링 없음.

### 2-1. 지킨 제약

| 지시 | 구현 |
|---|---|
| 선택된 ID만 정확히 연결 | 구성본 `items` 중 `result_id`·`run_id`가 있고 이 실행 행이 없는 섹션만 대상. 원 실행 행에서 `section_result_id === item.result_id`인 행만 채택 |
| 임의 최신 교체 금지 | 같은 섹션의 다른 버전·최신 행을 찾지 않는다. 선택 행이 없으면 그 섹션은 fallback 유지 |
| 재생성·원 run 변경 금지 | POST 없음. `getPreviewRun`은 GET 4종(reader·section-results·detail·composition)만 |
| 동일 source run 1회 GET | `runIds`를 `Set`으로 접고 `Map`에 캐시. 검사가 `filter(call[0]===OLD_RUN).length === 1`로 고정 |
| 선택 ID 없는 행 혼입 금지 | `result_id`/`run_id` 없는 항목은 대상에서 제외 |
| 조회 실패 = 본문 fallback + 진단 | `composed_error`를 `missing`에 남기고 본문은 reader 블록 그대로. 화면은 `preview-missing`(기존 진단 자리)에서 보인다 |
| 불필요 조회 없음 | 이 실행 행이 모든 섹션을 채우면 `composition` 호출 0회 |
| 카드 유지 | 사진 URL 2건·AI 카드 점수 2:0·배당 3행·AI/주목 제목 각 1회를 검사로 고정 |

## 3. 검사 명령과 실제 결과

```
cd frontend && npx vitest run \
  src/components/home-preview/MatchPreviewBody.test.ts \
  src/components/management/PreviewPanel.test.ts \
  src/features/match-preview/MatchPreview.test.ts
→ Test Files 3 passed (3) / Tests 37 passed (37)
   MatchPreviewBody 8 (기존 4 + 신규 4), PreviewPanel 21, MatchPreview 8

cd frontend && npx vue-tsc -p tsconfig.app.json --noEmit
→ exit 2, 오류 8건 — 모두 기존(§4). preview.ts 오류는 이번에 추가한 줄이 아니라
  원래 있던 미사용 import(16행 `previewRequest`)다.
```

**회귀 확인(검사가 실제 결함을 잡는지)**: `withComposedRows` 적용 줄을 일시 제거하면
핵심 검사가 실패(`1 failed | 7 passed`), 되돌리면 8 passed. 즉 이 검사는 이번 결함을 직접 잡는다.

추가 검사와 수용 기준:

| 검사 | 수용 기준 | 실패하면 사용자에게 생기는 일 |
|---|---|---|
| 원 실행 행을 이어받아 사진 2건·AI 카드·배당 3행, AI/주목 제목 각 1회 | 새 run에서도 기존 카드·사진·AI 제목 1개·배당 3행 유지 | 사진이 사라지고 같은 본문을 fallback 문단으로 다시 읽는다 |
| 선택 행 미발견 → reader 본문 유지 + `missing`에 사유 | 조회실패/미발견은 fallback + 진단 | 왜 카드가 없는지 알 수 없고 본문만 남는다 |
| 구성본 조회 503 → 본문 유지 + 사유 기록 | 조회실패는 기존본문 fallback+진단 유지 | 구성본 장애가 본문 유실로 번진다 |
| 이 실행 행이 전 섹션을 채우면 구성본 GET 0회 | 불필요 조회·범용 캐시 금지 | 평범한 run마다 불필요한 GET이 붙는다 |

## 4. 기존 타입 오류 8건 (확대 수정 금지, 그대로)

```
src/components/management/PreviewPanel.test.ts(522,771,784,838,870,933)  TS2353  ← 6
src/features/match-preview/BundleGenerationPanel.test.ts(57)             TS2339  ← 1
src/lib/api/preview.ts(16,10)                                            TS6133  ← 1
```

직전 라운드와 동일한 8건이며 이번 변경으로 늘지 않았다. `npm run type-check`(파일 0개 검사)는
근거로 쓰지 않았다.

## 5. 소유 범위 준수 메모

지시는 소유 파일을 `preview.ts`·필요 시 `previewView.ts`/실제 타입·기존 직접검사로 한정하고
완료한 PF-REUSE 4파일과 `PreviewPanel.vue`/`PreviewPanel.test.ts`를 다시 편집하지 말라고 했다.
이번 작업 중 진단 문구를 `PreviewPanel.vue`에 직접 넣는 안을 시도했다가 **되돌렸고**(현재
`composed` 참조 0건), 대신 기존 진단 채널(`missing` → `preview-missing`)로 옮겼다. 새 검사도
`PreviewPanel.test.ts`가 아니라 내 소유였던 `MatchPreviewBody.test.ts`에 두었다. PF-REUSE 배선
(`:bundle-id`, `:selected-result-ids`, `@regenerated`, 열기 버튼)은 그대로 남아 있다(21 tests).

## 6. 남은 일

- **실제 화면 확인은 root 담당**이다. 이번 검사는 고정 입력 + jsdom이며, 추가 모델/API 실행을
  하지 않았다. 새 run `493ef4a9…`의 저장본 GET으로 최종 확인하는 절차는 root가 수행한다.
- 검사 입력은 run `493ef4a9`(새 run, 배당 1행)와 `d96fe824`(원 run, 4섹션 구조화 값)의 저장
  모양을 옮긴 것이며, 실제 응답 원문을 이 세션에서 다시 조회하지는 않았다(HTTP 금지).
- 배당 실제 값 공급·부상 이름/사진의 **저장 payload** 반영은 범위 밖이다.

## 7. 실행하지 않은 것

backend·API 계약 신설·캐시·광범위 리팩터링·실제 HTTP·브라우저·모델·서버·DB 변경 0,
전체 빌드·전체 suite 0, 커밋 0, 하위 워커 0. 임시 파일은 `/tmp`에만 두고 지웠다.

EDITING STOPPED
