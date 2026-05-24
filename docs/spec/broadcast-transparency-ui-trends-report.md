# Broadcast Transparency UI Trends Report

작성일: 2026-05-14

상위 문서:
- `@AGENTS.md`
- `@docs/spec/broadcast-graphics-design-research.md`
- `@docs/spec/league-palette.md`

목적:
- 방송용 오버레이에서 투명도 제한을 완화한 뒤 적용 가능한 최신 UI 트렌드를 정리한다.
- 크로마키 배경(`#00B140`)이 컴포넌트 안으로 비쳐 들어가는 문제는 막되, 불투명한 카드/이미지/패널 위의 광택, 깊이, 반투명 장식은 허용하는 기준을 세운다.

---

## 1. 결론

투명도 완화로 개선할 수 있는 지점은 많다. 다만 이 프로젝트에서는 `glassmorphism` 을 화면 전체에 적용하면 안 된다. 방송 UI는 정보가 즉시 읽혀야 하고, 크로마키 배경이 비치면 합성 품질이 깨진다.

권장 방향:
- 정보 배경은 계속 불투명하게 유지한다.
- 반투명은 카드 내부의 광택, 림 라이트, 패턴, 국기 뱃지 하이라이트, 스탯 바 내부 레이어처럼 제한적으로 쓴다.
- `backdrop-filter` 는 크로마키 배경 위에 직접 쓰지 않는다.
- 텍스트가 올라가는 영역에는 항상 불투명한 backing surface 를 둔다.
- 유리/액체/광택 트렌드는 “재질감”으로만 가져오고, “배경을 비치는 패널”로 가져오지 않는다.

---

## 2. 조사 요약

### 2.1 Liquid Glass / 현대적 glass UI

Apple HIG 의 Materials 문서는 Liquid Glass 를 동적 재질로 설명하며, 콘텐츠를 완전히 가리지 않으면서 컨트롤과 내비게이션을 표현하는 방향을 제시한다.

적용 가능성:
- 스코어보드의 국가 뱃지에 얇은 광택을 얹는 방식
- 이벤트 팝업의 타이틀 바에 빛이 흐르는 듯한 highlight
- 스탯 보드 헤더의 badge/crest 표면 처리

주의:
- Apple 계열 glass UI도 접근성 설정에 따라 투명도 감소/대비 증가가 필요하다.
- 방송 UI에서는 작은 텍스트가 많으므로 Liquid Glass 의 투명 패널을 그대로 쓰면 위험하다.

