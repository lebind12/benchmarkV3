# 기간 지정 수집 API 시험 — 실제 호출 전 확인

2026-11-13 05:22 KST 조정자 기록. **실제 수집 POST와 이번 두 경기 생성은 아직0회다.** 이 문서는 사전 읽기 근거이며 실제 수집 성공 보고가 아니다.

## 현재 대상

기존 ADMIN 클라이언트의 targets GET은200이며 target13은 활성 EPL2026, fixture_limit=null, 상세/선수/순위true, scheduler_enabled=false였다. 두 fixture GET도200이며 실제 저장 DB 응답은 아래와 같다.

| 외부 경기 ID | 대진 | 상태 | 킥오프 |
|---|---|---|---|
| 1557470 | Chelsea–Leeds | NS | 2026-11-21T15:00:00Z / 11월22일00:00 KST |
| 1557476 | Tottenham–Ipswich | NS | 2026-11-21T15:00:00Z / 11월22일00:00 KST |

현재 실제 시각에서 두 경기 모두6시간 밖이다. 예정된 수집 기간은11월21일21:30~22일00:00 KST 양 끝 포함, 생성 시간창 예외는 두 ID에만 적용한다. OS/서버 시각과 DB 킥오프는 바꾸지 않았다.

## 실행 서버 반영

현재 PID13279는 `.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000`이다. 해당 서버의 openapi GET에는 `/api/v1/admin/management/runs/preview-test`가 아직 없다. 검토 중인 새 코드를 아직 실행 서버에 반영하지 않았고 재시작도 하지 않았다. 기존 런처는 `scripts/run_benchmark_dev.sh`이며 자동 마이그레이션 없이 기존 환경을 재사용한다.

## 실제 승인 조회

GET `/api/v1/admin/preview/admission`은200·ready=false였다. missing_approval은 section_form/section_availability/section_outlook/section_players/section_synthesis, stale_approval은 빈 배열이었다.

별도 approvals GET에서 기존 승인 기록을 확인했다. section_odds는 active이고, section_availability/outlook/players/ai_forecast에는 pinned 승인이 있으며 superseded로 분류된다. form/synthesis에는 승인 기록이 없다. 즉 “모든 승인이 없다”는 상태가 아니다.

네 pinned 승인과 현재 manifest는 R2/R3/R4/S1의 contract_version이 mp04-section-result-1 대 mp02-1로 다르고 표시된 implementation/prompt 버전은 같았다. 소스의 pipeline.required_workflows는 form/availability/outlook/players/synthesis이고 실제 bundle 대상은 players/availability/outlook/odds/ai_forecast다. 이 차이가 실제 공통 생성의 승인 판정과 연결되는지 읽기 조사를 배정했다. 새 승인을 쓰거나 기존 기록을 변경하지 않는다.

런처의 HOME_PREVIEW_ENABLED 기본값은false다. 실제 프로세스 값은 확인하지 않았으며 새 명시적 시험 요청이 이 기본값에서도 종료 훅으로 이어지는지는 조사 대상이다. 전역 설정을 변경하지 않았다.

## 현재 한계와 다음 실행

엔드포인트 구현자는 합성34 passed를 보고했고 독립 확인은 task_719c25f59bca·ctx_10dd39eab4f0에 배정했다. 승인 판정/명시적 시험 훅의 최소 연결 조사는 task_5b0e53d1d92a·ctx_1a81bf58d729이며 제품 파일은 읽기 전용이다. 실제 호출은 이 근거를 정리하고 필요한 수정의 한정 확인 뒤 진행한다.

관리 수집 목록 GET은 과거 이력을 정리할 수 있어 사용하지 않았다. 기존 인증 클라이언트의 세션 갱신 가능성을 포함하므로 모든 HTTP가 GET뿐이었다고 주장하지 않는다. 수집POST·승인POST·모델 호출·DB 수동 변경은0건이다. 실제 실행 후 이 문서에 수집ID·두 프리뷰ID·수집 상태·최종 결과를 추가한다.

## 05:28 KST 코드 근거와 보완 배정

