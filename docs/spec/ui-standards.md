# UI Standards (프론트엔드 통일성 기준)

본 문서는 모든 페이지 / feature 에 일관 적용되는 UI 기준의 SSOT.
개별 feature spec (`docs/features/*.md`) 은 본 문서를 인용하고 위반하지 않는다.

상위:
- 도메인: `@CLAUDE.md`
- FE 워크플로: `@docs/spec/fe-workflow.md`
- 메인 페이지 spec: `@docs/features/main-home.md`

---

## 1. 페이지 스크롤 정책

### 1.1 페이지 자체 스크롤 — **금지**

모든 페이지는 단일 viewport 안에 fit 한다. `body { overflow: hidden }` 또는 동등.

- footer 없음
- 페이지 진입 시 모든 핵심 정보가 한 화면에 들어와야 한다

### 1.2 패널 내부 스크롤 — 허용, 단 **스크롤바 숨김**

콘텐츠가 패널 영역을 초과하면 내부 스크롤 가능. 단 스크롤바 자체는 보이지 않아야 한다.

```css
.panel-scroll {
  overflow-y: auto;
  overflow-x: hidden;
  scrollbar-width: none;          /* Firefox */
}
.panel-scroll::-webkit-scrollbar {
  display: none;                  /* Chrome, Safari, Edge */
}
```

휠 / 트랙패드 / 키보드 스크롤은 정상 동작. 시각적으로만 숨김.

### 1.3 스크롤 가능성 인디케이션

스크롤바가 숨겨지면 사용자가 스크롤 가능함을 알기 어려움. 다음 중 한 방식으로 단서 제공:
- 상/하단 fade-out gradient (콘텐츠가 잘려 있음을 시사)
- 또는 마지막 카드 일부만 살짝 보이게 (잘림 단서)
- 또는 항목이 일정 수 초과 시 "더보기 →" 버튼

(구체 방식은 fe-planner 결정)

---

## 2. Layout 기준

### 2.1 Viewport

- **Baseline**: 1280×720 — 콘텐츠가 최소 padding 으로 fit
- **Fit**: 1440×900 (MacBook) / 1366×768 (구형 노트북)
- **최적**: 1920×1080 — 좌우 패딩 넉넉히 (콘텐츠 max-width 로 중앙 정렬)
- **모바일**: MVP 외

### 2.1.1 좌우 패딩 / max-width 정책 (SSOT)

상하 padding 은 컴포넌트 / panel 마다 자체 결정. **좌우 padding 은 다음 규칙 고정**:

| 화면 폭 | 콘텐츠 max-width | 좌우 padding |
|---|---|---|
| < 1280px | 100% (전체) | 16px |
| 1280–1439 | 100% (전체) | 16px |
| 1440–1919 | 1376px | 32px |
| ≥ 1920 | 1632px | 48px (좌우 144px 여백 자동) |

구현: `.app-container` 유틸 클래스 (또는 동등 layout 단위) 가 위 규칙 캡슐화. 모든 page 의 메인 콘텐츠 영역이 본 컨테이너 안에 들어가야 한다. AppHeader 의 바 자체는 full width 이되 내부 nav 는 `.app-container` 적용.

Tailwind 사용 시: 동등 효과를 `container` + breakpoint 응용으로 표현 가능 (Plans 9.2 완료 시점부터 마이그레이션 허용).

### 2.2 상단 탭 (header)
- 높이: **56px** 고정
- 좌측: 로고 (메인 페이지로 link)
- 중앙/좌측 정렬: 탭 메뉴 (홈/경기/순위/팀/선수/스탯/...)
- 우측: 로그인/프로필 토글, 다크/라이트 모드 토글

### 2.3 메인 콘텐츠 영역
- `height: calc(100vh - 56px)` 보장
- footer 없음
- 패널 분할은 feature 마다 spec (예: 메인은 3패널 25/50/25)

### 2.4 Flex 기반 반응형
- 모든 layout 은 `flex` / `grid` 기반
- 고정 px 보다 `%` / `fr` / `flex-basis` 우선
- 1920 → 1366 까지 자연 축소

---

## 3. 테마

### 3.1 Dark / Light Mode
- shadcn-vue 의 기본 테마 시스템 사용
- 사용자 토글 (localStorage 저장)
- 시스템 prefers-color-scheme 초기 적용

### 3.2 5 리그 색상 팔레트 / 동적 league 테마
- 별도 문서 `docs/spec/league-palette.md` 에서 정의
- 다크/라이트 모드 변형 제공

#### 동적 league 테마 적용 규칙
페이지/콘텐츠가 특정 리그와 연관된 경우 그 league 의 색상 토큰을 **동적으로** 적용:

| 페이지 / 컴포넌트 | 적용 league | 적용 범위 |
|---|---|---|
| **매치 디테일** (`/fixtures/{id}`) | 해당 매치의 `league_id` | 헤더 배경 (subtle gradient) + 서브탭 active + 강조 텍스트 + 골 아이콘 |
| 리그 페이지 (`/standings/{slug}`) | 해당 리그 | 전체 강조 색 |
| 메인 페이지 경기 카드 | 각 경기의 league | 카드 좌측 보더 또는 배지 |
| 순위표 row 의 리그 라벨 | 해당 league | 라벨 배경 |

