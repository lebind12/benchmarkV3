# PA-LIVE 실제 생성 및 홈 반영 관측 결과

작성 시각. 2026-11-18 KST  
작업트리. `/Users/woolee/orca/workspaces/benchmark/preview-api-migration` (`lebind12/preview-api-migration`)  
서버 실행 커밋. `4f896a8450834c1a4dd55aaefc971709c7430323` (보고서 직전 커밋 `261b02b6d4530e3cb36b08710d7fff8c037928b7`)  
실행 에이전트·모델. `antigravity / gemini-4-hydrogen-high` (하위 워커 0회, 추가 생성·수집·승인·코드 변경 없음)

## 1. 선행 수집 및 생성 관측 (경기 1557474)

- 고정 관리자 탭(`88b3b45e-8ad6-4031-af56-031b39976c22`, URL `previewRun=00d34c23-a1d6-43d0-b8e2-fe9962184f3b&testCollection=9f980724-568b-4933-a8ff-f72970605e19&testFixtures=1557474&testRuns=1557474:00d34c23-a1d6-43d0-b8e2-fe9962184f3b`):
  - 선행 기간 수집. `9f980724-568b-4933-a8ff-f72970605e19` (`succeeded`, 100%, `55/55` 처리 단위, 실패 0, 기록 1164행, 계획·저장 확인·상세 응답 각 6경기, 미확인 0, `/injuries` 미포함 안내 유지).
  - 단건 생성 관측. `POST /api/v1/admin/preview/bundle-runs` → `200 OK`, 신규 실행 `00d34c23-a1d6-43d0-b8e2-fe9962184f3b` (`맨체스터 시티 vs 풀럼 · 1557474`).
  - 결과 표 상태. `생성 응답 성공 실행 00d34c23-a1d6-43d0-b8e2-fe9962184f3b` · `저장 확인` · `저장된 문서 보기`.

## 2. 관리자 저장 문서 및 진단 확인 (`저장된 문서 보기`, GET 전용)

- 실행 요약(`preview-diagnostics` 열람 결과):
  - `실행 ID`: `00d34c23-a1d6-43d0-b8e2-fe9962184f3b`, `경기 번호`: `1557474`
  - `필수 섹션 본문`: `모두 있음`, `표시 모델에서 비어 있는 항목`: `없음`
  - `storage_mismatch` 경고 배너(`preview-storage-mismatch`) 및 부분 경고(`preview-partial-note`) 없음, `이 실행에는 저장된 구성본이 없습니다.`
  - `저장된 섹션 결과` 5건 모두 `v1 · live · ready` 저장:
    - `section_players` (`주목 선수`)
    - `section_availability` (`부상·결장 영향`)
    - `section_outlook` (`외부 매체 전망`)
    - `section_odds` (`배당 현황`)
    - `section_ai_forecast` (`AI 경기 전망`)
- 본문 및 선수 사진 확인:
  - `AI 경기 전망`, `주목 선수`(맨체스터 시티 요슈코 그바르디올·라얀 셰르키, 풀럼 조슈아 킹·로드리고 무니즈), `부상·결장`(마크 게히, 요아킴 안데르센), `외부 매체 전망`, `배당` 본문 표시 확인.
  - 화면 내 6명의 선수/부상 사진(`요슈코 그바르디올`, `라얀 셰르키`, `조슈아 킹`, `로드리고 무니즈`, `마크 게히`, `요아킴 안데르센`) 모두 `complete=true`, `150x150` 로드 확인(`preview-home-unresolved-note` 비노출). 단 기간 수집에 `/injuries`가 포함되지 않았다는 UI 안내는 그대로 유지됨.

## 3. 공개 GET 및 홈 페이지(`26288558-e6c9-4d49-8301-af0d897562a8`) 대조

- `GET http://127.0.0.1:5173/api/v1/home/recommendations` (`200`, `display_date=2026-11-21`, `items=1`):
  - `1557474` `preview`: `state="partial"`, `served="current"`, `generated_at="2026-11-17T17:52:46.504955+00:00"`, `as_of="2026-11-17T17:52:46.504955+00:00"` (생성 직후 저장된 `00d34c23` 시점과 동일값).