참고:
- [Apple Human Interface Guidelines - Materials](https://developer.apple.com/design/human-interface-guidelines/materials?changes=_11)

### 2.2 Fluent 2 Materials

Microsoft Fluent 2 는 solid, mica, acrylic, smoke 같은 재질을 구분한다. 핵심은 모든 표면이 같은 투명도가 아니라, 목적별 material 을 선택한다는 점이다.

적용 가능성:
- `solid`: 선수 이름, 점수, 수치 등 정보 핵심 영역
- `mica-like`: 스탯 보드의 큰 배경 카드
- `acrylic-like`: 국기/로고 뱃지의 광택, 이벤트 팝업 상단 장식
- `smoke-like`: 모달/전체 화면 전환 시 dim layer

주의:
- Fluent 도 기술 제약을 확인하고 material 을 선택하라고 안내한다.
- 방송 화면에서는 전체 패널을 acrylic 처럼 만들지 않는다.

참고:
- [Microsoft Fluent 2 - Material](https://fluent2.microsoft.design/material)

### 2.3 backdrop-filter 의 현재 위치

MDN 기준 `backdrop-filter` 는 2024년부터 최신 브라우저 기준 Baseline 으로 분류된다. blur, color shift 같은 효과를 뒤쪽 픽셀에 적용할 수 있다.

적용 가능성:
- OBS/Chromium 기반 브라우저 소스 또는 일반 웹 미리보기에서는 사용 가능성이 있다.
- 중계화면 직접 노출 모드에서는 실제 영상 위에 작은 glass overlay 를 테스트할 수 있다.

주의:
- 크로마키 오버레이 모드에서 컴포넌트 뒤가 `#00B140` 이면, blur 대상이 초록 배경이 된다.
- 그러면 유리 효과가 아니라 녹색이 섞인 오염된 패널이 된다.
- 따라서 `backdrop-filter` 는 크로마키 방송 페이지의 상시 UI에는 기본 비권장이다.

참고:
- [MDN - backdrop-filter](https://developer.mozilla.org/en-US/docs/Web/CSS/Reference/Properties/backdrop-filter)

### 2.4 Figma UI3 / 도구형 UI의 절제

Figma UI3 는 작업물 중심으로 인터페이스를 정리하는 방향을 강조한다. 이는 방송용 화면과도 맞는다. 캐릭터/중계화면이 주인공이고 UI는 보조 정보여야 한다.

적용 가능성:
- 고정 UI는 더 가볍게, 이벤트 UI는 더 선명하게
- 좌우 패널은 정보 밀도를 유지하되 시각적 소음을 줄임
- 도구적 컨트롤은 숨김 디버그 장치로 유지

참고:
- [Figma Blog - Making the move to UI3](https://www.figma.com/blog/making-the-move-to-ui3-a-guide-to-figmas-next-chapter/)

### 2.5 접근성 / 대비 이슈

WCAG 2.2 는 텍스트 대비를 배경 기준으로 평가한다. 반투명 패널은 실제 배경에 따라 대비가 계속 바뀌므로, 방송 화면에서는 특히 위험하다.

적용 가능성:
- 수치/팀명/선수명은 불투명한 chip 위에 둔다.
- 반투명 효과는 텍스트 뒤가 아니라 텍스트 주변 장식으로 둔다.

참고:
- [W3C - WCAG 2.2](https://www.w3.org/TR/WCAG22/)

---

## 3. 방송 UI에 적용할 수 있는 투명도 패턴

### 3.1 Gloss Badge

국기/팀 로고/대회 로고 위에 얇은 반투명 하이라이트를 얹는다.

적용 대상:
- 월드컵 국가 뱃지
- 스탯창 국가 뱃지
- 이벤트 팝업 좌측 로고 원형

구현 원칙:
- 국기 이미지는 실제 asset 을 사용한다.
- 뱃지 자체는 불투명한 원형 컨테이너 안에 둔다.
- 광택은 `rgba(255, 255, 255, 0.25~0.45)` 정도의 pseudo-element 로 처리한다.
- 텍스트를 국기 위에 직접 올리지 않는다.

### 3.2 Glass Header Strip

패널 전체가 아니라 헤더 영역에만 얇은 glass strip 을 둔다.

적용 대상:
- 스탯 보드 상단
- 이벤트 팝업 상단 제목 영역
- 스코어보드 추가시간 영역

구현 원칙:
- 헤더 배경은 불투명한 색상으로 둔다.
- 그 위에 반투명 white/league accent highlight 를 얹는다.
- 헤더 텍스트는 별도 solid text plate 또는 충분한 대비 색상 사용.

### 3.3 Layered Stat Tiles

스탯 항목을 단순 행이 아니라 얇은 레이어를 가진 타일로 만든다.

적용 대상:
- 우측 스탯 보드의 슈팅/유효슈팅/코너킥/패스 성공률

구현 원칙:
- 타일 바닥: 불투명 dark/navy
- 내부 광택: 반투명 highlight
- 수치 영역: 불투명 pill
- 바 차트: 반투명 fill 허용, 단 bar track 은 불투명해야 함

### 3.4 Tactical Overlay

포메이션 필드 위에 전술 구역, 레이더 링, 하프스페이스, 압박 영역을 반투명하게 얹는다.

적용 대상:
- F8 Radar Rings
- Zone Grid
- Half-Space Map
- 듀얼 전술판의 overload/press/space 영역

구현 원칙:
- 필드 배경은 불투명해야 한다.
- overlay 는 필드 내부에서만 사용한다.
- 선수 뱃지와 이름 chip 은 항상 overlay 위에 올라오고 불투명해야 한다.

### 3.5 Event Light Sweep

이벤트 팝업이 등장할 때 상단 헤더에 짧은 빛 sweep 을 준다.

적용 대상:
- 골
- VAR 판정
- 카드
- 교체

구현 원칙:
- 애니메이션은 0.5~0.9초로 짧게.
- 계속 움직이는 효과는 피한다.
- `prefers-reduced-motion` 대응 필요.

---

## 4. 컴포넌트별 개선안

### 4.1 스코어보드

적용:
- 국가 코드 원형 대신 국기 asset 기반 badge.
- badge 위에 얇은 광택 레이어.
- 중앙 점수 pod 는 불투명 ivory/black 기반 유지.
- 추가시간 영역은 gold solid + 아주 얇은 highlight.

비권장:
- 전체 스코어보드에 glass blur.
- 점수 뒤 배경이 비치는 패널.
- 팀명 위에 반투명 배경만 두는 방식.

### 4.2 우측 스탯 보드

적용:
- 국가 뱃지에 gloss badge 사용.
- stat row 는 layered stat tile 로 재구성 가능.
- 점유율 bar 에는 반투명 gloss 를 얹을 수 있음.

비권장:
- 스탯 보드 전체를 반투명 카드로 만들기.
- 작은 수치/라벨을 glass 배경 위에 직접 배치.

### 4.3 좌측 포메이션

적용:
- 필드 내부 레이더 링/zone overlay 에 반투명도 사용 가능.
- 패턴밴드는 불투명 유지.
- 선수 뱃지는 기존 구조 유지. 팀 구분이 필요하면 home/away primary color 만 조정.

비권장:
- 선수 뱃지 자체를 glass/metal 로 바꾸기.
- 선수 이름 chip 을 투명하게 만들기.
- 필드 배경이 크로마키로 비치게 만들기.

### 4.4 이벤트 팝업

적용:
- 좌측 로고 원형에 gloss badge.
- 상단 이벤트 제목 박스에 light sweep.
- 하단 상세 박스는 solid 유지.

비권장:
- 이벤트 팝업 전체 glass card.
- 상세 텍스트 뒤 배경이 비치는 구조.

---

## 5. 구현 가이드

### 5.1 CSS 토큰

권장 토큰:

```css
--surface-solid: #071866;
--surface-raised: #0B2D92;
--surface-ink: #000000;
--surface-ivory: #F5F1E8;
--surface-gold: #D4AF37;
--gloss-white-weak: rgba(255, 255, 255, 0.24);
--gloss-white: rgba(255, 255, 255, 0.42);
--glass-accent-weak: rgba(212, 175, 55, 0.22);
```

### 5.2 금지 규칙

- `#00B140` 을 UI 내부 색상으로 사용 금지.
- `transparent` 배경을 카드/패널의 실제 배경으로 사용 금지.
- `opacity` 를 카드 전체에 적용 금지.
- `backdrop-filter` 를 크로마키 배경 위의 상시 UI에 적용 금지.

### 5.3 허용 규칙

- 불투명한 카드 위의 `rgba(...)` 광택.
- 이미지 asset 위의 `rgba(...)` highlight.
- 불투명한 필드 위의 반투명 tactical overlay.
- 내부 pseudo-element 로 만든 얇은 shine.
- box-shadow / drop-shadow / inset shadow.

### 5.4 검증 기준

- 1920x1080에서 텍스트가 즉시 읽히는가.
- 광택 레이어가 텍스트를 가리지 않는가.
- 크로마키 녹색이 UI 내부에 보이지 않는가.
- OBS 캡처 시 green spill 이 생기지 않는가.
- `prefers-reduced-motion` 상황에서 정보 전달이 유지되는가.

---

## 6. 적용 우선순위

1. 국가/팀 뱃지의 gloss badge 정리.
2. 우측 스탯 보드 row 를 layered stat tile 로 개선.
3. 이벤트 팝업 상단에 light sweep 추가.
4. F8 포메이션 필드의 radar ring overlay 를 더 정교하게 조정.
5. 듀얼 전술판의 overload/press 영역에 반투명 tactical overlay 적용.
6. 중계화면 직접 노출 모드에서만 작은 glass scorebug 테스트.

---

## 7. 구현 리비전

### 7.1 `revision=material`

확인 URL:
- 기본: `/broadcast.html?fixtureId=260506&league=world-cup-2026`
- 투명도/재질감 리비전: `/broadcast.html?fixtureId=260506&league=world-cup-2026&revision=material`

적용 범위:
- 스코어보드: 패널 내부 gloss, inset rim, 국가 뱃지 표면 하이라이트
- 포메이션: 불투명 필드 위 tactical grid/radar overlay
- 스탯 보드: ribbon board 내부 light sweep, 국기 뱃지 gloss, possession bar highlight, stat row tile
- 이벤트 팝업: 로고 원형 객체 gloss, 상/하단 박스 light sweep

디자인 강도:
- 1차 구현은 glass 효과가 방송 상시 UI 대비 과해 보였으므로, 리비전은 낮은 강도의 표면광만 남긴다.
- 큰 패널의 색면은 덮어쓰지 않고 유지한다.
- 광택 레이어는 대부분 `rgba(..., 0.05~0.18)` 범위로 제한한다.

제외:
- 선수 뱃지 구조/크기/색상은 변경하지 않는다.
- 크로마키 배경이 컴포넌트 내부로 비치는 `transparent` 패널은 사용하지 않는다.

---

## 8. 참고 자료

- [Apple Human Interface Guidelines - Materials](https://developer.apple.com/design/human-interface-guidelines/materials?changes=_11)
- [Microsoft Fluent 2 - Material](https://fluent2.microsoft.design/material)
- [MDN - backdrop-filter](https://developer.mozilla.org/en-US/docs/Web/CSS/Reference/Properties/backdrop-filter)
- [W3C - WCAG 2.2](https://www.w3.org/TR/WCAG22/)
- [Figma Blog - Making the move to UI3](https://www.figma.com/blog/making-the-move-to-ui3-a-guide-to-figmas-next-chapter/)
- [Clay - Glassmorphism in UX](https://clay.global/blog/glassmorphism-ui)
- [Pixelmatters - 7 UI design trends to watch in 2026](https://www.pixelmatters.com/insights/7-UI-design-trends-to-watch-in-2026)