독립 검토는 기간/두 경기 예외 연결을 확인했으나 입력 소속 검증·경기별 제외 사유·종료 훅의 직접 연결 검사 부족을 지적했다. 보고서의 “시즌 정리 없음” 설명은 조정자의 실제 코드 대조와 달랐다. management_runs.py의 성공 분기는 시험 범위 검사 없이 prune_league_seasons를 호출하고, management.py의 해당 함수는 과거 시즌 행을 DELETE한다. 아직 실제 수집을 하지 않아 이 경로로 삭제된 자료는 없다. 기간 시험에서 이 호출을 제외하도록 보완한다.

읽기 조사에서는 실제 bundle5섹션과 승인 판정의 옛5섹션이 다르고, bundle 저장의 mp04 계약과 현재 manifest의 mp02 비교 축이 어긋나는 것을 확인했다. 또한 전역 HOME_PREVIEW_ENABLED=false이면 명시적 시험의 종료 훅도 생략된다. 기존 승인 기록을 변경하거나 ready를 강제하는 대신 실제 생성 집합·저장 계약·요청별 시험 의도를 맞추도록 같은 구현자에게 task_d6801dc4a3c4·ctx_a421b12be0a3를 배정했다. 세부 범위는 `preview-collection-endpoint-fix-brief.md`이며 실제 호출은 보완과 한정 확인 뒤 진행한다.

## 05:38 KST 보완 인계

여섯 보완 완료와 직접4파일66 passed가 보고됐다. 조정자는 인계와 현재 해시를 확인하고 task_b188b551d002·ctx_ebb9eadbc86f에 한정 수정 확인을 배정했다. 실제 서버는 아직 재시작하지 않았으며 이전 ready=false 조회는 수정 전 서버의 값이다. 새 manifest가 기존 승인5행과 일치하는지는 서버 반영 뒤 approvals GET으로 확인한다. 기존 GET/admission은 옛 파이프라인 판정을 유지하므로, 수집에 쓰는 bundle 섹션 집합의 준비 상태와 혼동하지 않는다. 실제 수집POST·이번 생성은 계속0회다.

## 05:43 KST 서버 반영과 실제 요청1회

별도 DeepSeek의 여섯 보완 수용·66 passed(0.60s, 1회)와 현재7파일 SHA256 일치를 확인했다. 기존 로컬API PID13279에 TERM을 보내 정상 종료하고 같은 `scripts/run_benchmark_dev.sh`를 실행했다. PID9499/실행세션88642의 startup complete를 확인했고 openapi에 새POST가 등록됐다. 설정·자격증명·승인행·마이그레이션은 바꾸지 않았다.

05:43:15 실제 approvals GET에서 기존 다섯 승인 모두approved이며 현재 버전이 승인 버전과 일치했다. 이전 승인ID와 동일하다.

| 섹션 | 승인ID | 일치한 버전 |
|---|---|---|
| players | 228fd0b2-443c-4f6f-94a4-921a79731961 | section_players@174a98077f78af37 |
| availability | 0a661ea9-c4f3-433c-9ce7-0ea585d27b8a | section_availability@7dc7fec4ec7919ac |
| outlook | 1203a932-12d0-4f31-971c-fd1c2a65e667 | section_outlook@0145de693ebdef28 |
| odds | 32a63842-1c72-442b-bbf7-4e22a634d512 | section_odds@49923b1c5dcb467a |
| ai_forecast | 430361ab-ce57-4cc5-8e84-7efd59a4ba2e | section_ai_forecast@c186f27356d4bb80 |

target13 활성·EPL2026·두 경기NS/킥오프도 다시 확인했다. 새승인POST 없이 비교 계산 수정으로 기존 승인이 현재 구성과 일치한 것이다.

기존 ADMIN 클라이언트로 POST `/api/v1/admin/management/runs/preview-test`를1회 호출했다. 입력은 target_ids=[13], fixture_from=2026-11-21T21:30:00+09:00, fixture_to=2026-11-22T00:00:00+09:00, preview_fixture_ids=[1557470,1557476]이다.