- `GET http://127.0.0.1:5173/api/v1/home/fixtures/1557474/document` (`200`):
  - `status="available"`, `reason=null`, `run_id="00d34c23-a1d6-43d0-b8e2-fe9962184f3b"`, `complete=false`, `saved_at="2026-11-17T17:52:46.504955+00:00"`.
- 홈 페이지(`26288558-e6c9-4d49-8301-af0d897562a8`, `http://localhost:5173/` GET 새로고침):
  - `2026.11.21` 예정 경기 `맨체스터 시티 vs 풀럼` (`21:30 KST`) 표시, `저장 프리뷰 11. 18. 02:52 KST 저장`.
  - 안내 문구: `"필수 섹션(주목 선수·AI 경기 전망) 중 미생성 또는 미승인 항목이 있어 승인된 섹션만 부분 표시합니다."`
  - 홈 실제 노출 섹션: `AI 경기 전망`, `외부 매체 전망`, `배당` 3개 섹션만 표시(`주목 선수`·`부상·결장` 미노출).

### 열린 실행(`00d34c23-a1d6-43d0-b8e2-fe9962184f3b`) 대 홈 공개 문서 섹션 대조

| `workflow_id` | 관리자 열린 실행 `section_result_id` | 홈 문서 `section_result_id` | 홈 반영·승인 구분 | 비고 |
|---|---|---|---|---|
| `section_players` | `8aa0ffaf-a4ad-4d63-8a9d-5e256872e956` | 없음 | **누락 (미승인)** | 필수 섹션. 관리자 본문(`주목 선수` 4명 카드)·진단에서 검토 가능. 사용자 승인 전까지 `complete=false`·`partial` 유지 |
| `section_availability` | `c8a19c2f-4a0e-4ec8-81b0-5281f7f26b4d` | 없음 | **누락 (미승인)** | 선택 섹션. 관리자 본문(`부상·결장` 2명 카드)·진단에서 검토 가능. 사용자 승인 전까지 홈 문서 미포함 |
| `section_outlook` | `6620a3f2-b102-4c13-b418-f1fefe01b030` | `6620a3f2-b102-4c13-b418-f1fefe01b030` | **일치 (승인 반영)** | `section_outlook@0145de693ebdef28`, `body_chars=398` |
| `section_odds` | `31b75881-dda4-4820-9705-830989d05abc` | `31b75881-dda4-4820-9705-830989d05abc` | **일치 (승인 반영)** | `section_odds@49923b1c5dcb467a`, `body_chars=294` |
| `section_ai_forecast` | `6c6b1556-fd30-4b68-9f31-be291be3d913` | `6c6b1556-fd30-4b68-9f31-be291be3d913` | **일치 (승인 반영)** | `section_ai_forecast@c186f27356d4bb80`, `body_chars=443` |

- 관리자 화면 `preview-home-document-status` 문구: `"홈(00d34c23-a1d6-43d0-b8e2-fe9962184f3b)에 열린 결과의 섹션(section_players, section_availability)이 누락되었습니다 · 필수 섹션 부분 반영(complete=false · 홈 섹션 3개)"` — 생성·저장은 5섹션 모두 성공했으나 미승인 섹션 2건 때문에 홈이 부분 반영(`complete=false`) 상태임을 정확히 분리 표시했다.

## 4. 미실행 범위 및 유지 상태

- 미실행 범위. 추가 생성/재생성, 수집 실행, 섹션 승인, 취소, 토큰 추출, 계정 변경, 코드/테스트 수정, 서버 재시작, DB 직접 쓰기 미실시.
- 유지 상태. 백엔드 `38000` (`term_1c294f9c-feb2-4a6a-a547-918bc8e8d9c5`, `PID 38299`), 프론트엔드 `5173` (`term_08a95d29-cd3b-4099-bb48-ec4a546e712f`, `PID 38395`), 수집 `38003` (`term_74737883-30f9-48c9-8d92-e361ddb5fa6a`, `PID 68684`), 관리자 탭 `88b3b45e-8ad6-4031-af56-031b39976c22`, 홈 탭 `26288558-e6c9-4d49-8301-af0d897562a8` 모두 유지 중.
