> **기획 참고 원문 · 2026-11-09 정리**
> 출처: `ax` 워크트리의 `docs/ax/natural-language-search/release-contract-20261029.md`.
> 요구·설계·결정의 맥락을 보존한 자료입니다. 본문의 구현 완료, 검증 수치, 실행 명령, 작업 경로, 배포 승인은 당시 기록이며 현재 상태나 새 실행 승인이 아닙니다. 현재는 네 워크트리의 개발 코드가 삭제된 기획 보관 상태입니다. 상충하는 과거안은 상위 기획 요약과 최신 결정 기록을 따릅니다.

# 2026-10-29 release 계약 선행 수정 제출

이 문서는 C1~C4 구현 제출 기록이다. 승인 기록이나 부모 출시 판정을 변경하지 않는다. 호스트 테스트, 빌드, 브라우저, 네트워크, 실제 provider/DB 호출 및 private 설정 조회는 실행하지 않았다. 아래 검증 상태는 모두 **미실행**이다.

| 요구 / 시나리오 | 변경 위치 | 변경 이유와 동작 | 검증 연결 |
| --- | --- | --- | --- |
| C1 / C1-S1 | `frontend/src/lib/api/axSearch.ts`, `frontend/tests/unit/lib/axSearch.spec.ts`, `frontend/tests/unit/lib/axReleaseContract.spec.ts` | results/partial/no_matches의 table+source 참조 집합과 applied/coverage의 완전한 일치를 요구한다. 중복·미발급 참조, 누락/여분 row key를 거절한다. 숨긴 player_id/league_id/source_rows 예외를 제거하며 season_year도 선언 없이는 거절한다. 직접 지표의 표시 단위, 파생 단위·lineage 검사를 유지/보강한다. 표가 없는 정상 no_matches는 source metadata와 lineage로 검증한다. | V-RELEASE-FE, V-RELEASE-BE |
| C2 / C2-S1 | `frontend/src/lib/api/axSearch.ts`, `frontend/src/views/AgenticSearchView.vue`, `frontend/tests/unit/lib/axReleaseContract.spec.ts` | agentic 전용 요청 타입/strict 스키마로 message 필수·choice_ref 금지·부모/대화 참조 쌍을 검사하고 POST/SSE 전송 전에 적용한다. clarification 버튼은 현재 대화의 마지막 응답에 발급된 option의 ref와 label이 모두 일치해야 하며 label을 message로 보낸다. | V-RELEASE-FE, V-RELEASE-BE |
| C3 / C3-S1 | `frontend/e2e/ax-acceptance.spec.ts`, `frontend/vite.config.ts`, `scripts/run_ax_acceptance.py`, `scripts/verify_ax_frontend.py` | 공개 표는 name/current/previous/change 또는 name/player_assists만 oracle에서 투영하여 값·NULL·순서를 비교하고 실제 row key 집합을 엄격히 검사한다. 메타데이터 참조 집합/중복·version·시각과 단위도 검사한다. 검색·복구용 최초 질문·NULL·취소는 fill 후 검색하기 버튼 enabled/click을 사용한다. production build에서 고정 MSW 출력 파일만 제거하고 두 실행 경로에서 실제 dist를 검사한다. 서버의 MSW 전용 404 가림을 제거했다. | V-RELEASE-FE, V-RELEASE-BE; actual E2E 별도 필수 |
| C4 / C4-S1 | `frontend/e2e/ax-acceptance.spec.ts` | 신규 private 결과 파일에 고정 stage/status/code, 각 stage의 전후 실측 counter 및 elapsed/model_calls/db_queries/total_tokens 차이를 기록한다. 관측 실패·provider 오류·예산 위반은 실패이며 남은 stage는 NOT_RUN이다. oracle 경로를 환경변수로 지정할 수 있다. | V-RELEASE-FE, V-RELEASE-BE; actual E2E 별도 필수 |

독립 spec/impl 검토의 실제 V-RELEASE-FE / V-RELEASE-BE 결과는 외부 컨트롤러가 생성해야 한다. 이 제출은 해당 결과를 인용한 독립 finding이나 통과 증거를 만들지 않는다. 기존 V-AUTH/V-SEARCH/V-FRONTEND 및 공통 auth 결과는 역사적 근거이며 이번 실행 결과 또는 승인으로 사용하지 않는다.