- HTTP200, 수집 실행ID: **0178213b-6cf8-4b38-a9d1-2554e4faeee1**.
- created_at/started_at:2026-11-12T20:43:39.614325Z(11월13일05:43:39 KST).
- 응답 status=queued, stage=실행 준비, finished_at=null.
- test_scope에 입력 기간·두 경기ID·같은 수집ID가 저장돼 반환됐다.
- 이 시점은 접수 성공이며 실제 수집·생성 성공은 아직 판정하지 않았다. 후속 조회는 이 실행ID에 한정하고 새POST를 재전송하지 않는다.

## 05:50 KST 첫 실제 실행 종료와 입력 연결 결함

05:49:42 KST에 위 실행이 종료됐다. `finished_at=2026-11-12T20:49:42.137618Z`, 수집 status=succeeded, home_preview.state=finished, collection_status=succeeded, approval_gate=ready, candidates=2, failed/skipped/deferred는 모두 빈 배열이다.

| 경기 | 새 프리뷰 실행 | 실제 결과 |
|---|---|---|
| 첼시–리즈1557470 | e6a78cd9-a32e-4038-86a4-566634cf3845 | live·succeeded·5섹션·전송장부6회·retry0·홈 최신 run_id 일치/complete=true |
| 토트넘–입스위치1557476 | 54c1b9ee-dc40-4f8d-8d89-b5533fc2b62a | live·succeeded·5섹션·전송장부6회·retry0·홈 최신 run_id 일치/complete=true |

실제 수집 로그에 fixtures=6과 상세 처리ID 1557474/1557468/1557476/1557470/1557467/1557471이 남았다. 처리 단위55/55·실패0·저장 처리 합계1164다. 이는 경기55개나 신규 고유행1164개가 아니다. 팀·선수·순위 보조 수집과 upsert가 포함된다. 프리뷰 생성은 위 두 ID에만 이루어졌다.

수집→실제 생성→저장→홈 문서 조회 연결은 확인됐으나, 저장된 정보묶음에서 입력 전달 결함을 발견했다. 두 새 실행 모두 db_snapshot.readable=false, 경기 식별 coverage=not_run(저장 경기 자료 읽기 연결이 설정되지 않았습니다), standings0행이다. 반면 별도 선수 통계는58/55행이며57/55행의 updated_at이 이번 수집 시작 이후다. 이전 관리자 첼시 실행32cc0aa9-905d-4d89-85cd-90deef1bba9f는 같은 경기의 readable=true·standings2행이었다.

조정용 코드 조사에서 공통 서비스의 경기 ID 해석은 임시 조회기를 열어 사용하지만 다음 생성 단계에는 원래 reader=None이 전달됨을 확인했다. 따라서 확보 가능한 순위 자료가 빠지는 현재 범위의 연결 결함으로 다룬다. [한정 보완 명세](preview-collection-reader-brief.md)에 따라 원 구현자에게 수정·대표 검사만 맡기며 첫 실행과 본문은 보존한다. 별도 한글 표기 진단·사진 구조화는 이 보완 범위가 아니다. 이 발견 이전의66 passed를 실제 자료 전달 완전성의 근거로 확대하지 않는다.

## 06:00 KST 조회기 수정 반영과 재시험 접수 거부

원 구현자 task_c47f539df3d3·ctx_6f297b2ecb73의 한파일 수정·직접49 passed를 별도 task_a376b22b29b4·ctx_575e39114dde가 코드와 검사로 한정 확인해 수용했다. 조정자는 인계 SHA256 두 개가 일치하고 서비스가 effective_reader를 전달하는 현재 코드를 확인했다. 구현자가 명세에서 금지한 변이/원복 실험을 수행한 것은 범위 초과로 기록하며 추가 근거로 삼지 않는다. 독립 검토는 검사를 반복 실행하지 않았다.

첫 실행이 finished_at과 home_preview 최종값을 남긴 뒤에만 PID9499를 TERM으로 정상 종료했다. 동일한 런처의PID15812/실행세션40430에서 startup complete를 확인했다. 설정·원본·승인행·기존 실행은 바꾸지 않았다.

