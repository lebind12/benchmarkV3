# 선수·감독 번역 검수의 리그·팀 조건 검색 (2026-10-25)

사용자 요청: 선수·감독 검색을 리그/팀으로 좁히고 팀 로고가 보이는 검색형 드롭다운 및 수집 대상 리그 로고를 제공한다. 기존 네 탭과 번역/미번역·이름·페이지·편집/충돌 처리는 유지한다.

## 화면과 흐름

- 번역 검수에서 `선수` 또는 `감독` 선택 시 `리그 / 팀` 조건을 표시한다.
- 리그 선택 → 해당 리그의 수집 기록이 있는 팀만 표시. 리그 변경 시 팀 조건을 해제한다. 팀만 선택해도 검색 가능하다.
- 이름/번역 상태/리그/팀은 AND 조합이며 조건 변경은 첫 페이지로 이동한다. entity 종류를 바꾸면 소속 조건을 해제한다.
- `소속 조건 초기화`는 이름·번역 상태를 유지하고 리그/팀만 초기화한다.
- 선수 소속 기준은 DB의 `player_season_stat`, 감독은 아래 `team_coach`/`team_season` 관계다. 보관된 이적 전 소속도 포함한다. 소속 기록이 없는 선수·감독은 조건 없이 이름 검색으로 찾는다. 현재 로스터나 실시간 소속을 추측하지 않는다.
- 같은 사람에게 여러 시즌/대회 기록이 있어도 목록/total에는 한 번만 나타난다. 다른 팀의 리그 기록을 섞지 않으며 잘못된 리그/팀 조합은 0건이다.

## FE가 필요한 API

기존 manager 권한/세션을 사용하고 외부 API를 호출하지 않는다.

- GET `/api/v1/admin/management/translations/affiliation-filters?type=player|coach&league_id=`
  - `{leagues:[{id,name,name_en,logo_url}],teams:[{id,name,name_en,logo_url}]}`
  - id는 내부 PK가 아니라 API-Football external_id. 번역이 있으면 한국어 이름, 없으면 원문.
  - 선택한 종류의 소속 기록이 존재하는 리그/팀만 제공하며 league_id가 있으면 해당 리그의 팀으로 제한한다.
- GET `/api/v1/admin/management/translations?...&type=player|coach&league_id=&team_id=`
  - 기존 `{items,total,page,page_size,missing_count}` 유지.
  - league_id/team_id는 optional positive external ID. 선수·감독 외 타입과 소속 조건 조합은 422.
  - 선수는 같은 player_season_stat row, 감독은 같은 소속 팀의 관계에 league/team 조건을 함께 적용하는 EXISTS. 페이지 적용 전 DB 검색/집계.

DB/마이그레이션 변경 없음. 기존 관계/index 재사용. 검증은 격리 PostgreSQL의 이적/다중시즌/불일치조합/이름·상태·페이지, 목업과 실제 API 화면의 종속 선택/초기화/모바일을 확인한다. 운영 데이터 쓰기·배포·서비스 재시작 없음.

## 감독·로고 추가 요구

- 감독은 team_coach 소속을 사용한다. team_coach.league_id는 마지막 관측 대회이므로 같은 팀의 team_season 리그 참가 기록도 결합한다. 컵 경기에서 마지막으로 관측된 감독도 해당 팀의 리그 조건으로 찾을 수 있다. 리그·팀은 같은 team_coach 팀을 기준으로 결합한다.
- 팀 조건은 로고/한국어·영문 이름을 보여주는 검색형 드롭다운이다. 키보드 이동/Enter 선택/Escape 닫기·포커스 복귀·바깥 클릭 닫기를 지원한다. 모바일에서는 viewport 안에 고정 배치하며, 페이지 스크롤 시 선택 버튼을 따라가고 버튼이 화면 밖으로 나가면 닫힌다.
- 수집 대상 카탈로그와 등록 목록의 logo_url은 기존 DB 필드를 응답에 추가한다. 원본 로고 URL을 이미지로 사용하며 실패/미입력 시 일반 아이콘을 표시한다. 공식 로고를 임의 생성하지 않는다.

## 구현·검증 기록

- 공통 `TranslationsPanel`에서 선수·감독 종류별 조건과 종속 팀 검색을 제공한다. 실제 API와 평가용 목업 모두 연결했다. 기존 서버 manager 권한을 유지한다.
- `TeamScopeSelect`는 body로 팝업을 분리해 패널에서 잘리지 않도록 했으며, 모바일 위/아래 공간에 따라 위치를 정한다. 다른 select의 scroll 및 결과 갱신으로 페이지가 움직일 때 팝업이 닫히던 문제도 수정했다. 실제 API 조건 전환 테스트 3회 연속 통과를 확인했다.
- `ResourceLogo`를 팀 선택·카탈로그·대상 목록에 사용한다. 로고 누락/이미지 오류 fallback을 검증했다. 목록 조회가 외부 축구 API나 데이터 수집을 실행하지 않는다.
- 격리 PostgreSQL 통합 테스트: 기존 관리 7개 + 소속 조건 3개 = **10개 통과**. 이적·다중 시즌 중복 제거, 다른 팀/리그 조합, 이름/번역 상태/페이지, 감독 컵 관측, 한국어 명칭·로고, 비인증 차단을 확인했다.
- 브라우저: 공통 UI 목업 15개, 실제 Vue→FastAPI→격리 PostgreSQL 6개 통과. 실제 외부 API-Football/Upstash는 테스트 fixture이며 유료 외부 호출 검증으로 확대하지 않는다.
- 관련 프론트 단위 테스트 34개, TypeScript/Vite build, 변경 Python 파일 Ruff 통과. 모바일 390px 메뉴 위치와 가로 넘침을 확인했다. 이미지 검증은 응답 URL 및 고정 이미지/fallback을 사용하고 CDN 가용성을 보장하지 않는다.
- 이번 변경에는 DB migration·운영 DB 쓰기·배포가 없다. 기존 개발 서버는 그대로 두고 별도 8016 테스트 서버만 변경된 fixture로 실행했다.
