# 2026-11-14 프리뷰 기능 배포 기록

## 사용자 요청과 범위

사용자가 완료 기능의 커밋·push·배포를 요청했다. 운영 프론트에서도 추천 경기와 기존 프리뷰 안내 문구를 유지하며, 승인된 저장 자료가 있는 맨체스터 시티–풀럼은 본문을 자동 표시한다. 새 본문 생성·DB 초기화·다음 단계 구조화는 이 배포의 범위가 아니다.

## 배포 전 확인

- main의 원격 대비 56개 커밋은 기존 프리뷰 개발 이력이다. 원격 fetch 완료. 새 커밋은 프리뷰·관리자 통합·수집 연결·관련 검사/문서를 선별한다. 이전 기획 정리의 421개 삭제와 로컬 생성물을 일괄 포함하지 않는다.
- 로컬 127.0.0.1:5173 실제 홈에서 맨시티–풀럼 추천 경기, “경기 시작 전 6시간 이내의 마지막 정기 수집에서 한 번 생성됩니다.”, 저장 프리뷰 5섹션·예상점수2:1·사진/배당을 확인했다.
- 실제 수집→두 경기 생성→저장→홈 최신 조회의 완료 근거는 [실수집 기록](preview-collection-live-evidence.md)을 재사용한다. 이번 배포에서 수집·모델 생성·승인 POST를 다시 실행하지 않는다.
- 최초 프론트 build는 타입 오류8개로 exit2였다. [REL-BUILD](release-build-brief.md)가 해당 오류와 기존 Vercel API proxy/build 설정 복구만 맡는다. 완료 수치는 구현·한정 확인 후 기록한다.

## 기존 배포 대상과 운영 조건

- Vercel: `woolees-projects/benchmark-v3`, project `prj_gBIpdmsxqiWXHgGk4vRZFTVwhQGk`, 운영 URL `https://benchmark-v3-steel.vercel.app`. CLI inspect와 기존 프로젝트 link 성공. 앱 connector는 재인증 요구라 기존 CLI 인증을 사용한다.
- Koyeb: `benchmark-v3/api`, service `5178062c-1ff2-49a3-a683-e96df3d672cb`, 운영 URL `https://benchmark-v3-lebind12-19f488ae.koyeb.app`. 배포 전 활성 deployment `6b6fbe4f-92eb-4cbe-9a09-68e1e9082287`는 HEALTHY이며 archive/buildpack·tyo/small·단일 인스턴스·8000 포트·기존 uvicorn 명령을 사용한다.
- 배포 전 원격 health200·프론트200, 신규 `/api/v1/home/fixtures/1557474/document`는404다. 새 코드가 아직 운영에 없는 상태다.
- 운영과 승인된 로컬 프리뷰 모델은 모두 Vertex `gemini-3.5-flash`/global이며 프로젝트도 일치한다. 기존 모델·DB secret을 재사용하고 값은 문서나 소스에 복사하지 않는다.
- 신규 PREVIEW 설정은 기존 단일 DATABASE_URL의 저장 조회와 승인된 자동 생성 경로를 연결하기 위한 것이다. 로컬 인증 플래그는 운영에서 켜지 않는다. 기존 세션·수집 scheduler 설정은 유지한다.
- backend archive는 커밋 tree에서 app 전체·requirements·pyproject/README·런타임 schema/prompt 문서 및 기존 번역 CSV를 포함한다. 로컬 자격 파일·node_modules·캐시·개발 산출물은 포함하지 않는다. 프론트도 같은 커밋의 frontend tree를 배포한다.

## 실행 결과

커밋·push·실배포는 REL-BUILD 완료 후 진행한다. 최종 코드 SHA, 배포 ID, 운영 API/홈 확인 결과는 실행 후 이 절에 기록한다. 이 문서는 배포 성공 증거가 아니다.
