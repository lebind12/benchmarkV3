<script setup lang="ts">
import goalBallUrl from '@/assets/broadcast/goal-soccer-ball.svg?url'
import brazilFlagUrl from '@/assets/broadcast/flags/br.svg?url'
import koreaFlagUrl from '@/assets/broadcast/flags/kr.svg?url'

type BottomVariantKind =
  | 'trophy-seal'
  | 'flag-canvas'
  | 'host-map'
  | 'medal-bar'
  | 'ticket-stub'
  | 'group-table'
  | 'knockout-bracket'
  | 'ball-orbit'
  | 'tri-host'
  | 'passport-stamp'
  | 'stadium-lights'
  | 'pennant-stack'
  | 'podium-strip'
  | 'net-mesh'
  | 'broadcast-plaque'
  | 'glass-ribbon'
  | 'route-line'
  | 'mosaic-tile'
  | 'confetti-gate'
  | 'data-ticker'

type BottomVariant = {
  id: string
  title: string
  source: string
  feedback: string
  next: string
  kind: BottomVariantKind
}

const match = {
  home: '대한민국',
  away: '브라질',
  homeCode: 'KOR',
  awayCode: 'BRA',
  score: '1 : 1',
  clock: '63:10',
  eventMinute: '58:21',
  eventTitle: '동점골',
  player: '손흥민',
  statTitle: '점유율',
  statValue: '61% - 39%',
  detail: '빠른 전환 이후 박스 중앙에서 경기를 원점으로 돌립니다',
}