06:00:07.947 KST 같은 기간·두 ID의 새POST를1회 보냈으나 HTTP409였다. 응답의 message/code를 반환 요약에서 빠뜨려 정확한 분기는 아직 보존하지 못했다. 코드상 활성 관리 실행 또는 분산 수집 잠금 때문에 생기는409이며, 새 수집ID는 받지 못했다. 따라서 전체 POST 시도는2회지만 **접수·실행은 첫1회뿐**이다. 실패 요청을 성공한 재시험으로 기록하지 않는다.

기존 관리 목록GET이7일 이전 실행행을 DELETE하므로 현재 작업 식별에 쓰지 않는다. `/admin/daily-sync/logs?limit=3`의 기존 조회는10월26일 옛 기록만 반환해 현재 수집 식별 근거가 아니었다. [읽기 전용 확인](preview-collection-active-read-brief.md)을 task_c571d57f62b8·ctx_ca50ada29e0d에 배정했다. 실제 동일 DB의 활성 실행과 잠금 메타데이터만 읽고 타 작업 취소·잠금 해제·새POST 반복은 하지 않는다.

## 06:06 KST 정기 수집 식별

DeepSeek의 SELECT 전용 확인에서 활성 실행 `1a80c517-31e0-40c2-95a8-61f230b5ae87`이 06:00:00 KST 시작·actor=정기 수집·test_scope 없음·대상4건·정상 heartbeat로 관측됐다. daily sync 잠금도 보유 중이었다. [읽기 근거](preview-collection-active-read-report.md). 조정자 06:05:58 개별GET은200·running·64%·finished_at=null, 대상14/15/17은succeeded이고13은running으로 반환됐다. 이는 시험 실행이 아니다. 해당 수집을 취소하거나 잠금을 해제하지 않고 정상 종료를 기다린다. 거부된 요청으로 새 프리뷰가 생성됐다고 세지 않는다.

## 06:09 KST 수정 후 재시험 접수

정기수집 개별GET에서 `finished_at=2026-11-12T21:08:26.210093Z`, status=succeeded를 확인한 뒤에만 같은 시험POST를1회 보냈다.

- HTTP200·새 수집ID **67adc7a9-8fc5-484b-ae53-d807930c256e**.
- 시작시각2026-11-12T21:08:53.938530Z(11월13일06:08:53 KST).
- 요청 기간/대상13/프리뷰 두ID는 첫시험과 동일하고 test_scope.run_id는 새 수집ID다.
- 접수 시queued·finished_at=null. 실제 완료는 이ID로 계속 확인한다.
- 전체 시험POST시도3회(첫접수·409거부·수정후접수), 실제 시험실행2회다. 별도 정기수집은 시험 실행 수에 포함하지 않는다.

## 06:15 KST 최종 수용 — 수정 후 실제 수집·두 생성·자료 입력·홈 조회

재시험 수집 `67adc7a9-8fc5-484b-ae53-d807930c256e`의 `finished_at=2026-11-12T21:14:43.242001Z`를 실제 개별GET으로 확인했다. 시작06:08:53→종료06:14:43 KST, 약5분49초다. status=succeeded·home_preview.state=finished·collection_status=succeeded·approval_gate.ready, candidates2·generated2·failed/skipped/deferred0이다. 누락/오래된 승인 목록도 비어 있다.

### 실제 수집 범위

요청과 최종 test_scope는 target13, 2026-11-21 21:30~22일00:00 KST 양 끝 포함, 생성 대상1557470/1557476으로 일치했다. 최종 로그의 fixtures=6과 details fixture=1557474/1557468/1557476/1557470/1557467/1557471을 확인했다. 기간 경기6개를 수집하고 두 경기만 자동 생성했다. 처리 단위55/55·실패0·pending0·저장 처리 합계1164다. 이 합계는 보조 수집/upsert를 포함하며 고유 신규 행 수가 아니다.

### 새 프리뷰와 저장 재조회

