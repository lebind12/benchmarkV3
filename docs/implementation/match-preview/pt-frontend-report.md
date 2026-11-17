# PT-FRONTEND B 보고 — 기존 프리뷰 탭의 기간 수집·다경기 생성·저장 문서

작성: 2026-11-17 KST. 담당: DeepSeek 구현 워커 B (Orca term_8c44b024).
Task `task_d53774e7c32d` / Dispatch `ctx_3ca9d129002c`.

기준 SHA: integration `07e6cdc0f9c174b08337fcded81fb6f90f03bc42`, worktree
`/Users/woolee/orca/workspaces/benchmark/preview-test-ui`.

실제 모델: 세션 메타데이터에서 확인한 `provider=hive`,
`model=deepseek-ai/deepseek-v4.1-flash-1017`, `reasoningEffort=high`
(`~/.dsh/sessions/.../68188d24-…/session.v4.jsonl.zstd`의 `model/selection` 이벤트).
모델을 바꾸지 않았고 다른 백엔드로 대체하지 않았다.

적용한 스킬·원칙: `.agents/skills/poteto-mode/SKILL.md` 전문,
`playbooks/feature.md`, `typescript-best-practices/SKILL.md`,
`principle-model-the-domain`, `principle-laziness-protocol`,
`principle-test-behavior-not-implementation`. 적용이 바꾼 결정은 §6에 적었다.

---

## 1. 결과 요약

기존 `/admin?tab=preview` 화면을 그대로 사용자 확인 환경으로 두고, 그 안쪽 위에
기간 수집 → 다경기 생성 → 저장 문서 열기 흐름을 붙였다. 새 진단 전용 페이지나 새
라우트는 만들지 않았고, `MatchPreviewBody`는 수정하지 않았다.

이번 작업에서 **실제 수집·실제 생성·실제 AI 호출은 0회**다. 아래 통과는 모두 모의 HTTP
대역에서 확인한 UI 동작이며, 실제 수집/생성이 성공했다는 근거가 아니다.

## 2. 변경 파일

B 소유 파일만 수정했다.

- `frontend/src/components/management/PreviewPanel.vue` — 기존 단일 경기 흐름 보존,
  시험 영역 마운트, 저장 불일치 섹션 차단과 원문 접힌 진단.
- `frontend/src/components/management/PreviewPanel.test.ts` — 직접 영향 사례 4개 추가.
- `frontend/src/components/management/PreviewTestPanel.vue` (신규) — 후보 선택, 기간·대상
  안내, 수집 실행·추적, 다경기 순차 생성, 경기별 생성/저장 분리 표시, 문서 열기.
- `frontend/src/components/management/PreviewTestPanel.test.ts` (신규) — 11 사례.
- `frontend/src/lib/api/previewTest.ts` (신규) — 수집 시험 API 클라이언트와 경계 파싱.
- `frontend/src/lib/api/collectionProxy.ts` (신규) — 수집 접두사 전용 프록시 규칙.
- `frontend/src/lib/api/collectionProxy.test.ts` (신규) — 프록시 4 사례.
- `frontend/src/lib/api/preview.ts` — `generatePreview`에 선택 `requestId` 전달.
- `frontend/src/lib/api/previewView.ts` — `storageMismatchSections`, `withoutBlockedSections`.
- `frontend/src/features/match-preview/api.ts` — `runBundle`에 선택 `request_id` 본문.
- `frontend/vite.config.ts` — 수집 접두사만 선택 환경변수로 프록시, 미설정 시 503.

`Plans.md`, backend, alembic, 기존 테스트 서버는 건드리지 않았다.

## 3. 사용자 흐름

1. 후보 목록에서 가까운 두 경기를 기본 선택하고 KST 킥오프·리그·시즌·경기 번호·추천
   순위를 본다. 세 번째를 고르면 가장 오래된 선택이 빠진다(수집 API가 정확히 두 경기).
2. 기간·활성 대상·범위 안내를 서버 응답 그대로 확인한다. 부상 자료(`/injuries`)가 이번
   수집에서 갱신되지 않는다는 문장을 표 위에 고정했다.