const variants: BottomVariant[] = [
  {
    id: 'W01',
    title: 'Trophy Seal Band',
    source: '대회 엠블럼형 공식 패키지',
    feedback: '왼쪽 원형 씰 하나로 월드컵 인지가 빠르다. 본 페이지 이식 난이도도 낮다.',
    next: '기본 하단 캐러셀 후보',
    kind: 'trophy-seal',
  },
  {
    id: 'W02',
    title: 'Flag Canvas Sweep',
    source: '국가대항전 국기 리본',
    feedback: '국가전 감성이 가장 직접적이다. 국기 면적이 커서 월드컵 느낌이 강하다.',
    next: '골/킥오프 이벤트 후보',
    kind: 'flag-canvas',
  },
  {
    id: 'W03',
    title: 'Host Cities Map Strip',
    source: '2026 북미 개최 도시 지도 그래픽',
    feedback: '월드컵 2026만의 개최지 맥락이 생긴다. 스탯 카드보다 오프닝/대기 카드에 좋다.',
    next: '프리매치/하프타임 후보',
    kind: 'host-map',
  },
  {
    id: 'W04',
    title: 'Gold Medal Plate',
    source: '시상식 메달/플레이트',
    feedback: '골드와 블랙이 고급스럽고 방송 그래픽처럼 보인다. 점수/평점 카드에 잘 맞다.',
    next: 'Player spotlight 후보',
    kind: 'medal-bar',
  },
  {
    id: 'W05',
    title: 'Match Ticket Stub',
    source: '월드컵 티켓/입장권',
    feedback: '좌우 절취선 때문에 다른 후보와 형태가 확실히 다르다. 이벤트 로그 느낌이 강하다.',
    next: '이벤트 큐 후보',
    kind: 'ticket-stub',
  },
  {
    id: 'W06',
    title: 'Group Table Snapshot',
    source: '조별리그 순위표',
    feedback: '월드컵의 조별리그 맥락을 직접 전달한다. 일반 스탯보다 대회 상황 설명에 적합하다.',
    next: '조별 순위 보조정보 후보',
    kind: 'group-table',
  },
  {
    id: 'W07',
    title: 'Knockout Bracket Rail',
    source: '토너먼트 브라켓',
    feedback: '좌우 레일이 토너먼트 구조를 떠올리게 한다. 후반부 라운드에서 강하다.',
    next: '16강 이후 후보',
    kind: 'knockout-bracket',
  },
  {
    id: 'W08',
    title: 'Match Ball Orbit',
    source: '공 궤적/월드컵 볼 그래픽',
    feedback: '아이콘 중심이라 캐릭터성은 있지만 공식감은 약하다. 골 이벤트에 적합하다.',
    next: '골/슈팅 후보',
    kind: 'ball-orbit',
  },
  {
    id: 'W09',
    title: 'Tri-host Split',
    source: '미국/캐나다/멕시코 공동개최',
    feedback: '2026 월드컵 고유성을 강하게 준다. 팀 정보보다 대회 브랜딩이 앞선다.',
    next: '월드컵 전용 idle 후보',
    kind: 'tri-host',
  },
  {
    id: 'W10',
    title: 'Passport Stamp',
    source: '국가 이동/여권 스탬프',
    feedback: '여행과 국가대항전 느낌이 있다. 비주얼 차별화는 좋지만 긴 텍스트에는 좁다.',
    next: '경기장/도시 정보 후보',
    kind: 'passport-stamp',
  },
  {
    id: 'W11',
    title: 'Stadium Lights',
    source: '경기장 조명/프라임타임',
    feedback: '방송 화면과 가장 자연스럽게 붙는다. 월드컵 표식은 별도 배지로 보강해야 한다.',
    next: '범용 하단 바 후보',
    kind: 'stadium-lights',
  },
  {
    id: 'W12',
    title: 'Pennant Stack',
    source: '국가 페넌트/응원 깃발',
    feedback: '좌측 페넌트가 월드컵을 한눈에 만든다. 반복 캐러셀에서 리듬감이 좋다.',
    next: '스탯 순환 후보',
    kind: 'pennant-stack',
  },
  {
    id: 'W13',
    title: 'Podium Strip',
    source: '시상대/랭킹 그래픽',
    feedback: '숫자 3개가 필요한 카드에 적합하다. 단일 이벤트보다 선수/스탯 비교에 좋다.',
    next: 'MOTM/평점 후보',
    kind: 'podium-strip',
  },
  {
    id: 'W14',
    title: 'Goal Net Mesh',
    source: '골망/득점 순간',
    feedback: '축구 자체가 가장 강하게 느껴진다. 월드컵 배지는 왼쪽 씰로 보완한다.',
    next: '골/슈팅 후보',
    kind: 'net-mesh',
  },
  {
    id: 'W15',
    title: 'Official Plaque Minimal',
    source: '공식 경기 기록 플라크',
    feedback: '가장 절제되어 실제 중계와 잘 맞는다. 월드컵 요소는 텍스트/금박만 사용한다.',
    next: '보수적 채택 후보',
    kind: 'broadcast-plaque',
  },
  {
    id: 'W16',
    title: 'Soft Glass Ribbon',
    source: '최신 스포츠 UI 글래스 리본',
    feedback: '광택이 있으나 과하지 않다. 배경 영상 밖이므로 투명도 활용 가능하다.',
    next: '현대적 후보',
    kind: 'glass-ribbon',
  },
  {
    id: 'W17',
    title: 'Travel Route Line',
    source: '개최 도시 이동 경로',
    feedback: '월드컵 투어 느낌이 강하다. 경기 중보다는 경기 전/후 카드에 좋다.',
    next: '도시/일정 카드 후보',
    kind: 'route-line',
  },
  {
    id: 'W18',
    title: 'Mosaic Tile',
    source: '월드컵 팬 페스티벌/국기 모자이크',
    feedback: '다양한 국가가 모이는 대회감이 있다. 배경 패턴이 강해 가독성 조절이 필요하다.',
    next: '축제감 후보',
    kind: 'mosaic-tile',
  },
  {
    id: 'W19',
    title: 'Confetti Gate',
    source: '개막식/득점 세리머니',
    feedback: '이벤트성은 가장 강하다. 상시 스탯 카드에는 다소 화려할 수 있다.',
    next: '골/승리 이벤트 후보',
    kind: 'confetti-gate',
  },
  {
    id: 'W20',
    title: 'Data Ticker Crest',
    source: '방송 데이터 ticker + 대회 배지',
    feedback: '정보 전달력이 가장 높다. 월드컵 감성은 좌측 대형 배지와 상단 리본으로 만든다.',
    next: '실사용 안정 후보',
    kind: 'data-ticker',
  },
]

function flagForCode(code: string) {
  return code === 'BRA' ? brazilFlagUrl : koreaFlagUrl
}
</script>

