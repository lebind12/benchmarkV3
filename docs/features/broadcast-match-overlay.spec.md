# Broadcast Match Overlay Spec

상위 요구사항: `docs/features/broadcast-match-overlay.md`

## 1. 목표

방송 소프트웨어가 캡처할 수 있는 1920x1080 기준 매치 오버레이 목업을 만든다. 축구 정보 UI 는 캐릭터 주변 슬롯에만 배치하고 중앙 캐릭터 세이프존은 유지한다.

## 2. 레이아웃

전체 stage 는 `100vw x 100vh`, `display:flex`, `flex-direction:column` 이다.

| 영역 | 비율 | 정책 |
|---|---:|---|
| top row | height 14% | 중앙 스코어보드만 배치 |
| body row | height 100% | 좌측 라인업, 중앙 세이프존, 우측 하단 스탯. top row 는 absolute overlay 로 겹쳐 배치 |
| left column | width 22% | 양 팀 포메이션 카드 세로 배치 |
| center safe zone | width 56% | 상시 UI 금지, 하단 이벤트 팝업 예외 |
| right column | width 22% | 상단 50% 예약/비움, 하단 50% 스탯 |

모든 주요 width/height 는 `%`, `flex-basis`, `flex` 기준이다. 송출 기준은 1920x1080 이다.

## 3. 크로마키 / 투명도

- stage 배경만 `#00B140` 을 사용한다.
- UI 컴포넌트는 `#00B140` 또는 유사 녹색을 사용하지 않는다.
- 투명도/광택 효과는 허용하되, 크로마키 배경색이 UI 내부로 비쳐 키잉 문제가 생기지 않도록 불투명 panel 위에만 올린다.
- `backdrop-filter` 로 stage 배경을 직접 샘플링하는 효과는 사용하지 않는다.

## 4. 테마

지원 테마:
- `premier-league`
- `champions-league`
- `europa-league`
- `carabao-cup`
- `fa-cup`
- `world-cup-2026`

리그별 차이는 색상, 프레임 형태, 패턴 강도, 이벤트 강조색으로 제한한다. 정보 구조는 동일하다.

## 5. 이벤트 팝업

중앙 하단 예외 슬롯에만 표시한다.

구조:
- 좌측 원형 로고 객체
- 우측 라운딩 카드
- 상단 박스: 이벤트 제목
- 하단 박스: 이벤트 상세

동작:
- 아래에서 위로 등장
- 약 7초 유지
- 아래로 내려가며 사라짐
- mock 단계에서는 goal/substitution/card/VAR/stat 이벤트를 순환 표시한다.

## 6. URL

- 직접 엔트리: `/broadcast.html?fixtureId=1000001&league=premier-league`
- 앱 라우트 브릿지: `/broadcast/fixtures/1000001?league=premier-league`

## 7. 라이브 데이터

기본은 기존 mock 데이터를 유지한다. 방송용 live mode 에서는 FE handler 가 API-Football 을 직접 호출한다.

관련 명세: `docs/spec/broadcast-api-football-live-fe.md`

정책:
- FastAPI 백엔드 endpoint 를 사용하지 않는다.
- `/api/v1/...` 경로를 호출하지 않는다.
- `fixture` query 가 있으면 해당 API-Football fixture id 를 사용한다.
- `fixture` query 가 없으면 `/fixtures?live=all` 의 첫 live fixture 를 사용한다.
- polling 기본 주기는 10초다.
