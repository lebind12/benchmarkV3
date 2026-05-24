# Broadcast Match Program Devplan

상위:
- 요구사항: `docs/features/broadcast-match-program.md`
- 설계 스펙: `docs/features/broadcast-match-program.spec.md`
- 하단 정보 영역 디자인: `docs/spec/broadcast-program-bottom-info-design.md`

## 1. 현재 단계

디자인 시작 단계. 아직 구현하지 않는다.

목표는 사용자가 우측 크로마키 채팅/캐릭터 영역과 좌측 중계화면/하단 정보 큐브 구조를 확인하고, 영상 피드 비가림 정책과 하단 카드 전환 방식을 결정할 수 있도록 설계 문서와 이후 목업 작업 범위를 정리하는 것이다.

## 2. 1차 목업 범위

사용자 승인 후 구현할 1차 목업 범위:

| 파일 후보 | 작업 |
|---|---|
| `frontend/broadcast-program.html` | 새 MPA entry html |
| `frontend/src/broadcastProgram.ts` | Vue mount entry |
| `frontend/src/BroadcastProgramApp.vue` | 중계화면 포함 방송 페이지 mock |
| `frontend/e2e/broadcast-program.spec.ts` | 1920x1080 smoke + layout checks |
| `frontend/tests/unit/BroadcastProgramApp.spec.ts` | query/theme/event-loop 단위 테스트 |

## 3. 컴포넌트 후보

1차는 단일 파일 목업으로 시작하되, 구조는 아래 컴포넌트 경계를 고려한다.

- `ProgramFeedSurface`
- `ProgramBottomCarousel`
- `ProgramInfoCard`
- `ProgramRightReserve`
- `ProgramChatSlot`
- `ProgramCharacterSlot`

## 4. Layout Implementation Notes

P1 기준:

```css
.broadcast-program-stage {
  width: 100vw;
  height: 100vh;
  display: flex;
}

.program-left {
  flex: 0 0 78%;
  display: flex;
  flex-direction: column;
}

.program-right {
  flex: 0 0 22%;
  display: flex;
  flex-direction: column;
}

.feed-surface {
  flex: 0 0 78%;
}

.bottom-info-carousel {
  flex: 0 0 22%;
}

.chat-slot {
  flex: 0 0 78%;
}

.character-slot {
  flex: 0 0 22%;
}
```

원칙:
- 모든 주요 영역은 `%`, `fr`, `flex-basis` 로 정의
- `1920x1080` 기준 스크린샷 검증
- 일반 앱 header/footer 미노출
- 영상 중앙에 상시 UI 배치 금지
- 좌측 중계화면은 좌측 78% 폭 기준 16:9 를 유지하므로 높이도 78%
- 중계화면 내부에는 어떤 웹 UI 도 올리지 않음
- 우측 상단 채팅은 중계화면 높이와 같은 78%, 우측 하단 캐릭터는 남은 22%
- 우측 채팅/캐릭터 영역은 `#00B140` 크로마키 면으로 비워둠
- 주요 스탯/이벤트/보조정보는 좌측 하단에서 한 장씩 크게 순환
- mock 단계에서는 실제 영상 대신 fixture-like visual surface 사용

## 5. 디자인 작업 순서

1. 좌측/우측 비율 78/22 확정
2. 좌측 내부 video/bottom carousel 비율 78/22 확정
3. 영상 placeholder 스타일 확정
4. feed surface 내부 overlay 제거
5. bottom info carousel 구현
6. vertical scroller / cube flip 후보 구현
7. right chat/character chroma reserve 구현
8. World Cup 2026 기준 테마 적용
9. Playwright screenshot 으로 1920x1080 확인

## 6. 테스트 계획 초안

구현 전 testplan 은 사용자 방향 확정 후 별도 작성한다.

최소 검증:
- `/broadcast-program.html?fixtureId=...` 렌더
- `data-league=world-cup-2026` fallback
- feed area 존재
- right chat slot 존재
- right character slot 존재
- bottom info carousel 존재
- feed area 내부에 scorebug/lower-third/event overlay 없음
- right chat/character slot 배경이 `#00B140`
- 1920x1080 에서 영역 overlap 없음
- P1 기준 left/right 78/22, video/bottom 78/22, right chat/character 78/22 비율 허용 오차 내

## 7. BE 의존성

1차 mock 은 BE 신규 작업 불필요.

실 API 교체 시 기존 방송 overlay endpoint 재사용 가능:

- `GET /api/v1/broadcast/fixtures/{external_id}/overlay`

추가 endpoint 는 영상 소스 정책 확정 후 판단한다.