<template>
  <main class="bottom-lab-page" data-testid="program-bottom-lab-page">
    <header class="lab-header">
      <div>
        <span>Broadcast Program Bottom Lab</span>
        <h1>월드컵 하단 캐러셀 디자인 후보 20종</h1>
      </div>
      <p>중계화면 밖 좌측 하단 22% 영역에 적용할 World Cup identity 후보입니다.</p>
    </header>

    <section class="variant-list" data-testid="program-bottom-variant-list">
      <article
        v-for="variant in variants"
        :key="variant.id"
        class="variant-row"
        :data-variant="variant.kind"
        data-testid="program-bottom-variant-tile"
      >
        <aside class="variant-meta">
          <strong>{{ variant.id }}. {{ variant.title }}</strong>
          <span>{{ variant.source }}</span>
          <p>{{ variant.feedback }}</p>
          <b>{{ variant.next }}</b>
        </aside>

        <section :class="['bottom-prototype', `bottom-prototype--${variant.kind}`]">
          <template v-if="variant.kind === 'trophy-seal'">
            <div class="cup-seal">WC<br />26</div>
            <div class="proto-copy">
              <span>FIFA WORLD CUP 2026</span>
              <strong>{{ match.statTitle }}</strong>
              <p>{{ match.detail }}</p>
            </div>
            <div class="proto-values"><b>61%</b><i>{{ match.statValue }}</i><b>39%</b></div>
          </template>

          <template v-else-if="variant.kind === 'flag-canvas'">
            <div class="flag-card flag-home"><img :src="flagForCode(match.homeCode)" alt="" /></div>
            <div class="flag-copy">
              <span>{{ match.eventMinute }} · {{ match.homeCode }}</span>
              <strong>{{ match.eventTitle }}</strong>
              <p>{{ match.player }} · {{ match.score }}</p>
            </div>
            <div class="flag-card flag-away"><img :src="flagForCode(match.awayCode)" alt="" /></div>
          </template>

          <template v-else-if="variant.kind === 'host-map'">
            <div class="map-line">
              <span>VAN</span><span>TOR</span><span>NYC</span><span>MEX</span><span>LA</span>
            </div>
            <div class="map-copy">
              <b>GROUP STAGE</b>
              <strong>{{ match.home }} vs {{ match.away }}</strong>
              <p>2026 host route graphic · live match context</p>
            </div>
          </template>

          <template v-else-if="variant.kind === 'medal-bar'">
            <div class="medal medal-left">1</div>
            <div class="medal-copy">
              <span>PLAYER SPOTLIGHT</span>
              <strong>{{ match.player }}</strong>
              <p>2골 · 평점 8.2 · 박스 안 터치 6회</p>
            </div>
            <div class="medal-score">8.2</div>
          </template>

          <template v-else-if="variant.kind === 'ticket-stub'">
            <div class="ticket-edge"></div>
            <div class="ticket-main">
              <span>MATCH EVENT · {{ match.eventMinute }}</span>
              <strong>{{ match.eventTitle }}</strong>
              <p>{{ match.homeCode }} {{ match.score }} {{ match.awayCode }}</p>
            </div>
            <div class="ticket-code">WC2026</div>
          </template>

          <template v-else-if="variant.kind === 'group-table'">
            <div class="group-title">GROUP B</div>
            <div class="group-row"><b>{{ match.homeCode }}</b><span>4 pts</span><i>+2</i></div>
            <div class="group-row"><b>{{ match.awayCode }}</b><span>3 pts</span><i>+1</i></div>
            <div class="group-note">현재 스코어 기준 순위 변동</div>
          </template>

          <template v-else-if="variant.kind === 'knockout-bracket'">
            <div class="bracket"><span></span><span></span><span></span></div>
            <div class="bracket-copy">
              <span>ROUND OF 16 PATH</span>
              <strong>{{ match.homeCode }} {{ match.score }} {{ match.awayCode }}</strong>
              <p>승자는 8강 라인으로 이동</p>
            </div>
            <div class="bracket"><span></span><span></span><span></span></div>
          </template>

          <template v-else-if="variant.kind === 'ball-orbit'">
            <div class="orbit">
              <img :src="goalBallUrl" alt="" />
              <span></span>
            </div>
            <div class="orbit-copy">
              <span>GOAL MOMENT</span>
              <strong>{{ match.eventTitle }}</strong>
              <p>{{ match.player }} · {{ match.detail }}</p>
            </div>
          </template>

          <template v-else-if="variant.kind === 'tri-host'">
            <div class="host-pill">CAN</div>
            <div class="host-pill host-main">USA</div>
            <div class="host-pill">MEX</div>
            <div class="host-copy"><strong>WORLD CUP 2026</strong><span>{{ match.homeCode }} / {{ match.awayCode }}</span></div>
          </template>

          <template v-else-if="variant.kind === 'passport-stamp'">
            <div class="stamp">APPROVED<br />WC26</div>
            <div class="stamp-copy">
              <span>MATCH PASSPORT</span>
              <strong>{{ match.home }} - {{ match.away }}</strong>
              <p>{{ match.clock }} · {{ match.statValue }}</p>
            </div>
          </template>

          <template v-else-if="variant.kind === 'stadium-lights'">
            <div class="lights"><span></span><span></span><span></span><span></span></div>
            <div class="light-copy">
              <span>LIVE FROM THE STADIUM</span>
              <strong>{{ match.statTitle }} {{ match.statValue }}</strong>
              <p>최근 10분 경기 주도권 변화</p>
            </div>
          </template>

          <template v-else-if="variant.kind === 'pennant-stack'">
            <div class="pennants"><span>KOR</span><span>WC</span><span>BRA</span></div>
            <div class="pennant-copy">
              <span>NATIONAL TEAM MATCH</span>
              <strong>{{ match.eventTitle }}</strong>
              <p>{{ match.eventMinute }} · {{ match.player }}</p>
            </div>
          </template>

          <template v-else-if="variant.kind === 'podium-strip'">
            <div class="podium-step second">7.4</div>
            <div class="podium-step first">8.2</div>
            <div class="podium-step third">7.1</div>
            <div class="podium-copy"><strong>{{ match.player }}</strong><span>PLAYER RATING LEADER</span></div>
          </template>

          <template v-else-if="variant.kind === 'net-mesh'">
            <div class="net-badge">GOAL</div>
            <div class="net-copy">
              <span>{{ match.eventMinute }}</span>
              <strong>{{ match.player }}</strong>
              <p>{{ match.detail }}</p>
            </div>
            <div class="net-score">{{ match.score }}</div>
          </template>

          <template v-else-if="variant.kind === 'broadcast-plaque'">
            <div class="plaque-top">FIFA WORLD CUP 2026 · LIVE DATA</div>
            <div class="plaque-main">
              <b>{{ match.homeCode }}</b>
              <strong>{{ match.statValue }}</strong>
              <b>{{ match.awayCode }}</b>
            </div>
            <div class="plaque-bottom">POSSESSION CONTROL</div>
          </template>

          <template v-else-if="variant.kind === 'glass-ribbon'">
            <div class="glass-tag">WC26</div>
            <div class="glass-copy">
              <span>LIVE MATCH INFO</span>
              <strong>{{ match.eventTitle }}</strong>
              <p>{{ match.homeCode }} {{ match.score }} {{ match.awayCode }} · {{ match.eventMinute }}</p>
            </div>
          </template>

          <template v-else-if="variant.kind === 'route-line'">
            <div class="route"><span>SEA</span><i></i><span>DAL</span><i></i><span>MEX</span></div>
            <div class="route-copy">
              <strong>{{ match.home }} pressure rising</strong>
              <p>최근 10분 왼쪽 하프스페이스 공격 집중</p>
            </div>
          </template>

          <template v-else-if="variant.kind === 'mosaic-tile'">
            <div class="mosaic-grid"><span v-for="cell in 16" :key="cell"></span></div>
            <div class="mosaic-copy">
              <span>FAN WALL</span>
              <strong>{{ match.homeCode }} {{ match.score }} {{ match.awayCode }}</strong>
              <p>{{ match.eventTitle }} · {{ match.player }}</p>
            </div>
          </template>

          <template v-else-if="variant.kind === 'confetti-gate'">
            <div class="confetti"><span v-for="cell in 18" :key="cell"></span></div>
            <div class="gate-copy">
              <span>CELEBRATION</span>
              <strong>{{ match.eventTitle }}</strong>
              <p>{{ match.player }} · {{ match.score }}</p>
            </div>
          </template>

          <template v-else>
            <div class="ticker-badge">WORLD CUP<br />2026</div>
            <div class="ticker-line">
              <b>{{ match.clock }}</b>
              <strong>{{ match.statTitle }}</strong>
              <span>{{ match.statValue }}</span>
              <i>{{ match.homeCode }} / {{ match.awayCode }}</i>
            </div>
          </template>
        </section>
      </article>
    </section>
  </main>