3. '기간 지정 수집'을 누르면 수집만 실행하고 상태를 GET으로 따라간다. 종료가 확인되면
   폴링만 멈춘다. **생성은 호출하지 않는다.**
4. '선택 경기 프리뷰 생성'을 누르면 고른 순서대로 한 경기씩 생성한다. 첫 경기가 실패해도
   다음 경기를 계속한다.
5. 표에서 경기별로 생성 응답, 저장 판정, 문서 열기를 따로 본다. 저장 판정은 받은 실행
   ID로 `getPreviewRun`을 다시 읽어 판단하며, 생성 성공 표시와 다르다.
6. '저장된 문서 보기'는 같은 실행을 GET으로 연다. 주소(`previewRun`)에 남으므로
   새로고침해도 같은 문서가 열리고 POST는 나가지 않는다.

## 4. 직접 명령과 결과

`node_modules`는 기존 설치를 재사용하려고
`player-section-integration/frontend/node_modules`를 이 워크트리에 심볼릭 링크했다(패키지
설치·업그레이드 없음, `frontend/node_modules`는 gitignore 대상).

| 명령 | 결과 |
|---|---|
| `vue-tsc --noEmit` (tsconfig.app) | exit 0, 오류 0 |
| `vue-tsc --noEmit -p tsconfig.node.json` | exit 0, 오류 0 |
| `vitest run src/components/management/` | 36 통과 (PreviewTestPanel 11, PreviewPanel 25) |
| `vitest run src/lib/api/` | 4 통과 (collectionProxy) |
| `vitest run src/components/home-preview/MatchPreviewBody.test.ts src/features/match-preview/PlayerSectionStorage.test.ts src/features/match-preview/BundlePanelAdapters.test.ts` | 15 통과 |
| `vitest run` (전체) | 65 파일 중 13 실패 / 450 중 58 실패 |

전체 회귀 실패 13 파일·58 사례는 **기준 워크트리
`player-section-integration`에서 같은 명령으로 동일하게 재현**됐다(13 파일 / 58 사례).
내가 추가한 19 사례는 그 안에서 전부 통과한다. 이 실패들은 `FixtureSelector`,
`PreviewMetricsView`, `RunInspector`, `R4PanelAndBody` 등 인증·네트워크 mock 미연결
계열이며 이번 변경과 무관하다.

`PreviewPanel.test.ts` 실행 시 `getPreviewRun`에서 `stderr`로
`TypeError: Cannot read properties of undefined (reading 'ok')`가 한 번 찍힌다. 이는 기준
워크트리에서도 동일하게 나오는 기존 현상(대역이 세 GET을 모두 예약하지 않은 한 사례)이며
해당 사례는 통과한다.

## 5. 수용 기준별 근거

| 요구 | 처리 | 근거 |
|---|---|---|
| 새로고침 GET-only | 주소의 `testFixtures`/`testRuns`/`testCollection`을 GET으로만 복원, POST 0 | `PreviewTestPanel.test.ts` "새로고침 복원은 GET만…", `previewRun` 복원은 기존 사례 유지 |
| 첫 경기 실패 후 다음 진행 | 생성 루프가 경기별 실패를 상태로 남기고 계속 | "첫 경기가 실패해도 두 번째 경기를 계속 진행한다" |
| 수집 후 자동 생성 금지 | 종료 확인 함수가 폴링만 멈춤, 생성 호출 없음 | "수집이 끝나도 생성 POST를 보내지 않고…" (POST 1건 유지 확인) |
| `storage_mismatch` 정상 렌더 차단 | 해당 섹션 본문·카드를 투영에서 제거, 문서 위 경고 + 접힌 원문 | `PreviewPanel.test.ts` "불일치 섹션은 정상 문서로 그리지 않고…", `withoutBlockedSections` 사례 |
| 기존 프리뷰 보존 | 단일 경기 번호 확인·생성·이력·진단·재생성 경로 손대지 않음 | 기존 21 사례 전부 통과 + 신규 4 사례 |
| 더블클릭·중복 방지 | 단일 경기 버튼 disabled 유지, 다경기 루프는 실행 중 재진입 차단 | 기존 더블클릭 사례, `canGenerateSelection` |
| request_id 보존·명시적 재시도 구분 | 통신 실패 재전송은 같은 값, 새 실행은 새 UUID | "응답을 못 받은 요청의 재전송은 같은 request_id…" |
| 늦은 응답 무시 | 경기별 순번 비교 | "붙잡힌 이전 요청의 응답이 늦게 도착해도…" |
| 저장 재조회 | 같은 실행 ID만 채택, 경기·run 불일치는 `unknown` | "저장 조회가 실패한 경기는 저장 성공으로 표시하지 않는다" |
| 수집 전용 프록시 | 접두사만 별도 대상, 미설정은 503 | `collectionProxy.test.ts` 4 사례 |
| `/injuries` 미갱신 명시 | 표 상단 고정 문장 | 첫 사례에서 `/injuries` 문구 확인 |

