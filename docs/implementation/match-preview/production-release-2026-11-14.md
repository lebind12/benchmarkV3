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

기능 커밋 **b2ac969ac3c9310c0544dd6b898e63c0209a39f3**을 생성했다(284파일, 과거 삭제0). origin/main push 성공(`5f354e3..b2ac969`)과 git ls-remote의 같은 SHA를 확인했다. 직접 검사26/26·로컬 build exit0은 구현자의 같은 파일 리비전 근거다. 별도 DeepSeek `task_6e9ef6efe50a / ctx_c4bbae665bf9`가 네 파일의 SHA·행 계약·matcher와 RouterLink 대역·API 호출7경로·Vercel 설정을 읽기 전용으로 확인해 차단0/수용을 보고했고 root가 수용했다. 검사 재실행0이며 잉여 캐스트·fixture available 미단언은 참고로만 남겼다.

해당 commit tree에서 backend35MB·frontend40MB를 따로 추출했다(임시 `/tmp/benchmark-release.Xs7Vdf`, 인계 기준은 임시 파일이 아니라 commit SHA다). Vercel `dpl_4vcuPMirkBvJ4g6jk5EyqcxFUrUn` (`https://benchmark-v3-7ca5yqe95-woolees-projects.vercel.app`)는 production 환경/skip-domain으로 먼저 배포해 원격 build가 통과하고 READY가 됐다. VITE_BACKEND_URL=/을 해당 빌드 입력에 명시했다. 이후 backend 확인을 마치고 `vercel promote`로 운영 주소에 승격했으며 운영 alias inspect가 정확한 deployment ID/READY를 반환했다.

Koyeb 신규 deployment **13237d92-1e6f-453f-b4a8-841a2d413255** / archive **5b0e4503-48b9-4347-95e2-93679dae8564**는 build와 시작을 마치고 service의 active/latest가 동일한 HEALTHY 상태가 됐다. APP_REVISION은 b2ac969 전체 SHA다. 기존 DATABASE_URL·모델 자격 secret 참조를 보존했고, 기존 tyo/small/1인스턴스·8000/http·/health·uvicorn 명령을 유지했다. PREVIEW_ENV=prod·COOKIE_SECURE=true·ALLOW_NONLOCAL_DB=true, 기존 프로젝트/global/gemini-3.5-flash 모델 연결과 LIVE_ENABLED=true·HOME_PREVIEW_ENABLED=true를 설정했다. 로컬 인증 플래그는 켜지 않았다. 배포 확인을 위해 수집·생성·승인 POST나 migration을 실행하지 않았다.

## 운영 확인 (2026-11-14 04:05~07 KST)

- Koyeb 공개 추천 GET: items의 fixture_id=1557474.
- Koyeb 공개 문서 GET와 Vercel 운영 도메인 경유 같은 GET: status=available, complete=true, 5섹션(players/availability/outlook/odds/ai_forecast), fixture1557474, run_id=`493ef4a9-0e14-4436-8a97-d6de7ce034a7`. 새 생성 없이 기존 승인 저장본이 연결됐다.
- 운영 홈 실제 브라우저 DOM: 오늘 추천 없음을 설명한 뒤 11월21일 맨시티–풀럼 추천·21:30 KST, “경기 시작 전 6시간 이내의 마지막 정기 수집에서 한 번 생성됩니다.”, 저장시각11월12일21:40 KST, AI 전망/예상점수2:1·주목 선수4·부상2·외부 매체·배당을 확인했다.
- 같은 페이지의 이미지 loaded 판정: main img12개 모두 complete 및 naturalWidth>0. 선수/부상 사진6개와 엠블럼이 정상 로드됐다.
- 스크린샷 캡처는 브라우저가 frame을 그리지 않는다는 도구 timeout으로2회 실패해 PNG를 확보하지 못했다. 새 배포의 픽셀/모션 재수용으로 인용하지 않는다. 위 DOM·API·이미지로드 확인과 기존 사용자의 디자인/스크롤 효과 수용은 별개 근거다. 같은 렌더/CSS 소스를 배포했고 수정하지 않았다.
- 보완 구현·검토 워커는 모두 편집종료/빈 입력창 확인 후 닫았고 ptyKilled=true를 확인했다. benchmark 터미널 목록에는 기존 backend와 frontend 서버 두 개만 남았다.

배포 요청의 필수 작업은 완료했다. 후속 본문 구조화는 아직 시작하지 않았다.
