# Broadcast Match Overlay Devplan

## 1. 수정 범위

| 파일 | 작업 |
|---|---|
| `frontend/src/BroadcastApp.vue` | 방송용 오버레이 목업 구현 |
| `frontend/src/broadcast.ts` | 필요한 전역 스타일 import 유지/추가 |
| `frontend/tests/unit/BroadcastApp.spec.ts` | theme/query/event 구조 단위 테스트 |
| `frontend/e2e/broadcast.spec.ts` | 1920x1080 브라우저 smoke |

## 2. 컴포넌트 구조

`BroadcastApp.vue` 내부에서 mock 단계 단일 파일 구현:

- `theme`
- `scoreboard`
- `formation-card`
- `stats-card`
- `event-toast`
- `reserved-chat-zone`
- `character-safe-zone`

## 3. CSS 정책

- `.broadcast-stage` 에만 `background:#00B140`
- UI class 에 chroma green 사용 금지
- `rgba`/광택/투명도는 불투명 패널 위 장식으로만 사용
- `backdrop-filter` 로 크로마키 stage 배경을 직접 샘플링하지 않음
- flex + percentage 기반 슬롯
- shadow/glass 효과는 리그 테마색과 검정 shadow 중심으로 제한

## 4. Query 처리

```ts
const league = new URLSearchParams(window.location.search).get('league')
const fixture = new URLSearchParams(window.location.search).get('fixture')
```

지원하지 않는 league 는 `premier-league` 로 fallback.

## 5. 테스트

- world-cup-2026 query 가 root data-league 로 반영되는지
- 캐릭터 세이프존이 존재하는지
- 우측 상단 예약 영역에 웹 UI 텍스트가 없는지
- 이벤트 팝업에 title/detail/logo 영역이 있는지
- CSS 소스에 금지 토큰이 UI 영역에서 쓰이지 않는지 간단 회귀
