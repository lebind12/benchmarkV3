> **기획 참고 원문 · 2026-11-09 정리**
> 출처: `ax` 워크트리의 `docs/features/ax-name-lookup-lab.md`.
> 요구·설계·결정의 맥락을 보존한 자료입니다. 본문의 구현 완료, 검증 수치, 실행 명령, 작업 경로, 배포 승인은 당시 기록이며 현재 상태나 새 실행 승인이 아닙니다. 현재는 네 워크트리의 개발 코드가 삭제된 기획 보관 상태입니다. 상충하는 과거안은 상위 기획 요약과 최신 결정 기록을 따릅니다.

# AX 이름 조회 점검 화면

2026-10-25. 사용자 승인: 자연어 전체 연동 전에 직접 이름·후보를 확인하는 중간 화면을 추가한다.

## FE 요구와 화면

route `/search/names`, 기존 검색 글래스 배경·Pretendard·보라 accent·light/dark. 검색창을 중심에 두고 아래 후보 리스트, 옆에는 선택된 대상/일치 근거를 배치한다. 모바일은 단일 열. 색상은 기존 검색의 light `#edf1f8/#5846af`, dark `#111827/#bcafff`, 텍스트/테두리는 프로젝트 토큰을 재사용한다. 결과 reveal 한 번 외 장식적 움직임을 추가하지 않고 reduced-motion을 지원한다.

이 화면의 질문은 이름 단위다. `맨유`·`맨시티`·`스미스` 예시, 종류 필터(전체/선수/팀/리그/감독), 최대20후보를 제공한다. 이름 miss에서 오타/부분 일치가 지원되지 않음을 알린다. 잘림은 ‘더 많은 후보가 있어요’로 표시하며 상위 후보가 유일하다고 표현하지 않는다. 후보 선택은 화면 내 확인일 뿐 최종 시즌/소속 확정이나 통계 조회가 아니다.

대상·종류·원문·일치한 표기와 출처(원문/한글/짧은 이름), 선택 상태, snapshot 기준 시각을 보여준다. 내부/외부 ID와 수정 시각은 접을 수 있는 ‘연결 정보’에서만 노출한다. 실제 소속/국적/사진/선수 전체 이름을 새로 추정하지 않는다. 데이터 수정·번역 편집·통계/LLM 호출 없음.

pending/취소/빈 exact 결과/오류·재시도/미인증·세션 만료/선택/새 검색을 구분한다. 중복 제출을 막고 입력/필터 변경 또는 취소·로그아웃 시 이전 결과/선택/늦은 응답을 무효화한다. IME Enter를 제출하지 않으며 키보드 form·radio 후보 선택·focus-visible·status/alert·320px overflow를 검증한다.

## endpoint-request (공개 검색 API 계약 아님)

동일 origin Vite proxy `/api/ax-name-lab` → 별도 localhost API. JSON 계약은 아래 endpoint spec을 따른다.

| Method/path | 요청 | 응답/화면 |
|---|---|---|
| POST `/api/ax-name-lab/session` | `{code:string}` | 204 + HttpOnly 테스트 cookie, 실패401/429 |
| GET `/api/ax-name-lab/session` | cookie | `{authenticated:true, mode:'local_snapshot', role:'USER'}` 또는401 |
| DELETE `/api/ax-name-lab/session` | cookie | 204, 세션 무효화 |
| POST `/api/ax-name-lab/lookup` | `{text, entity_type:null|enum, limit:5|20}` | snapshot 정보·후보·overflow·match kind/source·미지원 한계 |

로그인 성공 후 metadata/snapshot를 별도 무제한 전송하지 않는다. lookup 응답은 최대20개의 실제 후보와 그 일치 근거만 반환한다. FE는 zod로 shape를 검증한다.

## 로컬 점검의 인증 경계

현재 AX 분리 브랜치의 기존 로그인은 user JSON만 반환하고 JWT 세션/활성 사용자 검증 연결은 미완료다. 이를 운영 인증으로 간주하거나 X-Mock-Role로 우회하지 않는다. 별도 launcher가 127.0.0.1에서만 실행하는 로컬 테스트 도구에 임시 접근 코드/서버 세션을 둔다. role USER는 로컬 테스트 identity이며 실제 app_user 계정이 아니다.

운영 `app.main`, 로그인/회원가입 API·스토어를 변경하지 않는다. 이름 lab API도 운영 router에 등록하지 않는다. FE route는 DEV + 명시 VITE_AX_NAME_LAB_ENABLED=true에서만 열리고 production은 not-found로 간다. 실제 로그인 필수 정책은 공개 검색 단계에 그대로 적용하며 이 테스트 세션을 제품 인증으로 확장하지 않는다.

## DoD

선행 화면/API 요구 작성→endpoint spec→구현/실제 snapshot 연결→API unit·실제API Playwright·build·light/dark/mobile 시각 검증. 사용자에게 localhost 주소·테스트 코드·입력 예시와 현재 한계를 전달한다. 별도 포트를 사용하고 관리/메인 세션을 변경하지 않는다. 배포 제외.
