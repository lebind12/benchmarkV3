> **기획 참고 원문 · 2026-11-09 정리**
> 출처: `news-context` 워크트리의 `docs/spec/endpoints/news-context.testplan.md`.
> 요구·설계·결정의 맥락을 보존한 자료입니다. 본문의 구현 완료, 검증 수치, 실행 명령, 작업 경로, 배포 승인은 당시 기록이며 현재 상태나 새 실행 승인이 아닙니다. 현재는 네 워크트리의 개발 코드가 삭제된 기획 보관 상태입니다. 상충하는 과거안은 상위 기획 요약과 최신 결정 기록을 따릅니다.

# 뉴스 문맥 검증 제출 상태

동결 계약의 R01–R14 / 58개 수용 시나리오가 기준이다. 이 문서는 기준을 축소하거나 새 승인·실행 증거를 만들지 않는다. 작업자는 호스트 테스트·네트워크·DB·서버 명령을 실행하지 않았다.

| 검증 경로 | 작성한 검사 | 상태 |
|---|---|---|
| `tests/unit/test_news_context.py` | 49,999/50,000/50,001 CP, URL·주입 필드, NFD/RTL/반복/교차 위치, 기준시각, 실제 HTTP 모양의 MAX_TOKENS/STOP 잘린 JSON, usage, NULL/0/missing, scope·지시어, 실제 finally 슬롯 barrier | 미실행 |
| `tests/integration/test_news_context.py` | in-process ASGI/SQLite, 전 API 권한·안전 ID, 입력 전 provider 거절, 반복 등장, 타인 ADMIN 작업/binding 404, 멱등 작업/판단, 취소 이력, 원천 순위 의미, 2026/2022 실제 두 시즌, 자동 재분할 성공/소진 | 미실행 |
| `frontend/tests/unit/news-context*.spec.ts` | 기존 목업 상호작용 보존, 실제 JWT fetch 호출/원문 payload, zod 실패, 권한 ID, commit 불명확, 스트림 오류 | 미실행 |
| `frontend/e2e/news-context-live.spec.ts` | 실제 로그인 두 context, 동결 matrix 순서의 새 분석/저장/취소/같은 문서 검사/별도 A 수정 페이지, 실제 카드 DOM, API 원문 digest, 실제 응답 기반 관찰 인계 | 미실행·완전성 미확보 |
| `tests/integration/test_news_context_live.py` | 실제 관찰 projection, 독립 DB source/actor/판단/감사/revision 조회, provider token/finish/config 확인, 고정 기대값 비교, 실패 관찰 우선 기록 | 미실행·완전성 미확보 |
| 두 control 모듈 | 동결 control binding/대상 등록 및 누락 실패 | **구체적 92개 제어 변형·하위 조작 구현 미완료** |

현재 control 디스패처는 구체적 조작이 없는 항목을 PASS/skip으로 바꾸지 않고 실패시킨다. 따라서 현 제출은 V06·R14 완료나 merge-ready가 아니다. 실제 PG 동시성·감사 실패 rollback·재시작·FK/index·읽기 전용 역할, 브라우저 fault controls 전체를 구현/실행해 이 차단을 해결해야 한다. 기존 V01–V06와 verification_files는 수정하지 않았다.

실제 평가 입력은 외부 expanded-oracle-v6(88/92/426)과 독립 동결 정답이다. 저장소의 과거 v3를 평가 입력으로 사용하지 않는다. browser가 먼저 실제 실행하고 API/DB suite가 같은 실행의 관찰을 독립 대조한다. 다른 실행에는 새 job이 필요하다. 관찰은 실제 API/DOM/DB 값만 사용하며 expected 값을 누락된 관찰에 채워 넣지 않는다.

과거 동일 커뮤니티 글의 전문이 없으므로 그 글의 503 재현을 주장하지 않는다. MAX_TOKENS·잘린 JSON 제어 회귀와 운영자가 확보한 pre-fix 50,000자 실패 로그는 별도의 근거다. 새 50,000자 provider 도달 검사와 실제 모델 3회는 외부 컨트롤러 실행 전까지 미확인이다.
