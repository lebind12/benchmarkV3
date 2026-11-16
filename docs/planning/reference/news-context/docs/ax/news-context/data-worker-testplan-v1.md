> **기획 참고 원문 · 2026-11-09 정리**
> 출처: `news-context` 워크트리의 `docs/ax/news-context/data-worker-testplan-v1.md`.
> 요구·설계·결정의 맥락을 보존한 자료입니다. 본문의 구현 완료, 검증 수치, 실행 명령, 작업 경로, 배포 승인은 당시 기록이며 현재 상태나 새 실행 승인이 아닙니다. 현재는 네 워크트리의 개발 코드가 삭제된 기획 보관 상태입니다. 상충하는 과거안은 상위 기획 요약과 최신 결정 기록을 따릅니다.

# 이적·부상 적재 선행 작업 — 실행 가능한 수용 기준

부모14/58 요구는 유지한다. 이 문서는 제품 완료가 아닌 worker 선행 의존성의 동결 기준이다.

## 이적의 기술적 보관 창

API의 공식 season.start/end는 원본 그대로 보존하고 경기 범위에 사용한다. 이적 관찰용 창을 별도로 계산한다. 축구 이적 기간을 공식 시즌 날짜로 가장하지 않는다. 시즌의 start와 end가 서로 다른 연도이면 해당 season.year의 6월 1일~다음 해 5월 31일(양끝 포함)을 이적 관찰 창으로 사용한다. 같은 연도에 시작·종료하는 calendar season은 그 season.year의 1월 1일~12월 31일을 사용한다. current와 직전 실제 시즌만 선택하며 WorldCup2026/2022의 달력 창도 각각 보존한다. 제공 날짜가 없거나 역전되거나 두 연도 방식으로 해석할 수 없으면 해당 이적 범위를 미확인 오류로 기록하고 추정하지 않는다. 다른 자료는 기존 정책대로 진행한다. 이는 여름 이동을 누락하지 않기 위한 명시적 기술 범위이며 새로운 경기 시즌이나 공식 이적시장 날짜를 창작하는 정책이 아니다.

EPL 실제 관측: season2025 공식2025-08-15~2026-05-24, season2026 공식2026-08-21~2027-05-30. 이적 창은2025-06-01~2026-05-31 및2026-06-01~2027-05-31이다. 2025-06-05 실데이터 포함을 검증한다. 경계 전날·당일·끝날·다음날 및 달력 시즌·희소2022/2026을 새 runner 테스트에서 독립 검사한다.

## NULL 자연키의 실제 DB 검증

알려진 선수·팀·리그에 대해 fixture=NULL인 injury 1종, from=NULL/to=known, from=known/to=NULL, 양쪽=NULL인 transfer3종을 명시적 합성 fault로 삽입한다. 각 1회 commit 후 engine.dispose와 새 Session/연결로 동일 요청을 반복한다. 각 자연키가 반드시 정확히1행이어야 하며 0행 성공은 금지한다. 실제 source 양성 행과 합성 fault를 구분하고 검증 후 합성의 정확한 row ID만 삭제해 최종 실제 원천 snapshot에 포함하지 않는다. 정상 real source 응답은 별도로 실제 partial commit→재시작→전체2회 적재를 검사한다.

## 실패/복구와 관측 (DW03-S1·S2)

- transfers의 한 팀 HTTP 실패·재시도3회 소진: safe endpoint/error를 season.errors에 기록, 그 팀을 빈 성공으로 세지 않는다. 다른 팀·injuries·다른 시즌은 기존 endpoint 오류 정책대로 계속한다. 성공한 적재/commit만 progress.stored와 결과 집계에 반영한다.
- injuries 한 시즌의 같은 실패: 오류 상태를 남기고 transfers/다른 시즌을 계속한다. 정상 오류 없는 빈 응답과 미수집 실패를 구분한다.
- 응답 중 잘못된 레코드 하나: mapper가 안전하게 skip하고 invalid/skipped 집계를 구분하며 뒤의 정상 레코드는 처리한다. 필수 참조 누락과 API source의 명시적 NULL은 다르다.
- DB 쓰기/commit 실패: 현재 미commit batch를 rollback하고 실제 오류를 기존 league/batch 실패 처리로 전파한다. 이미 commit한 자료는 유지한다. 거짓 성공 집계·진행 완료·추가 정상화 저장을 하지 않는다. 기존 바깥 batch 정책대로 다음 league/다음주기에서 재개한다. 재개 시 중복 없음과 profile/번역 불변을 검증한다. 정상 API 오류에 대한 한 endpoint 계속 처리를 DB transaction 실패와 혼동하지 않는다.
- client max3retry/≤6 동시성/≤450RPM을 유지하며 추가 무한 retry를 만들지 않는다. progress/counts는 시도/성공commit/invalid/누락/endpoint오류를 혼동하지 않는다. 정해진 endpoint 단위 기존 progress 보고를 재사용하며 새 수동 API나 서비스를 추가하지 않는다.

새 `tests/unit/test_daily_sync_history_runner.py`는 위 정상호출·중복팀·범위경계·HTTP단일실패·레코드부분실패·DB실패·commit관측을 반드시 의미 있게 검증한다. root host는 실제 Postgres와 raw HTTP 관측으로 양성·FK·NULL·멱등성·재시작·보호를 실행한다. worker가 단위/host 테스트를 직접 실행하지 않는다. 최종 독립 검토는 정확히6개DW 시나리오를 각각1회 판정하며 중복 finding으로 형식 검사를 우회하지 않는다.