</template>

<style scoped>
*,
*::before,
*::after {
  box-sizing: border-box;
}

.bottom-lab-page {
  min-height: 100vh;
  padding: 2.4rem;
  background:
    radial-gradient(circle at 13% 2%, rgba(201, 151, 43, 0.24), transparent 26rem),
    linear-gradient(135deg, #050505 0%, #10100e 52%, #060914 100%);
  color: #f5f1e8;
  font-family:
    'Avenir Next Condensed',
    'DIN Condensed',
    'Pretendard',
    system-ui,
    sans-serif;
  letter-spacing: 0;
}

.lab-header {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 2rem;
  margin-bottom: 2rem;
}

.lab-header span,
.variant-meta span,
.variant-meta b,
.bottom-prototype span {
  font-weight: 950;
  letter-spacing: 0;
  text-transform: uppercase;
}

.lab-header span {
  color: #c9972b;
  font-size: 1rem;
}

.lab-header h1 {
  margin: 0.25rem 0 0;
  font-size: 3rem;
  line-height: 1;
}

.lab-header p {
  max-width: 36rem;
  margin: 0;
  color: #d9cfae;
  font-size: 1.1rem;
  font-weight: 800;
  line-height: 1.35;
  text-align: right;
}

.variant-list {
  display: flex;
  flex-direction: column;
  gap: 1.1rem;
}

.variant-row {
  display: grid;
  grid-template-columns: 22rem 1fr;
  gap: 1rem;
  min-height: 14.8rem;
}

.variant-meta {
  padding: 1rem;
  background: #111111;
  border: 0.08rem solid rgba(201, 151, 43, 0.38);
  border-radius: 0.5rem;
  box-shadow: inset 0 0 0 0.08rem rgba(245, 241, 232, 0.04);
}

.variant-meta strong {
  display: block;
  color: #ffffff;
  font-size: 1.35rem;
  line-height: 1.05;
}

.variant-meta span {
  display: block;
  margin-top: 0.55rem;
  color: #c9972b;
  font-size: 0.82rem;
}

.variant-meta p {
  margin: 0.8rem 0 0;
  color: #d9cfae;
  font-size: 0.98rem;
  font-weight: 750;
  line-height: 1.35;
}

.variant-meta b {
  display: inline-block;
  margin-top: 0.8rem;
  padding: 0.25rem 0.55rem;
  background: #050505;
  border: 0.08rem solid #c9972b;
  border-radius: 999rem;
  color: #f5f1e8;
  font-size: 0.72rem;
}

.bottom-prototype {
  position: relative;
  min-height: 14.8rem;
  overflow: hidden;
  display: flex;
  align-items: center;
  gap: 1.4rem;
  padding: 1.35rem 1.65rem;
  background:
    linear-gradient(90deg, rgba(200, 16, 46, 0.22), transparent 29%, rgba(0, 52, 120, 0.25)),
    linear-gradient(180deg, #151515 0%, #050505 100%);
  border: 0.12rem solid #c9972b;
  border-radius: 0.55rem;
  box-shadow:
    inset 0 0.7rem 2rem rgba(255, 255, 255, 0.06),
    0 0.8rem 2.2rem rgba(0, 0, 0, 0.3);
}

.bottom-prototype::before {
  content: '';
  position: absolute;
  inset: 0 0 auto;
  height: 0.48rem;
  background: linear-gradient(90deg, #c8102e 0 16%, #f5f1e8 16% 30%, #c9972b 30% 56%, #003478 56% 80%, #c8102e 80%);
}

.bottom-prototype strong {
  display: block;
  color: #ffffff;
  font-size: clamp(2rem, 3vw, 4rem);
  font-weight: 950;
  line-height: 0.95;
}

.bottom-prototype p {
  margin: 0.45rem 0 0;
  color: #f6e1a8;
  font-size: 1.22rem;
  font-weight: 850;
  line-height: 1.25;
}

.proto-copy,
.flag-copy,
.map-copy,
.medal-copy,
.ticket-main,
.bracket-copy,
.orbit-copy,
.stamp-copy,
.light-copy,
.pennant-copy,
.podium-copy,
.net-copy,
.glass-copy,
.route-copy,
.mosaic-copy,
.gate-copy {
  position: relative;
  z-index: 2;
  min-width: 0;
  flex: 1 1 auto;
}

.cup-seal,
.flag-card,
.medal,
.ticket-code,
.group-title,
.orbit,
.host-pill,
.stamp,
.net-badge,
.glass-tag,
.ticker-badge {
  position: relative;
  z-index: 2;
  flex: 0 0 auto;
}

.cup-seal {
  width: 7.8rem;
  aspect-ratio: 1;
  display: grid;
  place-items: center;
  border-radius: 50%;
  background:
    radial-gradient(circle at 34% 25%, rgba(255, 255, 255, 0.72), transparent 24%),
    linear-gradient(135deg, #f5f1e8, #c9972b 48%, #7b4d11);
  color: #050505;
  font-size: 2rem;
  font-weight: 950;
  line-height: 0.9;
  text-align: center;
  box-shadow: 0 0 0 0.35rem #050505, 0 0 0 0.55rem #c8102e;
}

.proto-values {
  z-index: 2;
  display: grid;
  grid-template-columns: auto auto auto;
  align-items: center;
  gap: 0.9rem;
}

.proto-values b {
  color: #ffffff;
  font-size: 4rem;
  font-weight: 950;
}

.proto-values i {
  color: #c9972b;
  font-style: normal;
  font-weight: 950;
}

.bottom-prototype--flag-canvas {
  justify-content: space-between;
  background:
    linear-gradient(90deg, rgba(200, 16, 46, 0.52), rgba(5, 5, 5, 0.94) 35%, rgba(5, 5, 5, 0.94) 65%, rgba(0, 52, 120, 0.55)),
    #050505;
}

.flag-card {
  width: 11rem;
  height: 7rem;
  overflow: hidden;
  border: 0.18rem solid #f5f1e8;
  border-radius: 0.45rem;
  box-shadow: 0 0.55rem 0 #c9972b;
}

.flag-card img {
  width: 100%;
  height: 100%;
  display: block;
  object-fit: cover;
}

.flag-copy {
  text-align: center;
}

.flag-copy span,
.proto-copy span,
.map-copy b,
.medal-copy span,
.ticket-main span,
.bracket-copy span,
.orbit-copy span,
.stamp-copy span,
.light-copy span,
.pennant-copy span,
.net-copy span,
.glass-copy span,
.mosaic-copy span,
.gate-copy span {
  color: #c9972b;
  font-size: 1rem;
}

.bottom-prototype--host-map {
  background:
    radial-gradient(circle at 20% 70%, rgba(200, 16, 46, 0.3), transparent 28%),
    linear-gradient(105deg, #050505 0%, #111111 48%, #1d1607 100%);
}

.map-line {
  z-index: 2;
  flex: 0 0 42%;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 1rem;
  color: #050505;
}

.map-line::before {
  content: '';
  position: absolute;
  left: 4rem;
  right: 48%;
  height: 0.16rem;
  background: #c9972b;
}

.map-line span {
  z-index: 2;
  display: grid;
  place-items: center;
  width: 3.8rem;
  aspect-ratio: 1;
  border-radius: 50%;
  background: #f5f1e8;
  color: #050505;
  box-shadow: 0 0 0 0.22rem #c9972b;
}

.bottom-prototype--medal-bar {
  background:
    linear-gradient(90deg, #050505, #17110a 52%, #050505),
    #050505;
}

.medal {
  width: 7rem;
  aspect-ratio: 1;
  display: grid;
  place-items: center;
  border-radius: 50%;
  background: radial-gradient(circle at 35% 25%, #ffffff, #c9972b 42%, #5e3709);
  color: #050505;
  font-size: 3.4rem;
  font-weight: 950;
}

.medal-score {
  z-index: 2;
  padding: 1.1rem 1.35rem;
  background: #c9972b;
  border-radius: 0.3rem;
  color: #050505;
  font-size: 3.8rem;
  font-weight: 950;
}

.bottom-prototype--ticket-stub {
  background: #f5f1e8;
  color: #050505;
  border-color: #c8102e;
}

.bottom-prototype--ticket-stub::before {
  height: 100%;
  width: 0.5rem;
  background: repeating-linear-gradient(180deg, #c8102e 0 0.6rem, #003478 0.6rem 1.2rem, #c9972b 1.2rem 1.8rem);
}

.ticket-edge {
  position: absolute;
  top: -1.2rem;
  bottom: -1.2rem;
  left: 13rem;
  width: 1.2rem;
  background: radial-gradient(circle, #050505 0 0.28rem, transparent 0.3rem) 0 0 / 1.2rem 1.2rem;
}

.ticket-main strong,
.ticket-main p,
.ticket-code {
  color: #050505;
}

.ticket-code {
  margin-left: auto;
  padding: 1rem 1.2rem;
  border: 0.16rem solid #050505;
  border-radius: 0.35rem;
  transform: rotate(-7deg);
  color: #c8102e;
  font-size: 1.35rem;
  font-weight: 950;
}

.bottom-prototype--group-table {
  display: grid;
  grid-template-columns: 14rem 1fr 1fr 18rem;
  gap: 0.8rem;
  background: linear-gradient(90deg, #050505, #121212);
}

.group-title,
.group-row,
.group-note {
  z-index: 2;
}

.group-title {
  display: grid;
  place-items: center;
  height: 100%;
  background: #c9972b;
  color: #050505;
  font-size: 2rem;
  font-weight: 950;
}

.group-row {
  display: grid;
  grid-template-columns: 1fr auto auto;
  align-items: center;
  gap: 1rem;
  padding: 1rem;
  border: 0.08rem solid rgba(245, 241, 232, 0.26);
}

.group-row b {
  font-size: 3rem;
}

.group-row span,
.group-row i {
  color: #f6e1a8;
  font-size: 1.5rem;
  font-style: normal;
  font-weight: 950;
}

.group-note {
  align-self: stretch;
  display: grid;
  place-items: center;
  color: #d9cfae;
  font-size: 1.3rem;
  font-weight: 900;
  text-align: center;
}

.bottom-prototype--knockout-bracket {
  justify-content: space-between;
  background: linear-gradient(90deg, #050505, #0b101b 50%, #050505);
}

.bracket {
  z-index: 2;
  width: 11rem;
  height: 8rem;
  display: grid;
  gap: 0.8rem;
}

.bracket span {
  border: 0.12rem solid #c9972b;
  border-left: 0;
}

.bracket-copy {
  text-align: center;
}

.bottom-prototype--ball-orbit {
  background:
    radial-gradient(circle at 13% 50%, rgba(245, 241, 232, 0.18), transparent 18%),
    linear-gradient(90deg, #1a0b10, #050505 48%, #111111);
}

.orbit {
  width: 8.6rem;
  aspect-ratio: 1;
  display: grid;
  place-items: center;
  border: 0.14rem dashed #c9972b;
  border-radius: 50%;
}

.orbit img {
  width: 4.7rem;
}

.orbit span {
  position: absolute;
  width: 1rem;
  aspect-ratio: 1;
  border-radius: 50%;
  background: #c8102e;
  transform: translate(3rem, -3rem);
}

.bottom-prototype--tri-host {
  background: linear-gradient(90deg, #c8102e 0 20%, #050505 20% 80%, #003478 80%);
}

.host-pill {
  display: grid;
  place-items: center;
  width: 7rem;
  height: 7rem;
  border-radius: 50%;
  background: #f5f1e8;
  color: #050505;
  font-size: 1.9rem;
  font-weight: 950;
}

.host-main {
  width: 9rem;
  height: 9rem;
  background: #c9972b;
}

.host-copy {
  margin-left: auto;
  text-align: right;
}

.host-copy strong {
  font-size: 3.6rem;
}

.host-copy span {
  color: #f6e1a8;
  font-size: 1.4rem;
}

.bottom-prototype--passport-stamp {
  background:
    linear-gradient(90deg, rgba(245, 241, 232, 0.08) 0 0.08rem, transparent 0.08rem 3rem),
    #16110c;
}

.stamp {
  width: 9rem;
  height: 6rem;
  display: grid;
  place-items: center;
  border: 0.22rem solid #c8102e;
  border-radius: 0.5rem;
  color: #c8102e;
  font-size: 1.25rem;
  font-weight: 950;
  line-height: 1;
  text-align: center;
  transform: rotate(-8deg);
}

.bottom-prototype--stadium-lights {
  background: linear-gradient(180deg, #070707 0%, #111111 60%, #050505 100%);
}

.lights {
  position: absolute;
  inset: 0 0 auto;
  height: 5rem;
  display: flex;
  justify-content: space-around;
}

.lights span {
  width: 9rem;
  height: 10rem;
  background: linear-gradient(180deg, rgba(245, 241, 232, 0.28), transparent 70%);
  clip-path: polygon(45% 0, 55% 0, 100% 100%, 0 100%);
}

.light-copy {
  margin-left: 2rem;
}

.bottom-prototype--pennant-stack {
  background: #050505;
}

.pennants {
  z-index: 2;
  display: flex;
  gap: 0.6rem;
  align-self: stretch;
}

.pennants span {
  display: grid;
  place-items: center;
  width: 4.8rem;
  background: #c9972b;
  color: #050505;
  clip-path: polygon(0 0, 100% 0, 100% 78%, 50% 100%, 0 78%);
}

.pennants span:first-child {
  background: #c8102e;
  color: #ffffff;
}

.pennants span:last-child {
  background: #003478;
  color: #ffffff;
}

.bottom-prototype--podium-strip {
  align-items: flex-end;
  background: linear-gradient(90deg, #050505, #161616);
}

.podium-step {
  z-index: 2;
  width: 8rem;
  display: grid;
  place-items: center;
  background: #c9972b;
  color: #050505;
  font-size: 2.4rem;
  font-weight: 950;
}

.podium-step.first {
  height: 9rem;
}

.podium-step.second {
  height: 6.8rem;
  background: #f5f1e8;
}

.podium-step.third {
  height: 5.2rem;
  background: #c8102e;
  color: #ffffff;
}

.podium-copy {
  align-self: center;
  margin-left: 2rem;
}

.bottom-prototype--net-mesh {
  background:
    linear-gradient(45deg, rgba(245, 241, 232, 0.12) 0 0.08rem, transparent 0.08rem 1.2rem),
    linear-gradient(-45deg, rgba(245, 241, 232, 0.1) 0 0.08rem, transparent 0.08rem 1.2rem),
    #070707;
}

.net-badge {
  padding: 1.2rem;
  background: #c8102e;
  color: #ffffff;
  font-size: 2.5rem;
  font-weight: 950;
}

.net-score {
  z-index: 2;
  margin-left: auto;
  color: #c9972b;
  font-size: 4rem;
  font-weight: 950;
}

.bottom-prototype--broadcast-plaque {
  display: grid;
  grid-template-rows: auto 1fr auto;
  gap: 0.55rem;
  background: #0b0b0b;
}

.plaque-top,
.plaque-bottom {
  z-index: 2;
  color: #c9972b;
  font-size: 0.95rem;
  font-weight: 950;
  text-align: center;
}

.plaque-main {
  z-index: 2;
  display: grid;
  grid-template-columns: 1fr auto 1fr;
  align-items: center;
  gap: 2rem;
}

.plaque-main b {
  color: #f5f1e8;
  font-size: 2.2rem;
}

.plaque-main b:last-child {
  text-align: right;
}

.plaque-main strong {
  color: #c9972b;
  font-size: 4.3rem;
}

.bottom-prototype--glass-ribbon {
  background:
    linear-gradient(105deg, rgba(245, 241, 232, 0.12), rgba(245, 241, 232, 0.03)),
    linear-gradient(90deg, #050505, #101010);
}

.glass-tag {
  display: grid;
  place-items: center;
  width: 7rem;
  height: 7rem;
  border: 0.12rem solid rgba(245, 241, 232, 0.58);
  border-radius: 0.5rem;
  background: rgba(245, 241, 232, 0.12);
  color: #f5f1e8;
  font-size: 1.5rem;
  font-weight: 950;
  text-align: center;
}

.bottom-prototype--route-line {
  background:
    radial-gradient(circle at 16% 56%, rgba(201, 151, 43, 0.25), transparent 18%),
    #070707;
}

.route {
  z-index: 2;
  flex: 0 0 42%;
  display: flex;
  align-items: center;
  gap: 0.8rem;
}

.route span {
  display: grid;
  place-items: center;
  width: 4.6rem;
  aspect-ratio: 1;
  border-radius: 50%;
  background: #f5f1e8;
  color: #050505;
}

.route i {
  flex: 1;
  border-top: 0.16rem dashed #c9972b;
}

.bottom-prototype--mosaic-tile {
  background: #050505;
}

.mosaic-grid {
  position: absolute;
  inset: 0;
  display: grid;
  grid-template-columns: repeat(8, 1fr);
  opacity: 0.34;
}

.mosaic-grid span:nth-child(4n + 1) { background: #c8102e; }
.mosaic-grid span:nth-child(4n + 2) { background: #c9972b; }
.mosaic-grid span:nth-child(4n + 3) { background: #003478; }
.mosaic-grid span:nth-child(4n) { background: #f5f1e8; }

.mosaic-copy {
  padding: 1.1rem 1.3rem;
  background: rgba(5, 5, 5, 0.84);
}

.bottom-prototype--confetti-gate {
  justify-content: center;
  text-align: center;
  background: linear-gradient(90deg, #110407, #050505 50%, #100b03);
}

.confetti {
  position: absolute;
  inset: 0;
}

.confetti span {
  position: absolute;
  width: 0.8rem;
  height: 1.6rem;
  background: #c9972b;
  transform: rotate(18deg);
}

.confetti span:nth-child(3n) { background: #c8102e; }
.confetti span:nth-child(4n) { background: #003478; }
.confetti span:nth-child(5n) { background: #f5f1e8; }
.confetti span:nth-child(1) { left: 5%; top: 22%; }
.confetti span:nth-child(2) { left: 11%; top: 68%; }
.confetti span:nth-child(3) { left: 18%; top: 34%; }
.confetti span:nth-child(4) { left: 27%; top: 72%; }
.confetti span:nth-child(5) { left: 35%; top: 20%; }
.confetti span:nth-child(6) { left: 44%; top: 66%; }
.confetti span:nth-child(7) { left: 52%; top: 28%; }
.confetti span:nth-child(8) { left: 61%; top: 72%; }
.confetti span:nth-child(9) { left: 69%; top: 24%; }
.confetti span:nth-child(10) { left: 77%; top: 62%; }
.confetti span:nth-child(11) { left: 84%; top: 18%; }
.confetti span:nth-child(12) { left: 92%; top: 70%; }

.gate-copy {
  max-width: 54rem;
  padding: 1.1rem 2rem;
  background: rgba(5, 5, 5, 0.76);
}

.bottom-prototype--data-ticker {
  background: #050505;
}

.ticker-badge {
  width: 8rem;
  height: 8rem;
  display: grid;
  place-items: center;
  background: #c9972b;
  border-radius: 50%;
  color: #050505;
  font-size: 1.35rem;
  font-weight: 950;
  line-height: 1;
  text-align: center;
}

.ticker-line {
  z-index: 2;
  flex: 1 1 auto;
  display: grid;
  grid-template-columns: 8rem 1fr auto 9rem;
  align-items: center;
  gap: 1.2rem;
  padding: 1.15rem 1.3rem;
  border: 0.12rem solid rgba(201, 151, 43, 0.62);
}

.ticker-line b,
.ticker-line i {
  color: #f6e1a8;
  font-size: 1.45rem;
  font-style: normal;
  font-weight: 950;
}

.ticker-line span {
  color: #c9972b;
  font-size: 2.6rem;
}
</style>