| 경기 | 이번 프리뷰 실행 | 모델·저장 | 공개 최신 조회 |
|---|---|---|---|
| 첼시–리즈1557470 | `248ccbc6-9337-4898-ab43-3b39ba45e4a7` | live·succeeded·ready·5섹션, 시작06:10:43/완료06:12:36, 전송장부6회·retry0·미확정전송0 | `/home/fixtures/1557470/document` 200·available·complete=true·이번run_id |
| 토트넘–입스위치1557476 | `eb2323c1-c02f-4569-9428-cb1b126634b2` | live·succeeded·ready·5섹션, 시작06:12:39/완료06:14:42, 전송장부6회·retry0·미확정전송0 | `/home/fixtures/1557476/document` 200·available·complete=true·이번run_id |

두 실행 label은 `preview-test:67adc7a9-8fc5-484b-ae53-d807930c256e`와 각 경기ID를 담는다. 관리자 수동 생성 POST로 보충하지 않았고, 같은 수집 종료 훅에서 생성된 결과다. 모든 공개 섹션이 ready·partial=false이고 주목 선수/부상 영향/외부 전망/배당/AI 전망 다섯 워크플로우가 존재한다. 첼시는 선수4·부상2·매체3·배당3, 토트넘은 선수4·부상4·매체2·배당3이며 둘 다 예상점수2-1이 구조화 값에 있다. 이는 생성·저장 계약 확인이며 새 본문 내용의 사용자 승인을 대신하지 않는다.

[첼시 새 문서 열기](http://127.0.0.1:5173/admin?tab=preview&previewRun=248ccbc6-9337-4898-ab43-3b39ba45e4a7) · [토트넘 새 문서 열기](http://127.0.0.1:5173/admin?tab=preview&previewRun=eb2323c1-c02f-4569-9428-cb1b126634b2)

### 조회기 누락의 실제 해소

두 새 실행의 정보묶음 저장 GET에서 `db_snapshot.readable=true`, 경기 식별 available, 리그 순위 available(저장 순위20행 읽기), 각 경기의 양 팀 standings2행을 확인했다. 첼시 선수 통계58행 중57행, 토트넘55행 전부가 재시험 수집 시작 이후의 updated_at을 가진다. db_snapshot.diagnostics는 둘 다 비었고 섹션에도 이전의 DB 읽기불가 진단이 없다. 첫 시험의 reader=None·not_run·standings0 관측과 구분되는 실제 저장 근거다.

저장된 DB 부상행은 양쪽 모두 없으며 coverage는unknown이다. 이를 부상자 없음으로 해석하지 않는다. 검색 근거로 생성된 부상 섹션은 별도로 존재한다. 한글 표기 등록 진단·사진/본문 스키마 개선과 공개 매체의 키 누락은 기존 후속 범위이며 이번에 수정했다고 하지 않는다.

### 종료와 범위

현재 승인된 기간 수집→실제 생성→preview_dev 저장→재조회→홈 최신 문서 선택을 두 경기에서 확인해 PC-LIVE를 수용한다. 일반 경로6시간 조건 보존은 기존 직접 합성 검사 근거를 사용하고, 현재 시각이6시간 밖인 두 경기의 실제 생성은 명시적 시험 범위로 확인했다. 두 시험은 현재11월13일 자료로 미래11월22일 경기를 생성한 것이며 경기 당일 자료를 재현한 시험이 아니다.

모델 재시도·수집 자동 재시도 정책은 추가하지 않았고 승인POST·마이그레이션·시즌정리·기존 실행 삭제·계정 변경·배포는 하지 않았다. 정기수집409 대기는 해당 작업을 그대로 두고 해결했다. API서버PID15812/세션40430은 로컬 확인용으로 유지한다. 이번 최종 단계는 API·저장 조회이며 브라우저 시각 검사를 새로 했다고 주장하지 않는다. 기존 홈 디자인 수용은 유지한다.

검사 근거는 endpoint 보완66 passed와 reader 보완49 passed라는 서로 다른 리비전/범위로 보존하고 합산하지 않는다. 별도 DeepSeek 확인이 각 범위를 수용했고 원 구현·검토·읽기 조사 워커는 모두 편집 종료/백그라운드0이다. 다음 후보는 사용자와 논의한 본문 구조화이며 현재 구현 단위를 임의로 확장하지 않는다.