검증 대상은 동결 명령의 `scripts/verify_ax_frontend.py --scratch "$TMPDIR"` 경로(V-RELEASE-FE: 전체 Vitest/type-check/실제 Vite build/dist 검사)와 `tests/unit/test_ax_security_contract.py`, `tests/unit/test_ax_shared_auth.py`(V-RELEASE-BE)다. 신규 회귀 사례는 `frontend/tests/unit/lib/axReleaseContract.spec.ts`의 `C1 release public evidence boundary`, `C2 agentic request boundary`에 있다. 기존 SearchEvidence의 invalid cached 자료 안내 테스트는 수정하지 않았다.

전용 agentic 요청 타입은 기존 `search/conversation`의 legacy 타입을 사용하는 다른 화면을 변경하지 않기 위한 필요한 분리다. production asset 검사 함수는 검증 스크립트와 actual acceptance launcher가 동일한 dist 조건을 적용하기 위한 공유다. public/source MSW 파일과 DEV 동작, scratch copy/원본 read-only 원칙은 유지한다. backend/API 계약, SQL·모델·권한·JWT·DB·scope·신선도·원본 oracle/component grader는 수정하지 않았다.

`AX_ACCEPTANCE_RESULT_FILE`은 workspace 밖 절대 경로여야 하며 실제 부모 디렉터리 권한은 0700이어야 한다. O_EXCL/O_NOFOLLOW로 새 0600 파일을 생성하고 기존 파일은 덮어쓰지 않는다. 이후 해당 신규 파일에 stage별로 갱신하고 fsync한다. 파일에는 질문·SQL·응답 원문·계정·credential·token·예외 원문을 넣지 않는다. counter도 허용된 숫자 필드만 복사한다. 오류 출력은 고정 stage ID의 `_FAILED`이며 route callback의 원문 오류도 외부로 보내지 않는다. 결과 파일 설정/생성 자체가 실패하면 파일은 없을 수 있으며 실패를 성공으로 처리하지 않는다. 기존 private Playwright 설정의 trace/video/screenshot 비활성화와 원문 오류 문맥 복사 금지를 유지한다.

`AX_ACCEPTANCE_ORACLE_PATH`를 지정하면 원천 version에 맞는 새 oracle 절대 경로를 읽는다. 미지정 시 기존 oracle 경로를 사용하며 version과 추출 시각의 신선도 검사를 완화하지 않는다. 공개 E2E projection은 내부 ID를 API에 추가하지 않는다. full ID 정확성은 기존 private component grader의 책임으로 남는다.

turn을 수행하는 E-REAL-3P/E-FOLLOW/E-RECOVER/E-NULL/E-CANCEL stage의 관측 차이는 모델 12회/180초/120000 tokens를 넘으면 실패한다. 그 외 stage는 모델/reader 추가 호출과 token 소비 0을 요구한다. suite는 기존 launcher counter 기준 모델 32회/600초/500000 tokens 및 기존 DB 24회 상한을 별도로 검사한다. provider 실패나 누락된 관측을 0으로 대체하지 않는다. 모델 대체와 자동 retry를 추가하지 않았다. USD 가격은 미확인이며 결과에 `usd_price_verified=false`를 기록한다. 현재 실측 시간·표본 p95·오류율·토큰 사용량은 실행 전이라 없다. 후속 root 보고에서 실측하고 표본 p95를 모집단 SLA로 주장하지 않아야 한다.

부모 Q/E/R 전체, PI-01~PI-12/SEC-01~SEC-02 및 정상 대조군, 독립 holdout/SQL oracle, actual Vertex→DB→브라우저, runtime §2~7 격리 인수, coverage≥80%와 최종 독립 검토는 여전히 필수 머지 차단 게이트다. 이번 E2E의 취소 ack/취소 nonce 거절, 실제 완료 응답의 전송 차단 뒤 동일 nonce 복구와 중복 호출 0, 서로 다른 USER 격리 검사도 실제 실행 전이다. 이 선행 수정의 단위/빌드 통과가 추후 확인되더라도 부모 게이트 PASS를 의미하지 않는다. 실제 운영 DDL·배포는 실행하지 않는다.

수정 전 동작의 근거는 동결 baseline 및 공개 표 contract proof와 현재 source의 정적 확인이다. 수정 전 실패 테스트나 actual E2E를 재현 실행한 증거는 없다. 소유 경로 밖의 기존 편집과 발견되는 기존 미사용 코드는 제거하지 않았다.
