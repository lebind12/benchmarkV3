# 맨유–본머스 직접 JSON 저장 검증 — 2026-10-26

DB 입력값 검증 기준으로3회 연속 성공했다. 최종 버전은49·50·51이며 공개 조회는51을 반환한다. 최종 실행은 `out/home-preview/direct-schema-json-1557445-v10/`에 보존했다.

## 실제 결과

|항목|확인값|
|---|---|
|AI예측|맨체스터 유나이티드1–2본머스, medium|
|주요결장|마이누·쇼·스콧3명, 홈2/원정1|
|마이누|muscle / 토트넘전 근육 부상 /2026-10-10 / 원문1·4|
|쇼|code:null / 토트넘전 부상 /2026-10-10 / 원문1·5|
|스콧|thigh / 대표팀 경기 중 허벅지 부상 악화 /2026-10-03 / 원문6·7|
|눈여겨볼선수|음뵈모·태버니어. 시즌·완전한최근도움·연속골·팀흐름을 연결한 LLM선정이유와 DB상세기록|
|외부전망|SportsMole홈1-2, Goal홈2-2, Football365본머스무패/+0.5. 각 이유·실제URL 포함|
|기존기록|양팀5경기, 선수8명 원자료, 부상12명 원자료, 배당3개북메이커 값 보존|

LLM이 `facts.injuries.data[].cause.data`의 code/label/occurred_on/occurred_month를 직접 반환했다. 문장에서 날짜·원인을 추출하거나 반환값을 다른 필드로 옮기지 않았다. 전체 응답 객체를 JSONB에 그대로 저장했다. 원 응답의 UTF-8 문자열도 snapshot에 보존한다. 이전 고정 선정 문장과의 완전 일치 검사·GET 문장 덮어쓰기는 제거했다.

## 검증 근거

- `final-verification.json`: 요청스키마 오류0, raw JSON = JSONB 저장본 = snapshot 원응답, 원문문자열 일치, 세 독립 응답·최종HTTP응답 확인.
- `response-1/2/4.txt`: 수정하지 않은 세 LLM 응답. 같은 번호의 JSON/DB/GET/targets/review 파일과 연결한다.
- `execution.json`: 실제4API요청(완성후보3개, HTTP429전송재시도1개). 검사할 후보가 없는429는 DB스키마 검사 실패로 세지 않는다. 실패한 내용 후보가 사이에 없으며 세 DB검사 모두 성공했다.
- DB원본·기사·템플릿·request는 같은 실행 폴더에 보존한다. 이전 실패 실험은 각 별도 폴더에 남겼다. 총세션호출이3회였다는 뜻이 아니다.
- 세 후보의 DB입력/스키마/생성설정은 같다. 실행 도중 이전 harness가429로그를 시스템지시에 덧붙였기 때문에 전체 request바이트가 모두 같은 것은 아니다(`same_request_body_for_final_three=false`). 이 전송로그 주입은 현재 코드에서 제거했다. 이를 동일프롬프트의3회실험이라고 주장하지 않는다.
- 실제공개GET→화면 검증: 데스크톱1440/모바일390, AI예측·선수접기/이유·얼굴 실제로드·부상2×2·날짜·외부3곳·상세링크·overflow/pageerror0. `browser-verification.json`과 `main-*.png`, `mobile-*.png` 참조.

기존 수집 원문을 재사용한 승인된 과거 시점 로컬 재현이다. fixture1557445의 실제 킥오프는 그대로 두고 payload 기준 시각은2026-10-25T11:45:00Z, 실제 실행 시각은snapshot에 별도로 저장했다. 신규 검색 수집이나 다른 경기 일반화, 자동 worker전환/운영 배포 완료를 뜻하지 않는다. 일반GET DB전용/6시간 정책은 유지한다.

## 코드·화면

- 실행: `scripts/run_home_preview_direct_regression.py`
- 독립 재검증: `scripts/verify_home_preview_direct_regression.py --run-dir out/home-preview/direct-schema-json-1557445-v10`
- 화면: http://127.0.0.1:5193/?previewDate=2026-10-25&fixtureId=1557445
- API: http://127.0.0.1:8018/api/v1/home/fixtures/1557445/prematch

격리DB55441 및 메인 전용worktree/브랜치만 사용했다. 기존개발서버를 재시작하지 않고 검증용8018/5193을 별도로 실행했다.

## 테스트 결과

- BE 단위·Postgres통합104개 PASS(새 전송재시도/실패초기화3개 포함).
- FE 단위33개 PASS, Playwright E2E17개 PASS, production build PASS.
- 실제세후보의요청스키마오류0·JSONB/원문/API동등성 PASS.
- 실제화면의얼굴로드·접힌이유·부상날짜·3매체·상세링크·모바일overflow·pageerror 검사 PASS.
- Ruff와diff공백검사 PASS. 독립인수/운영전환은 이 로컬검증에 포함하지 않는다.
