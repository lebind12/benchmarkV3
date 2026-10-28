# 기사 수동 분석 구현 보고서

- 모드: FULL / 담당: news-developer
- 서비스 계획: `docs/ax/news-context/service-plan-v1.md`
- 작업 브리프: `docs/ax/news-context/work-brief.json`
- 구현 커밋: `36ca08446cb82acd0637d6f22c5a8aa1c09b45a2`
- 작업 위치: `/Users/woolee/.codex/worktrees/news-context/benchmark`, `codex/news-context`
- 이 보고서는 개발자 자체 확인이며 독립 테스트/머지/배포 승인을 대신하지 않는다.

## 구현

| 기준 | 구현 위치와 동작 |
|---|---|
| AC-1 | `frontend/src/router/index.ts` verifySession + 활성 STREAMER/ADMIN guard, NewsAnalysisView 이중 화면 확인. `app/api/v1/news_analysis.py`는 기존 manager_user/JWT/DB 활성 확인 재사용. 미인증·비활성 401, USER 403. |
| AC-2 | `frontend/src/lib/api/news-analysis.ts`, AnalyzeInput. 빈 원문, 원문 20,000자, URL 2,048자, HTTP(S)·hostname·credentials·제어문자 확인. JS UTF-16 길이는 비 BMP 문자의 경우 서버보다 보수적이다. |
| AC-3 | `app/services/news_analysis.py` 원문 실제 위치의 인용 구절과 이름 경계를 확인하고 이름/번역명/firstname+lastname의 정확한 DB 후보 조회. LLM의 ID·URL·추가 키 거부. 2개 이상 후보는 ambiguous, 없음·성 단독·축약 선수명은 unresolved. unsafe 후보도 개수에 유지해 동명이인을 숨기지 않는다. |
| AC-4 | 서버 DB slug만 URL 인코딩해 기존 팀/선수 상세 경로 생성. 화면은 escaped text로 원문 근거·보류 사유·출처 표시. URL 내용을 검증했다는 주장 없음. |
| AC-5 | NewsAnalysisView 초기·분석중·완료·대상 확인 못함·보류·오류/재시도 구분. 오류 시 입력 유지. |
| AC-6 | pending 중 중복 submit 차단. 입력 변경 시 controller abort + 세대값 갱신으로 이전 응답 무시. unmount 시 중단. |
| AC-7 | `news_analysis_vertex.py` 뉴스 전용 모델/위치 설정, URL 인자/웹 도구 없음. 사용자 지시는 데이터로 취급. 원문/모델 본문 logging 없음. 추출 최대30, 근거600자, 후보조회6, 출력4096토큰. 분당 사용자3회·동시2, 인증 refresh HTTP10초·provider read45/connect10초, endpoint 대기60초. timeout 이후 실행 중 worker는 슬롯 유지, 종료 후 반환. |
| AC-8 | DB select만 사용, 새 테이블/마이그레이션/저장/공개 발행/워커 없음. 기존 뉴스·상세 코드는 변경하지 않음. |

프론트 목업과 endpoint 계약을 먼저 제출했고 운영자의 계약 검토·후속 구현 지시 후 서버 구현과 실 API 연결을 진행했다. 최종 화면 기본은 authenticated POST이며 가상 selector/결과를 제거했다. `/admin/news-analysis`, 서비스 관리의 진입 링크를 제공한다. 디자인은 기존 Pretendard와 관리 화면 색·border 토큰을 재사용하고 760px 이하에서 세로 배치한다.

## 실행 근거

- `/Users/woolee/benchmark/.venv/bin/python -m pytest tests/unit/test_news_analysis.py tests/integration/test_news_analysis.py -q`: **24 passed**. SQLite memory DB와 실제 JWT/manager dependency 사용. 운영 DB·Supabase·Upstash 접근 없음. 모델은 stub/MockTransport이며 유료 호출 없음.
- `frontend`에서 `./node_modules/.bin/vitest run --config /tmp/news-context-vitest.config.mjs`: **4 passed**. 입력·권한 UI·중복·stale 응답·오류 입력 보존·retry·empty·linked/held·HTML escaping.
- `frontend`에서 `npm run build`: **PASS**, vue-tsc + Vite 완료.
- 추가한 Python 5개 파일 `ruff check`: **All checks passed**.
- `git diff --check`: **PASS**.
- 기존 vitest include를 바꾸지 않고 /tmp config가 `src/**/news-analysis*.test.ts`를 선택하도록 했다. 공유 node_modules를 symlink로 읽기 전용 재사용했으며 의존성 파일을 수정하지 않았다.
- 자체 브라우저 screenshot 시도는 이전 목업 버튼 대기 timeout으로 완료하지 못했다. 이를 UI 성공 근거로 사용하지 않는다. 별도 tester의 독립 브라우저/API 검증이 필요하다.

## 제약과 남은 위험

- 실제 Vertex 분석 품질과 비용은 위 stub 테스트로 검증한 것이 아니다. 운영자가 별도 실호출 smoke를 진행했으며 해당 근거는 `verification/live-vertex-smoke.json` 관리 대상이다.
- 보수적인 정확 이름 연결이므로 영문 기사와 한글 이름만 있는 DB, 별칭, 철자 차이, 성만 언급된 경우는 연결되지 않을 수 있다. 보류 상태로 남긴다.
- rate budget은 프로젝트의 단일 인스턴스 전제에 맞춘 메모리 상태다. 재시작 시 초기화되며 다중 인스턴스 전역 제한은 제공하지 않는다.
- endpoint timeout은 응답 대기를 중단하지만 Python thread의 진행 중 HTTP를 강제 종료하지 않는다. provider 개별 timeout과 슬롯 유지로 무제한 추가 동시 호출을 막는다.
- 실제 전체 DB에서의 조회 성능 및 팀/선수 상세 브라우저 이동은 독립 테스트에서 추가 확인한다.
- 부모/테스터의 progress·verification 파일은 커밋하지 않았다. push·merge·배포·운영 DB 변경 없음.