#### 구현 패턴 (CSS variable swap)
페이지 / 컴포넌트의 root 에 `data-league="<slug>"` 속성 부여 → CSS 가 토큰 swap:

```css
[data-league="premier-league"] {
  --theme-primary:     var(--league-epl-primary);
  --theme-secondary:   var(--league-epl-secondary);
  --theme-accent:      var(--league-epl-accent);
  --theme-on-primary:  var(--league-epl-on-primary);
}
[data-league="champions-league"] {
  --theme-primary:     var(--league-ucl-primary);
  /* ... */
}
/* 5리그 × 다크/라이트 모드 */
```

페이지 내 강조 컴포넌트는 `var(--theme-primary)` 등 일반 토큰 참조 → 페이지 root 의 league 슬러그에 따라 자동 swap.

#### 절제 원칙
- 색상 적용은 **subtle** (배경 전체 채우기 X, 보더 / accent / gradient 일부 등)
- 가독성 우선 (텍스트 대비 WCAG AA 보장)
- 다크 / 라이트 모드 모두 호환

---

## 4. 3D 페이징 패턴 (좌측 큐브 같은 용도)

### 4.1 회전 방식
- **큐브 회전** (transform-style: preserve-3d + rotateY)
- 4 면 = 4 페이지 매핑이 자연

### 4.2 자동 회전
- 10초 간격
- hover 시 정지
- focus 시 정지 (접근성)

### 4.3 인디케이터
- 하단 dot 형식
- 현재 페이지 강조 + 다른 페이지 dot
- 라벨 표시 (예: News / Hot / Transfer / Injury)
- 클릭 시 직접 이동

---

## 5. 컴포넌트 기준 (shadcn-vue)

### 5.1 기본 빌딩 블록
- Button / Card / Tabs / Dialog / Sheet / Dropdown 등 shadcn-vue 컴포넌트 우선 사용
- 임의 재구현 금지 (꼭 필요한 경우 fe-reviewer 검토)

### 5.2 폰트
- 한국어: 시스템 폰트 우선 (Pretendard / 시스템 fallback)
- 영문: shadcn 기본
- 별도 웹폰트 도입은 디자인 단계에서 결정

### 5.3 모서리 / 간격
- shadcn 기본값 따름
- 변경 필요 시 별도 디자인 토큰

---

## 6. 데이터 패널 일반 규칙

### 6.1 카드 리스트 표시
- 1 패널 = 1 데이터 종류
- 패널 내부 항목 (예: 경기 카드, 순위 행) 일관된 디자인
- 항목 클릭 시 상세 페이지로 (탭 또는 같은 페이지의 다른 페이지)

### 6.2 빈 상태
- "데이터 없음" 메시지 + 아이콘
- 또는 placeholder 카드 (스켈레톤)

### 6.3 로딩 상태
- 스켈레톤 카드 (shadcn-vue Skeleton) 권장
- 스피너는 부분적 새로고침 시만

### 6.4 에러 상태
- 패널 단위로 격리 (한 패널 실패가 다른 패널 영향 X)
- "다시 시도" 버튼

---

## 7. 인터랙션 기준

### 7.1 클릭 가능 요소
- `cursor: pointer`
- hover 시 시각 피드백 (배경 / 보더 강조)
- focus 시 outline 표시 (접근성)

### 7.2 필터 / 탭
- 활성 상태 명확 표시
- 클릭 시 즉시 반영 (로딩 표시)

### 7.3 자동 갱신
- 메인 페이지는 자동 polling X (라이브 데이터 메인 표시 안 함)
- 라이브가 필요한 페이지에서만 polling (별도 spec)

---

## 8. 방송용 페이지 예외

방송용 페이지 (`/broadcast/...`) 는 본 문서의 일반 기준에서 예외:
- 배경: 크로마키 `#00B140` (CLAUDE.md §7)
- 1920×1080 송출 환경 가정 (1366×768 최소 동작 면제)
- 콘텐츠 외 모든 UI 요소 (header / footer / 컨트롤) 없음 (송출 시 깨끗한 화면)
- 폰트 크기 송출 환경 가독성 우선 (일반 페이지보다 큼)

별도 spec 은 방송용 feature 작성 시 `docs/features/broadcast-*.md` 에서.

---

## 9. 미정 / 추후 결정

| 항목 | 메모 |
|---|---|
| 정확한 색상 토큰 / 5리그 팔레트 값 | `docs/spec/league-palette.md` 별도 |
| 폰트 결정 (Pretendard 도입?) | 디자인 단계에서 |
| 애니메이션 duration / easing 표준 | shadcn 기본 우선, 필요 시 추가 |
| 빈/로딩/에러 상태 정확한 카피 | fe-planner 가 feature 별 결정 |
| 모바일 대응 — MVP 외 | 사용자 트래픽 보고 결정 |

---

## 10. 적용 범위

- 모든 일반 사용자 페이지 (홈 / 경기 / 순위 / 팀 / 선수 / 스탯 / 인증 등)
- 방송용 페이지는 §8 예외 적용

본 문서 변경 시 PR + 사용자 승인 필수.
