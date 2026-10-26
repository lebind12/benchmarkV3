# 관리·홈 운영 배포 검증 — 2026-10-26

사용자 승인: 관리와 메인 업데이트를 함께 push하고 배포한 뒤 운영 페이지까지 테스트한다. 기존 배포 금지 지시는 이번 범위의 명시적 승인으로 해제되었으며 AX 개발 브랜치는 포함하지 않는다.

## 배포 결과

- 배포 소스: `74f3370b4a5b158087d3c529eacaa193396e4031`. 관리278d152, 홈JSON/스크롤/중계버튼 및 카라바오·FA컵 준결승 이상 제한961daa3을 포함한다. GitHub origin/main push를 확인했다.
- Vercel `woolees-projects/benchmark-v3`: production READY, deployment `dpl_4QcuH8M9dxg99dBsRnAG6VBQmTff`. production 빌드를 skip-domain으로 만들고 API 프록시200을 확인한 뒤 promote했다. 운영 주소는 https://benchmark-v3-steel.vercel.app 이다.
- Koyeb `benchmark-v3/api`: HEALTHY, active deployment `86bb5a96-429c-442f-987e-e877bd8050b8`. source revision74f3370, 기존 tyo/small/단일인스턴스/health검사를 유지했다. 백엔드 주소는 https://benchmark-v3-lebind12-19f488ae.koyeb.app 이다.
- Git archive의 백엔드 실행 소스·프롬프트/스키마·migration·seed만 따로 묶어 배포했다. frontend/assets를 포함한 전체 묶음은 Koyeb50MB 한도를 넘어 실행 전 거부되었으며, 런타임 파일만 포함한 묶음으로 배포했다. 로컬.env·ignored out·인증파일은 업로드하지 않았다.

## 배포 설정 보완

- Vercel의 명시적 Vite build/output 설정과 `/api/:path*` → Koyeb 프록시를 추가했다. 운영 VITE_BACKEND_URL을 `/`로 설정해 브라우저 API가 same-origin으로 동작하고 refresh cookie를 유지한다.
- Koyeb에 새 JWT 서명 secret을 stdin으로 생성하고 `JWT_SECRET_KEY`에 secret 참조로 연결했다. 값은 문서·로그·프로세스 인자로 기록하지 않았다. CORS/CSRF 허용 Origin은 운영 Vercel 주소로 지정했다. Secure/SameSite 기본 보호는 유지한다.
- `HOME_PREVIEW_ENABLED=true`, 기존 `WORKER_SCHEDULER_ENABLED=true`, Redis prefix `prod:`를 확인했다. 추천 경기의 마지막6시간 수집1회 정책이 적용되며 일반 GET은 생성을 실행하지 않는다.
- 운영 DB는 사전 적용·검증한0017/0018을 사용한다. 이번 배포에서 schema를 재적용하거나 사용자/권한/축구 데이터를 테스트 목적으로 수정하지 않았다.

## 실제 운영 검증

API 응답을 mock하지 않은 운영 주소에서 확인했다. 상세 증거는 `production-release-2026-10-26.verification.json`이다.

- Koyeb health, 추천, 저장프리뷰 조회200 및 JSON schema 대조. 추천에 컵8강이하가 없음을 확인했다. 현재 추천 fixture1557450의 생성 예정시각은10/31 18:00 KST로 표시된다. 현재 미래 경기라 새 LLM생성을 수동으로 실행하지 않았다.
- 실제 운영 home·match detail을1440/390 viewport에서 확인했다. 단일 main/스크롤 소유자, 숨긴스크롤바, 가로초과0px, 개발도구 미노출, 상세이동과 조회응답200을 확인했다. 페이지 JavaScript 오류0.
- 비로그인 및 위조 X-Mock-Role의 관리 API 접근401 확인. 이는 관리 API 검증이며 기존 방송 endpoint 권한 구현 전체의 독립 감사는 아니다.
- 사용자가 운영 서비스에 로그인한 기존 Chrome 세션으로 관리4탭(수집대상·실행·이력·번역)을 조회했다. 저장된 실제 대상/이력/번역이 표시되고 선수 ‘브루노’ 검색19건(선수1485 포함)을 확인했다. 편집 저장·새 수집 시작은 하지 않았다.
- 관리 화면을 실제 새로고침한 뒤 인증·관리 접근을 유지했다. 백엔드 로그의 refresh200/me200/관리GET200으로 UI→same-origin proxy→API→DB 흐름을 대조했다.
- 로그인한 ADMIN의 홈 스트리밍 버튼과 선택창을 확인했다. 두 링크에 현재 fixture1557450/league가 연결되며 기존 권한과 일치한다. 반복 라이브 polling을 시작하는 방송 창은 테스트 중 열지 않았다.
- 확인 구간 Koyeb runtime ERROR/Traceback0, Vercel deployment error log0, 인증된 Chrome console error0.

이 검증은 운영의 조회·권한·로그인·세션·화면 흐름 검증이다. 쓰기/CAS/취소/재시도는 앞선 격리DB와 fixture E2E 검증을 유지하며, 운영 데이터에 임의의 변경을 만들어 재시험하지 않았다. 배포 후 정기 수집은 기존 정상 스케줄에 따라 실행된다.
