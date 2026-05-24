# Broadcast Match Overlay Testplan

| ID | 레이어 | 시나리오 | 검증 |
|---|---|---|---|
| BMO-U-01 | Unit | 기본 query 없음 | `data-league=premier-league` fallback |
| BMO-U-02 | Unit | `league=world-cup-2026` | 월드컵 테마명/스코어보드 표시 |
| BMO-U-03 | Unit | 중앙 세이프존 | `data-testid=character-safe-zone` 존재 |
| BMO-U-04 | Unit | 우측 상단 예약 영역 | 채팅 UI 대신 empty reserved area |
| BMO-U-05 | Unit | 이벤트 팝업 구조 | logo circle/title/detail 존재 |
| BMO-E-01 | E2E | 1920x1080 broadcast page | score/left/right/event 영역 표시 |
| BMO-E-02 | E2E | route bridge | `/broadcast/fixtures/:id?league=...` 가 `broadcast.html` query 로 이동 |

## Mock 단계 제외

- 실시간 API polling
- STREAMER 인증 guard
- OBS 실제 캡처 검증
