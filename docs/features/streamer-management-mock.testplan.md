# 관리 목업 — 테스트 플랜

정본: [spec](streamer-management-mock.spec.md), [개발 방향](streamer-management-mock.devplan.md). 이번 범위는 L1/L2. L3는 BE 구현 후 별도이며 이번 통과로 표시하지 않는다.

| ID | 레이어 | 시나리오 | 검증 |
|---|---|---|---|
| M01 | L1/L2 | 개발 경로 진입·4탭·query 복원 | 기본 targets, execution/history/translations 직접 진입, 잘못된 tab 정상화, 샘플/공통 영향 안내 |
| M02 | L2 | 기본 production 경로/실 API 분리 | prod build 기본 route 미등록, 목업 요청은 전용 namespace, 실제 admin/backend/외부 API 쓰기 0, auth key 불변 |
| M03 | L1/L2 | target 검색·활성 필터·0건 | 이름/ID 검색과 필터, 전체 0건/검색 0건 구별, reset/해제 복귀 |
| M04 | L1/L2 | target 추가·동일 대상 갱신 | 최신 2개 실제 시즌, 0/음수/소수 제한 거부, 동일 league+season 중복 row 없음 |
| M05 | L1/L2 | 기존 target 편집·제한 해제 | 현재 옵션 복원, 10→빈값/null 저장, reload 유지, 원래 ID 유지 |
| M06 | L1/L2 | 활성·대상 제외 확인 | 활성 변경, 취소 시 유지, 확인 시 설정만 제외, 기존 적재 데이터 삭제 안내와 혼동 없음 |
| M07 | L1/L2 | target 선택→실행 | 선택 IDs 유지, inactive/미선택 차단, initial/refresh 설명·snapshot·확인 후에만 생성 |
| M08 | L1/L2 | 실행 진행·중복 | 단계·진행량·로그 변화, 진행 중 새 실행 409/기존 run 이동, 타깃별 수와 요약 일치 |
| M09 | L1/L2 | 실행 취소 | cancel 요청/완료, 이미 저장>0·미처리>0 유지, 이후 진행 중단, 이력 기록 |
| M10 | L2 | 진행 중 reload/탭 이동 | 동일 run ID 복원, 이력/활성 연결, UI 이탈 시 polling 중단, 재진입 progress 복원 |
| M11 | L1/L2 | 부분 실패·중단·재실행 | failure scenario로 terminal 상태 확인, 실패 대상만 실행 탭에 전달, 즉시 실행하지 않음, parent 연결 |
| M12 | L1/L2 | 이력 필터·단건·7일 | 상태/이름/날짜 필터, 로그·target별 저장/실패/미처리, active run prune 제외, 필터 0건과 오류 구별 |
| M13 | L1/L2 | 4종 번역 검색·필터 | 리그/팀/선수/감독, 원문/한국어/short 검색, 번역/미번역(짧은 이름 제외), 동명이인 식별 |
| M14 | L1/L2 | 번역 저장·상태·이력 | name/short 저장·번역 상태 자동 반영, version 증가·편집자/시각·before/after, 원문 불변 |
| M15 | L1/L2 | 사람의 NULL | 한글 공백→null·원문 fallback·보호 안내, name/short 각각 의도 보존 |
| M16 | L1/L2 | 번역 409 충돌 | 편집 draft 유지, current와 비교, 재검토/재저장 후 version 일치, 조용한 overwrite 없음 |
| M17 | L1/L2 | 로드/저장 오류·초기화 | 503 오류·다시 시도·입력 보존·정상 복귀, reset은 mock key만 삭제/복원 |
| M18 | L1 | 깨진 storage·불가 storage | parse 에러로 앱 중단 없음, 초기값 복구/복원 한계 안내, auth/site storage 보존 |
| M19 | L2 | 키보드·dialog | label/포커스, Enter 동작, Escape 닫기, focus trap/원래 버튼 복귀, toast/status 접근성 |
| M20 | L2/시각 | desktop/mobile/light/dark | 1440×900 및 390×844, root 가로 넘침 없음, 4탭/표/편집·확인 버튼 접근, 텍스트 잘림/겹침 없음 |

## 자동화 구성

- Vitest: `frontend/tests/unit/...managementMock*.spec.ts`. state/handler의 validation·진행/취소·버전 경쟁은 가상 시계와 메모리/localStorage fixture로 검증한다. UI는 MSW node server 또는 API mock을 사용하고 테스트마다 storage/worker/timer를 정리한다.
- Playwright: `frontend/e2e/streamer-management-mock.spec.ts`. 기존 사용자 5173 서버를 유지하고 전용 5186 config의 로컬 mock 경로로 진입한다. 초기화 후 주요 target→실행→취소→reload→이력 흐름과 번역 conflict 흐름을 검증한다. real API에 대한 request 감시를 두고 VITE_BACKEND_URL이 있더라도 관리 mock 요청 origin/path가 로컬 전용 namespace인지 확인한다.
- 모의 완료를 기다리는 실제 장시간 sleep 대신 API scenario 또는 clock 제어를 활용한다. 테스트가 전용 storage만 정리하고 authUser/mockRole을 추가·변경하지 않는지 확인한다.
- 파일 경로·명령·통과 수·실행 URL·screenshots 또는 시각 확인 viewport를 evidence로 보고한다. 실패/skip을 통과로 표현하지 않는다.

## BE 이후 L3 후속 항목(이번 실행 제외)

실제 JWT/role·DB 실행 복원/취소·advisory lock·최신 2시즌/공통 한도·번역 감사/인간 보호·실제 번역 조회 반영은 이 목업 테스트로 입증되지 않는다. FE 평가 후 endpoint-request와 zod response schemas를 확정하고 격리 BE와 L3에서 검증한다.

## 평가 반영 검증 (2026-10-25)

- DB 조회/최신화 확인·진행·건수·재조회·시각 유지·시즌 선택.
- 실패 이력의 오류 기본 필터, 원인별 통계, 원문 펼침, 대상·재시도 표시, 원인 필터 해제.
- 한국어 이름 유무 기반 두 상태, 짧은 이름 누락 허용, 검수 완료 체크 제거.
- 구조화 코드/과거 제한 패턴/미분류/원문 불변/재시도 중복 발생 집계의 unit 검증.