A가 인계한 run 상세 매핑(19:53·19:58 메시지)을 반영했다. `counts_kind`가
`processing_units`면 수량을 "처리 단위"로 적고, `legacy_unknown`이면 `미상`으로 두어 0으로
채우지 않는다. 실제 수집 경기 목록과 대상 `last_sync`는 응답에 없으므로 표시하지 않으며,
생성 대상 2개를 수집 경기 수로 대신 쓰지 않는다.

## 6. 원칙이 바꾼 결정

- **Model the Domain**: 경기별 상태를 `idle | generating | saved | failed` 판별 유니온으로
  두었다. "실행 ID는 있는데 저장 판정이 없는" 상태를 표현할 수 없게 만들어, 생성 성공을
  저장 성공으로 읽는 경로를 타입 수준에서 없앴다. 불리언 여러 개를 두는 대신 이 구조를
  골랐다.
- **Laziness Protocol**: 새 페이지·새 라우트·별도 저장소를 만들지 않고 기존
  `PreviewPanel` 안에 한 컴포넌트를 붙였다. `request_id`도 기존 실행 저장/잠금 계약을
  그대로 쓰고 새 표를 만들지 않았다.
- **Boundary Discipline**: 서버 응답 해석을 `parseCandidates`/`parsePlan`/`parseRun` 한
  곳으로 모으고, 안쪽 컴포넌트는 파싱된 타입만 받는다. 해석 실패를 빈 목록으로 바꾸지
  않고 사유를 그대로 올린다.
- **Test Behavior, Not Implementation**: 대역을 `authenticatedFetch` 한 곳에만 두어
  실제 모듈의 경로·본문·정규화를 그대로 실행했다. 검사는 화면에 보이는 문구와 나간 요청
  본문을 본다.

## 7. 미검증·남은 일

- 실제 수집 실행, 실제 두 경기 생성, 실제 DB 재조회, 실제 모델 호출은 **하지 않았다**.
  위 모든 통과는 모의 HTTP 대역 근거이며 실수집/실AI 근거가 아니다.
- A의 최종 backend 구현(후보·계획·수집 시작·목록 GET)이 이 워크트리에 없으므로 실제
  응답과의 대조는 C(통합)에서 필요하다. 특히 목록 envelope는 A가 `active/items/limit`로
  확정했으나 이 화면은 단건 `GET /runs/{id}`만 쓰므로 영향 없다.
- 수집 대상별 실제 경기 목록과 `last_sync`는 서버가 주지 않아 화면에 없다. A가 필드를
  추가하면 그때 연결한다.
- 서버 재시작·5173/38000 반영·프록시 환경변수 실설정·브라우저 화면 확인은 이번 배정
  범위 밖이다(C 담당).
- `storage_mismatch` 차단은 이 화면의 문서 wrapper에서만 적용된다. 홈 공개 문서와 다른
  관리 화면의 투영은 바꾸지 않았고, 그쪽 동작은 이번에 확인하지 않았다.
