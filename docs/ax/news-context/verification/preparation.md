# 독립 검증 준비

2026-10-28. 테스트 담당 news-tester. 이 문서는 실행 결과나 PASS 보고서가 아니다. 운영자가 최종 commit/revision을 전달하면 해당 변경본을 대조하고 실행한다.

소유 범위는 이 verification 디렉터리의 테스트 코드·fixture·실행 로그·캡처·보고서뿐이다. 제품 파일, 다른 세션, 운영 DB, 외부 배포를 변경하지 않는다.

## 검증 기준

| 기준 | 독립 실행 시나리오 |
|---|---|
| AC-1 | 서명된 access JWT + 격리 사용자 DB/fake session으로 기존 current_user/manager_user 실행. 비로그인·오서명·만료·USER·비활성·삭제 계정 거부, 활성 STREAMER/ADMIN 허용. 브라우저의 직접 주소 진입도 역할별 확인. |
| AC-2 | 빈칸/공백 기사, 빈 URL, javascript/file/credentials URL, 길이 상한 초과 거부. 정상 HTTP(S) 및 경계값 허용. |
| AC-3 | 실제 DB 이름/번역명 연결, 동명이인·단독 성·없는 대상 보류. 조작 evidence, 원문에 없는 mention, 모델 제공 임의 ID/path를 확정 연결에 사용하지 않는지 확인. |
| AC-4 | 연결 카드에 원문 substring, 서버 생성 DB 상세 경로, 입력 출처 URL과 내용 미검증 안내 표시. 보류 대상에는 상세 링크 없음. |
| AC-5 | 분석 중/완료/없음/보류/실패 화면. 서버 오류 후 텍스트·URL 유지 및 재시도. |
| AC-6 | 지연 응답 중 중복 클릭은 한 요청. 기사/URL 변경 후 이전 요청 결과 무시. 새 요청 결과와 과거 결과 분리. |
| AC-7 | 출처 호스트로 network 호출 없음. 입력 HTML/명령문은 데이터, DOM HTML 실행 없음. timeout·동시/사용자 제한과 안전한 오류. 로그에 기사 전문 미포함. |
| AC-8 | fake/격리 DB에서 쓰기 호출을 실패시키고도 분석 성공. 공개 뉴스 미등록. 기존 뉴스·팀/선수 상세 기본 진입 및 링크 회귀 확인. |

## 실행 환경 계획

- API 8027 / 프론트 5197. 사용 전 LISTEN 확인하고 이미 점유되면 다른 세션 프로세스에 접근하거나 종료하지 않는다.
- Python은 /Users/woolee/benchmark/.venv/bin/python, node 패키지는 기존 frontend/node_modules를 재사용한다. 현재 전용 worktree에 .venv는 없다.
- 서버 권한 검사에서 current_user를 unconditional override하지 않는다. DB dependency와 모델 외부 호출만 격리하고 JWT 서명·검증·활성 검사·역할 검사 제품 코드를 실행한다.
- 브라우저 UI 목업을 위한 auth HTTP stub은 서버 권한 검증과 명시적으로 분리한다.
- 실제 Vertex 유료 호출 없이 모델 stub을 사용하면 실제 모델 품질은 미검증으로 남긴다. 운영 DB나 Upstash에 쓰지 않는다.
- 실행 시 UTC 시각, 명령, 종료 코드, 기대/실제 결과, 전체 HEAD와 미커밋 경로를 함께 남긴다. 최종 정형 보고서는 기준별 근거 파일과 운영자 전달 revision을 포함한다.

## 준비 중 관찰

- 준비 시 HEAD: e677a7924f60c12850fc3788dba829cbf068e049. 프론트 구현 미커밋 변경이 존재하며 최종 제출 SHA가 아니다.
- 관리 checkout의 최신 AGENTS.md와 전용 worktree의 service-plan-v1.md/work-brief.json/test-brief.json 및 endpoint 계약을 읽었다.
- 준비 시 5197/8027 LISTEN 없음. 최종 실행 때 다시 확인한다.
