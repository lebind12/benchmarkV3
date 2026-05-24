# League Color Palette

5대 리그 + 2026 FIFA 월드컵의 공식 / 추정 색상 팔레트. 메인 페이지 큐브 / 카드 / 배지 / 강조 부분에 적용.

상위:
- UI 기준: `@docs/spec/ui-standards.md`
- 도메인: `@AGENTS.md`

---

## 1. 색상 분류 원칙

각 리그 / 대회마다 다음 4가지 색상 토큰 정의:

| 토큰 | 의미 | 사용처 예 |
|---|---|---|
| `primary` | 핵심 브랜드 색 | 배지 배경 / 헤더 강조 |
| `secondary` | 보조 색 | 카드 보더 / 호버 |
| `accent` | 강조 / 액션 색 | 버튼 / 라이브 표시 |
| `on-primary` | primary 위 텍스트 색 | 가독성 보장 |

다크/라이트 모드 변형은 shadcn 컨벤션 따름 (라이트는 표시값, 다크는 채도 약간 조정).

---

## 2. Premier League (EPL) — external_id 39

**근거**: [Premier League 공식 brand](https://www.schemecolor.com/premier-league-logo-color.php) — 단일 컬러 "Purple Power" `#3D195B`.

| 토큰 | Hex | 메모 |
|---|---|---|
| primary | `#3D195B` | Purple Power (공식) |
| secondary | `#04F5FF` | Cyan (로고 보조색, 일부 자료) |
| accent | `#E90052` | Pink/Magenta (Premier League 마케팅에 자주 등장) |
| on-primary | `#FFFFFF` | |

---

## 3. UEFA Champions League (UCL) — external_id 2

**근거**: [UEFA 2024-2027 "Kick of Light" 브랜드 가이드](https://www.footyheadlines.com/2024/07/champions-league-2024-2027-visuals-revealed.html) — 공식.

| 토큰 | Hex | 메모 |
|---|---|---|
| primary | `#010056` | Dark Blue (공식) |
| secondary | `#0232FF` | Electric Blue (공식) |
| accent | `#9A00FF` | Purple (rainbow accent 중) |
| on-primary | `#FFFFFF` | |

(추가 accent 가능: `#FF51A2` 마젠타, `#00EEFF` 시안, `#FFD300` 노랑, `#00F084` 그린, `#FF6D4F` 오렌지)

---

## 4. UEFA Europa League (UEL) — external_id 3

**근거**: 2024 리브랜드 로고의 pumpkin orange. 정확 hex 공식 미공개. 일반적 EL orange 추정값 사용.

| 토큰 | Hex | 메모 |
|---|---|---|
| primary | `#FF6D00` | Pumpkin Orange (추정. 공식 발표 시 정정 필요) |
| secondary | `#1A1A1A` | Black (로고 배경) |
| accent | `#FFCC00` | Yellow (trophy 강조) |
| on-primary | `#FFFFFF` | |

⚠️ 공식 hex 미공개. UEFA 브랜드 가이드 입수 시 정정.

---

## 5. Carabao Cup / League Cup — external_id 48

**근거**: Carabao 에너지 음료 브랜드 (대회 스폰서). 빨강 + 노랑.

| 토큰 | Hex | 메모 |
|---|---|---|
| primary | `#D7282F` | Carabao Red (음료 캔 기준 추정) |
| secondary | `#FCB813` | Carabao Yellow (음료 로고 기준 추정) |
| accent | `#000000` | Black (cup logo 외곽) |
| on-primary | `#FFFFFF` | |

⚠️ Carabao 공식 hex 미공개. 추정값.

---

## 6. FA Cup — external_id 45

**근거**: [FA 공식 가이드](https://teamcolorcodes.com/england-national-football-team-color-codes/) — `#011E41` (English FA navy) 확인. FA Cup 자체는 별도 표준 미공개. 일반적 FA red 보조.

| 토큰 | Hex | 메모 |
|---|---|---|
| primary | `#011E41` | FA Navy (공식 영국 FA) |
| secondary | `#E22636` | FA Red (Three Lions 가슴 빨강 일반) |
| accent | `#D4AF37` | Gold (트로피 강조) |
| on-primary | `#FFFFFF` | |

---

## 7. FIFA World Cup 2026 — **사용자 강조: 가장 중요한 대회**

2026 WC 는 미국 / 캐나다 / 멕시코 공동 개최. 32 → 48 팀 확장 첫 대회. 한국 사용자에게 **대한민국 국가대표 출전 (예선 통과)** 이라는 점이 가장 중요.

### 7.1 공식 브랜드 구조 (FIFA 2023-05-17 발표)

[FIFA 공식 발표](https://www.fifa.com/en/articles/world-cup-2026-official-brand-unveiled-canada-mexico-usa-celebration-football-diversity), [Logopedia](https://logos.fandom.com/wiki/2026_FIFA_World_Cup) 확인:

- **기본 색상**: **Black + White**. 로고 자체는 monochromatic
- **트로피 강조**: Gold (정확 hex FIFA 공식 미공개. 일반적 metallic gold 사용)
- **City-specific 시스템**: 16 개 host city 각각 별도 logo / 색상 적용 (LA, Toronto, Guadalajara 등)
- **Country logos**: 3 host country (CAN/MEX/USA) 별도 logo + 색상

### 7.2 우리 사이트 적용 팔레트 (제안)

| 토큰 | Hex | 메모 |
|---|---|---|
| primary | `#000000` | Black (공식 default) |
| secondary | `#FFFFFF` | White (공식 default) |
| accent (cup) | `#D4AF37` | Gold (트로피 / 추정 metallic gold) |
| on-primary | `#FFFFFF` | |

### 7.3 한국 강조 색상 (한국 사용자 친화)

대한민국 출전이라 한국 국가대표 컬러 강조 가능:

| 토큰 | Hex | 메모 |
|---|---|---|
| `--wc2026-korea-red` | `#C60C30` | 태극기 빨강 |
| `--wc2026-korea-blue` | `#003478` | 태극기 파랑 |

대한민국 경기 카드 / 알림에 우선 적용 가능.

### 7.4 Host country 색상 (참고)

| 국가 | Red | 보조 |
|---|---|---|
| 🇨🇦 Canada | `#FF0000` | white |
| 🇲🇽 Mexico | `#006847` (green) | `#CE1126` red, white |
| 🇺🇸 USA | `#B22234` red | `#3C3B6E` blue, white |

위는 국기 색. host country logo 와 같지 않을 수 있음 (각자 별도 디자인).

### 7.5 Bid 시절 색상 (참고용, 현재 미사용)

2018 bid 시 사용된 [United 2026 bid logo](https://brandpalettes.com/united-2026-fifa-world-cup-bid-logo-colors/):
- Average Green `#3CAC3B`, Hermes Blue `#2A398D`, Torch Red `#E61D25`, Light Gray `#D1D4D1`, Dark Heather Grey `#474A4A`

본 색상은 bid 단계 한정. 공식 발표 시 black/white 로 변경됨. 참고만.

### 7.6 운영 정책 제안

- **MVP 외**: WC 2026 은 5 대 리그와 별개. 현재 league 화이트리스트에 미포함
- **2026 6월 (대회 시작 직전)**: ADMIN endpoint 로 WC 2026 league 등록 (`/admin/leagues` POST)
- 사용자 의도 ("가장 중요") 반영: 대회 임박 시 메인 페이지 우상단에 별도 배지 / WC 카운트다운 영역 추가 검토

---

## 8. CSS Custom Properties (적용 예)

`frontend/src/styles/leagues.css` 같은 파일에 정의 (구체 위치는 fe-planner 결정):

```css
:root {
  /* EPL */
  --league-epl-primary:     #3D195B;
  --league-epl-secondary:   #04F5FF;
  --league-epl-accent:      #E90052;
  --league-epl-on-primary:  #FFFFFF;

  /* UCL */
  --league-ucl-primary:     #010056;
  --league-ucl-secondary:   #0232FF;
  --league-ucl-accent:      #9A00FF;
  --league-ucl-on-primary:  #FFFFFF;

  /* UEL */
  --league-uel-primary:     #FF6D00;
  --league-uel-secondary:   #1A1A1A;
  --league-uel-accent:      #FFCC00;
  --league-uel-on-primary:  #FFFFFF;

  /* Carabao */
  --league-carabao-primary:   #D7282F;
  --league-carabao-secondary: #FCB813;
  --league-carabao-accent:    #000000;
  --league-carabao-on-primary:#FFFFFF;

  /* FA Cup */
  --league-fa-primary:     #011E41;
  --league-fa-secondary:   #E22636;
  --league-fa-accent:      #D4AF37;
  --league-fa-on-primary:  #FFFFFF;

  /* WC 2026 (사용자 강조: 가장 중요) */
  --league-wc2026-primary:    #000000;
  --league-wc2026-secondary:  #FFFFFF;
  --league-wc2026-accent:     #D4AF37;    /* gold cup */
  --league-wc2026-on-primary: #FFFFFF;
  /* 대한민국 강조 */
  --wc2026-korea-red:         #C60C30;
  --wc2026-korea-blue:        #003478;
}

/* 다크 모드 변형: primary 를 밝게 (대비 확보), accent 는 채도 유지 */
html.dark {
  /* EPL */
  --league-epl-primary:     #6B3A8C;       /* 3D195B → 살짝 밝게 */
  --league-epl-secondary:   #04F5FF;       /* 동일 */
  --league-epl-accent:      #FF3D7F;       /* E90052 → 살짝 밝게 */
  --league-epl-on-primary:  #FFFFFF;

  /* UCL */
  --league-ucl-primary:     #2A3DAE;       /* 010056 → 밝게 */
  --league-ucl-secondary:   #4A6EFF;
  --league-ucl-accent:      #B566FF;
  --league-ucl-on-primary:  #FFFFFF;

  /* UEL */
  --league-uel-primary:     #FF8C33;       /* FF6D00 → 살짝 밝게 */
  --league-uel-secondary:   #4A4A4A;       /* 1A1A1A → 회색으로 */
  --league-uel-accent:      #FFD633;
  --league-uel-on-primary:  #1A1A1A;

  /* Carabao */
  --league-carabao-primary:   #E8504F;     /* D7282F → 살짝 밝게 */
  --league-carabao-secondary: #FFD24F;
  --league-carabao-accent:    #FFFFFF;     /* 다크 모드는 black 대신 white accent */
  --league-carabao-on-primary:#FFFFFF;

  /* FA Cup */
  --league-fa-primary:      #2B4B7A;       /* 011E41 → 밝게 */
  --league-fa-secondary:    #FF4856;
  --league-fa-accent:       #EEC34A;
  --league-fa-on-primary:   #FFFFFF;

  /* WC 2026 */
  --league-wc2026-primary:    #2A2A2A;     /* 다크 배경 위에서 black 은 안 보이므로 회색 */
  --league-wc2026-secondary:  #E5E5E5;
  --league-wc2026-accent:     #EEC34A;
  --league-wc2026-on-primary: #FFFFFF;
}
```

다크 변형의 hex 는 [chroma.js](https://gka.github.io/chroma.js/) 등으로 L* 채도 조정해 WCAG AA 대비 확보. 위 값은 1차 제안이며 PoC 후 fe-reviewer 검토 결과에 따라 미세 조정 가능.

---

## 9. 슬러그 → 색상 매핑

slug 기반 동적 클래스 적용:

```typescript
// 슬러그 → 토큰 prefix
const LEAGUE_TOKEN: Record<string, string> = {
  'premier-league':     'epl',
  'champions-league':   'ucl',
  'europa-league':      'uel',
  'carabao-cup':        'carabao',
  'fa-cup':             'fa',
}

function leagueColorVar(slug: string, kind: 'primary' | 'secondary' | 'accent' | 'on-primary'): string {
  const token = LEAGUE_TOKEN[slug]
  return token ? `var(--league-${token}-${kind})` : 'var(--muted)'  // fallback
}
```

---

## 10. 미확정 / 검증 필요

| 항목 | 메모 |
|---|---|
| UEL primary hex | 공식 미공개. UEFA 가이드 입수 시 정정 |
| Carabao primary/secondary | 음료 브랜드 추정. 정확값 EFL 가이드 필요 |
| FA Cup primary/secondary | FA navy 는 확정. cup 자체 색상 가이드 미입수 |
| 다크 모드 변형 값 | 8개 모두 디자인 단계에서 실제 표시 확인 후 fine-tune |
| 색 대비 (WCAG AA) | on-primary 색이 primary 배경에서 4.5:1 이상 보장 |

본 문서는 1차 안. 운영 / 디자인 단계에서 실제 보이는 결과 확인 후 정정.

---

## Sources
- [Premier League Logo Color Palette (SchemeColor)](https://www.schemecolor.com/premier-league-logo-color.php)
- [UEFA Champions League 2024-2027 brand reveal (Footy Headlines)](https://www.footyheadlines.com/2024/07/champions-league-2024-2027-visuals-revealed.html)
- [UEFA Europa League brand refresh (RedBee)](https://www.redbeecreative.com/work/uefa-europa-league-brand-refresh)
- [Carabao Cup logo (BrandLogos)](https://brandlogos.net/efl-cup-league-cup-logo-vector-93737.html)
- [England Football Team Color Codes (TeamColorCodes)](https://teamcolorcodes.com/england-national-football-team-color-codes/)
- [FIFA World Cup 2026 Official Brand (FIFA)](https://www.fifa.com/en/articles/world-cup-2026-official-brand-unveiled-canada-mexico-usa-celebration-football-diversity)
- [United 2026 FIFA WC Bid Colors (BrandPalettes)](https://brandpalettes.com/united-2026-fifa-world-cup-bid-logo-colors/)
