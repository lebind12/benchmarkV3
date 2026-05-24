<script setup lang="ts">
type Player = {
  no: number
  x: number
  y: number
  rating: string
}

type FormationKind =
  | 'classic-pitch'
  | 'tactical-board'
  | 'zone-grid'
  | 'half-space'
  | 'radar-rings'
  | 'stadium-perspective'
  | 'compact-pitch'

type IdentityLayerKind =
  | 'top-ribbon'
  | 'crest-tab'
  | 'side-rail'
  | 'corner-motif'
  | 'tournament-plate'
  | 'pattern-band'

type FormationRow = {
  id: string
  title: string
  source: string
  fit: string
  kind: FormationKind
}

type IdentityLayer = {
  id: string
  title: string
  short: string
  summary: string
  kind: IdentityLayerKind
}

type DualBoardKind =
  | 'mirror-lineups'
  | 'phase-split'
  | 'matchup-channels'
  | 'overload-map'
  | 'compact-dual'
  | 'camera-dual'

type DualBoard = {
  id: string
  title: string
  source: string
  fit: string
  kind: DualBoardKind
}

type DualPlayer = Player & {
  team: 'home' | 'away'
}

const players: Player[] = [
  { no: 1, x: 50, y: 88, rating: '7.1' },
  { no: 3, x: 12, y: 72, rating: '6.8' },
  { no: 4, x: 33, y: 73, rating: '7.0' },
  { no: 5, x: 67, y: 73, rating: '6.9' },
  { no: 2, x: 88, y: 72, rating: '6.7' },
  { no: 8, x: 22, y: 49, rating: '7.4' },
  { no: 6, x: 50, y: 57, rating: '7.2' },
  { no: 10, x: 78, y: 49, rating: '7.6' },
  { no: 11, x: 16, y: 25, rating: '6.5' },
  { no: 9, x: 50, y: 16, rating: '8.2' },
  { no: 7, x: 84, y: 25, rating: '7.1' },
]

const formationRows: FormationRow[] = [
  {
    id: 'F1',
    title: 'Classic Pitch',
    source: '전통 축구장 라인업',
    fit: '기본 피치 후보',
    kind: 'classic-pitch',
  },
  {
    id: 'F2',
    title: 'Tactical Board',
    source: '분석/전술판',
    fit: 'UCL/전술 리뷰',
    kind: 'tactical-board',
  },
  {
    id: 'F3',
    title: 'Zone Grid',
    source: 'thirds/grid 피치',
    fit: '전술 피드백',
    kind: 'zone-grid',
  },
  {
    id: 'F4',
    title: 'Half-Space Map',
    source: '현대 축구 분석',
    fit: 'EPL/UCL 분석형',
    kind: 'half-space',
  },
  {
    id: 'F8',
    title: 'Radar Rings',
    source: '포지션 존 그래픽',
    fit: '월드컵 보조 후보',
    kind: 'radar-rings',
  },
  {
    id: 'F9',
    title: 'Stadium Perspective',
    source: '방송 카메라 전술뷰',
    fit: '중계화면 직접 노출',
    kind: 'stadium-perspective',
  },
  {
    id: 'F10',
    title: 'Compact Pitch',
    source: '좁은 좌측 패널',
    fit: '실사용 우선 후보',
    kind: 'compact-pitch',
  },
]

const identityLayers: IdentityLayer[] = [
  {
    id: 'L1',
    title: 'Top Ribbon',
    short: 'RIBBON',
    summary: '상단 얇은 대회/리그 리본',
    kind: 'top-ribbon',
  },
  {
    id: 'L2',
    title: 'Crest Tab',
    short: 'CREST',
    summary: '팀/대회 배지 탭',
    kind: 'crest-tab',
  },
  {
    id: 'L3',
    title: 'Side Rail',
    short: 'RAIL',
    summary: '좌우 세로 컬러 레일',
    kind: 'side-rail',
  },
  {
    id: 'L4',
    title: 'Corner Motif',
    short: 'CORNER',
    summary: '코너 장식/컵대회 모티프',
    kind: 'corner-motif',
  },
  {
    id: 'L5',
    title: 'Tournament Plate',
    short: 'PLATE',
    summary: '상단 대회 플레이트',
    kind: 'tournament-plate',
  },
  {
    id: 'L6',
    title: 'Pattern Band',
    short: 'BAND',
    summary: '국기/별/컵 패턴 띠',
    kind: 'pattern-band',
  },
]

const dualBoards: DualBoard[] = [
  {
    id: 'D1',
    title: 'Mirror Lineups',
    source: '양 팀 기본 배치 비교',
    fit: '킥오프 전 프리뷰',
    kind: 'mirror-lineups',
  },
  {
    id: 'D2',
    title: 'Phase Split Board',
    source: '공격/수비 국면 분리',
    fit: '전술 설명용',
    kind: 'phase-split',
  },
  {
    id: 'D3',
    title: 'Matchup Channels',
    source: '직접 매치업 채널',
    fit: '주요 대결 구도',
    kind: 'matchup-channels',
  },
  {
    id: 'D4',
    title: 'Overload Map',
    source: '압박/과부하 영역',
    fit: '분석 방송',
    kind: 'overload-map',
  },
  {
    id: 'D5',
    title: 'Compact Dual Board',
    source: '좌측 패널 압축형',
    fit: '실제 오버레이 후보',
    kind: 'compact-dual',
  },
  {
    id: 'D6',
    title: 'Camera Dual View',
    source: '중계 카메라 전술뷰',
    fit: '중계화면 직접 노출',
    kind: 'camera-dual',
  },
]

const dualPlayers: DualPlayer[] = [
  { team: 'home', no: 1, x: 50, y: 90, rating: '7.1' },
  { team: 'home', no: 3, x: 16, y: 75, rating: '6.8' },
  { team: 'home', no: 4, x: 38, y: 76, rating: '7.0' },
  { team: 'home', no: 5, x: 62, y: 76, rating: '6.9' },
  { team: 'home', no: 2, x: 84, y: 75, rating: '6.7' },
  { team: 'home', no: 6, x: 42, y: 62, rating: '7.2' },
  { team: 'home', no: 8, x: 58, y: 62, rating: '7.4' },
  { team: 'home', no: 11, x: 23, y: 47, rating: '6.5' },
  { team: 'home', no: 10, x: 50, y: 45, rating: '7.6' },
  { team: 'home', no: 7, x: 77, y: 47, rating: '7.1' },
  { team: 'home', no: 9, x: 50, y: 32, rating: '8.2' },
  { team: 'away', no: 1, x: 50, y: 10, rating: '7.0' },
  { team: 'away', no: 6, x: 16, y: 25, rating: '6.8' },
  { team: 'away', no: 3, x: 38, y: 24, rating: '7.2' },
  { team: 'away', no: 4, x: 62, y: 24, rating: '7.0' },
  { team: 'away', no: 2, x: 84, y: 25, rating: '6.9' },
  { team: 'away', no: 5, x: 24, y: 40, rating: '6.7' },
  { team: 'away', no: 8, x: 50, y: 39, rating: '7.3' },
  { team: 'away', no: 10, x: 76, y: 40, rating: '7.5' },
  { team: 'away', no: 11, x: 23, y: 55, rating: '7.2' },
  { team: 'away', no: 9, x: 50, y: 58, rating: '7.8' },
  { team: 'away', no: 7, x: 77, y: 55, rating: '7.1' },
]

function formationTag(kind: FormationKind) {
  if (kind === 'tactical-board') return 'TACTICAL'
  if (kind === 'zone-grid') return 'ZONES'
  if (kind === 'half-space') return 'HALF-SPACES'
  if (kind === 'radar-rings') return 'RADAR'
  if (kind === 'stadium-perspective') return 'CAM VIEW'
  if (kind === 'compact-pitch') return 'COMPACT'
  return '4-2-3-1'
}
</script>

<template>
  <main class="formation-lab-page" data-testid="formation-lab-page">
    <header class="lab-header">
      <div>
        <span>Broadcast Formation Lab</span>
        <h1>포메이션 아이덴티티 매트릭스</h1>
      </div>
      <p>선택된 7개 포메이션 구조를 고정하고, 리본/크레스트/레일/코너/플레이트/패턴 레이어를 얹어 비교합니다.</p>
    </header>

    <section class="layer-guide" data-testid="identity-layer-guide">
      <article v-for="layer in identityLayers" :key="layer.id">
        <strong>{{ layer.id }}. {{ layer.title }}</strong>
        <span>{{ layer.summary }}</span>
      </article>
    </section>

    <section class="identity-matrix" data-testid="formation-identity-matrix">
      <article
        v-for="row in formationRows"
        :key="row.id"
        class="matrix-row"
        :data-formation="row.kind"
        data-testid="formation-matrix-row"
      >
        <aside class="row-meta">
          <b>{{ row.id }}</b>
          <strong>{{ row.title }}</strong>
          <span>{{ row.source }}</span>
          <i>{{ row.fit }}</i>
        </aside>

        <div class="row-cells">
          <section
            v-for="layer in identityLayers"
            :key="`${row.id}-${layer.id}`"
            :class="[
              'matrix-cell',
              row.id === 'F8' && layer.kind === 'pattern-band' ? 'matrix-cell--selected' : '',
            ]"
            :data-layer="layer.kind"
            :data-selected="row.id === 'F8' && layer.kind === 'pattern-band' ? 'true' : 'false'"
            data-testid="formation-matrix-cell"
          >
            <header class="cell-label">
              <b>{{ layer.short }}</b>
              <span>{{ layer.title }}</span>
              <i v-if="row.id === 'F8' && layer.kind === 'pattern-band'">채택</i>
            </header>

            <section
              :class="[
                'formation-prototype',
                `formation-prototype--${row.kind}`,
                `identity-layer--${layer.kind}`,
              ]"
            >
              <div v-if="layer.kind === 'top-ribbon'" class="identity-top-ribbon">
                <span>PREMIER LEAGUE</span>
                <b>KOR</b>
              </div>

              <div v-if="layer.kind === 'tournament-plate'" class="identity-plate">
                <span>UEFA</span>
                <b>FORMATION</b>
                <i>MD 06</i>
              </div>

              <div v-if="layer.kind === 'pattern-band'" class="identity-pattern-band">
                <span></span><span></span><span></span><span></span><span></span>
              </div>

              <header class="pitch-header">
                <b>KOR</b>
                <span>{{ formationTag(row.kind) }}</span>
              </header>

              <div class="pitch-shell">
                <span v-if="layer.kind === 'side-rail'" class="side-rail side-rail-left">EPL</span>
                <span v-if="layer.kind === 'side-rail'" class="side-rail side-rail-right">UCL</span>
                <span v-if="layer.kind === 'crest-tab'" class="crest-tab crest-tab-left">PL</span>
                <span v-if="layer.kind === 'crest-tab'" class="crest-tab crest-tab-right">KOR</span>
                <span v-if="layer.kind === 'corner-motif'" class="corner-motif corner-motif-a"></span>
                <span v-if="layer.kind === 'corner-motif'" class="corner-motif corner-motif-b"></span>
                <span v-if="layer.kind === 'corner-motif'" class="corner-motif corner-motif-c"></span>
                <span v-if="layer.kind === 'corner-motif'" class="corner-motif corner-motif-d"></span>

                <div class="mini-pitch">
                  <div class="pitch-zones" aria-hidden="true">
                    <span></span><span></span><span></span><span></span><span></span>
                  </div>
                  <span class="half-line"></span>
                  <span class="center-circle"></span>
                  <span class="box box-top"></span>
                  <span class="box box-bottom"></span>
                  <span class="goal-area goal-area-top"></span>
                  <span class="goal-area goal-area-bottom"></span>
                  <span
                    v-for="player in players"
                    :key="`${row.kind}-${layer.kind}-${player.no}`"
                    class="player-dot"
                    :style="{ left: `${player.x}%`, top: `${player.y}%` }"
                  >
                    <b>{{ player.no }}</b>
                    <i>{{ player.rating }}</i>
                  </span>
                </div>
              </div>
            </section>
          </section>
        </div>
      </article>
    </section>

    <section class="dual-board-section" data-testid="dual-board-section">
      <header class="section-heading">
        <div>
          <span>Two Teams / One Tactical Board</span>
          <h2>양 팀 단일 전술판 후보 6종</h2>
        </div>
        <p>두 팀을 하나의 피치에 올려 킥오프 전 매치업, 압박 구도, 공간 과부하, 중계화면 분석 그래픽을 비교합니다.</p>
      </header>

      <div class="dual-board-list">
        <article
          v-for="board in dualBoards"
          :key="board.id"
          class="dual-board-tile"
          :data-board="board.kind"
          data-testid="dual-board-tile"
        >
          <aside class="dual-meta">
            <b>{{ board.id }}</b>
            <strong>{{ board.title }}</strong>
            <span>{{ board.source }}</span>
            <i>{{ board.fit }}</i>
          </aside>

          <section :class="['dual-board', `dual-board--${board.kind}`]">
            <header class="dual-header">
              <span>대한민국 4-2-3-1</span>
              <b>ONE BOARD</b>
              <span>브라질 4-3-3</span>
            </header>

            <div class="dual-pitch">
              <div class="dual-zones" aria-hidden="true">
                <span></span><span></span><span></span><span></span><span></span>
              </div>
              <span class="dual-half-line"></span>
              <span class="dual-center-circle"></span>
              <span class="dual-box dual-box-top"></span>
              <span class="dual-box dual-box-bottom"></span>

              <template v-if="board.kind === 'phase-split'">
                <span class="phase-band phase-band-home">HOME ATTACK</span>
                <span class="phase-band phase-band-away">AWAY BLOCK</span>
              </template>

              <template v-if="board.kind === 'matchup-channels'">
                <span class="matchup-line matchup-line-left"></span>
                <span class="matchup-line matchup-line-center"></span>
                <span class="matchup-line matchup-line-right"></span>
              </template>

              <template v-if="board.kind === 'overload-map'">
                <span class="overload-zone overload-zone-left">2v1</span>
                <span class="overload-zone overload-zone-center">PRESS</span>
                <span class="overload-zone overload-zone-right">SPACE</span>
              </template>

              <span
                v-for="player in dualPlayers"
                :key="`${board.kind}-${player.team}-${player.no}`"
                :class="['dual-player', `dual-player--${player.team}`]"
                :style="{ left: `${player.x}%`, top: `${player.y}%` }"
              >
                <b>{{ player.no }}</b>
              </span>
            </div>
          </section>
        </article>
      </div>
    </section>
  </main>
</template>

<style scoped>
*,
*::before,
*::after {
  box-sizing: border-box;
}

.formation-lab-page {
  width: 100vw;
  height: 100vh;
  overflow-y: auto;
  overflow-x: hidden;
  background: #11151F;
  color: #F7F4EC;
  font-family:
    'Avenir Next Condensed',
    'DIN Condensed',
    'Pretendard',
    system-ui,
    sans-serif;
  letter-spacing: 0;
}

.lab-header {
  position: sticky;
  top: 0;
  z-index: 20;
  min-height: 6.5rem;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 2%;
  padding: 1.1% 1.25% 0.9%;
  background: #191F2D;
  border-bottom: 0.16rem solid #D7B85D;
}

.lab-header span {
  display: block;
  color: #D7B85D;
  font-size: 0.86rem;
  font-weight: 900;
}

.lab-header h1,
.lab-header p {
  margin: 0;
}

.lab-header h1 {
  font-size: 2.05rem;
  line-height: 1;
}

.lab-header p {
  max-width: 48%;
  color: #D8DEEC;
  font-size: 1rem;
  font-weight: 800;
  line-height: 1.35;
  text-align: right;
}

.layer-guide {
  display: flex;
  gap: 0.55rem;
  padding: 0.72rem;
  background: #151B28;
  border-bottom: 0.08rem solid #3B465D;
}

.layer-guide article {
  flex: 1 1 0;
  min-width: 0;
  padding: 0.64rem 0.72rem;
  background: #202838;
  border: 0.08rem solid #3B465D;
  border-radius: 0.45rem;
}

.layer-guide strong,
.layer-guide span {
  display: block;
}

.layer-guide strong {
  color: #F4D27A;
  font-size: 0.88rem;
  line-height: 1.05;
}

.layer-guide span {
  margin-top: 0.24rem;
  color: #C7D0E2;
  font-size: 0.72rem;
  font-weight: 800;
  line-height: 1.2;
}

.identity-matrix {
  display: flex;
  flex-direction: column;
  gap: 0.72rem;
  padding: 0.72rem;
}

.matrix-row {
  min-height: 17.8rem;
  display: flex;
  gap: 0.62rem;
  padding: 0.62rem;
  background: #202838;
  border: 0.1rem solid #3B465D;
  border-radius: 0.55rem;
  box-shadow: 0.22rem 0.22rem 0 #070910;
}

.row-meta {
  flex: 0 0 11.2rem;
  display: flex;
  flex-direction: column;
  justify-content: center;
  gap: 0.4rem;
  padding: 0.74rem;
  background: #121826;
  border: 0.08rem solid #3B465D;
  border-radius: 0.4rem;
}

.row-meta b {
  width: 2.15rem;
  height: 2.15rem;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  background: #D7B85D;
  border-radius: 50%;
  color: #0B1020;
  font-size: 0.95rem;
}

.row-meta strong,
.row-meta span,
.row-meta i {
  display: block;
}

.row-meta strong {
  color: #FFFFFF;
  font-size: 1.12rem;
  line-height: 1.05;
}

.row-meta span {
  color: #B8C2D6;
  font-size: 0.75rem;
  font-weight: 800;
}

.row-meta i {
  color: #F4D27A;
  font-size: 0.78rem;
  font-style: normal;
  font-weight: 900;
  line-height: 1.2;
}

.row-cells {
  flex: 1 1 0;
  min-width: 0;
  display: flex;
  gap: 0.52rem;
}

.matrix-cell {
  flex: 1 1 0;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 0.34rem;
}

.matrix-cell--selected {
  padding: 0.18rem;
  background: #D4AF37;
  box-shadow: 0.18rem 0.18rem 0 #000000;
}

.cell-label {
  flex: 0 0 2rem;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.35rem;
  padding: 0 0.45rem;
  background: #0C1220;
  border: 0.08rem solid #3B465D;
  border-radius: 0.32rem;
}

.cell-label b {
  color: #F4D27A;
  font-size: 0.74rem;
}

.cell-label span {
  min-width: 0;
  color: #E8EDF7;
  font-size: 0.7rem;
  font-weight: 900;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.cell-label i {
  flex: 0 0 auto;
  padding: 0.12rem 0.28rem;
  background: #D4AF37;
  border-radius: 0.22rem;
  color: #0B1020;
  font-size: 0.58rem;
  font-style: normal;
  font-weight: 900;
}

.matrix-cell--selected .cell-label {
  border-color: #F5F1E8;
}

.formation-prototype {
  flex: 1 1 0;
  min-height: 0;
  position: relative;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  color: #FFFFFF;
  background: #07123D;
  border: 0.13rem solid #F4D27A;
  box-shadow: 0.18rem 0.18rem 0 #050609;
  font-weight: 900;
}

.pitch-header {
  flex: 0 0 12.5%;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 0.42rem;
  background: #010B28;
  border-bottom: 0.08rem solid #FFFFFF;
  font-size: 0.72rem;
}

.pitch-shell {
  position: relative;
  flex: 1 1 0;
  min-height: 0;
  display: flex;
  padding: 0.42rem;
}

.mini-pitch {
  position: relative;
  flex: 1 1 0;
  min-width: 0;
  min-height: 0;
  overflow: hidden;
  background: #3158A8;
  border: 0.08rem solid #DDE7FF;
}

.formation-prototype--classic-pitch .mini-pitch {
  background: repeating-linear-gradient(0deg, #3158A8 0 16.6%, #284B93 16.6% 33.2%);
}

.formation-prototype--tactical-board {
  background: #071542;
  border-color: #F1F4FF;
}

.formation-prototype--tactical-board .mini-pitch {
  background: #101C3D;
  border-color: #8CB2FF;
}

.formation-prototype--zone-grid {
  background: #132D5E;
  border-color: #F7F1E3;
}

.formation-prototype--zone-grid .mini-pitch {
  background: #2E4E86;
}

.formation-prototype--half-space {
  background: #3D195B;
  border-color: #04F5FF;
}

.formation-prototype--half-space .mini-pitch {
  background: #32105A;
  border-color: #04F5FF;
}

.formation-prototype--radar-rings {
  background: #050505;
  border-color: #D4AF37;
}

.formation-prototype--radar-rings .mini-pitch {
  background: repeating-radial-gradient(circle at 50% 50%, #111111 0 14%, #202020 14% 28%);
  border-color: #D4AF37;
}

.formation-prototype--stadium-perspective {
  background: #050505;
  border-color: #F5F1E8;
}

.formation-prototype--stadium-perspective .mini-pitch {
  width: 88%;
  height: 70%;
  flex: 0 0 70%;
  margin: auto;
  background: #1E3067;
  border-color: #F5F1E8;
  transform: perspective(18rem) rotateX(15deg);
  transform-origin: 50% 72%;
}

.formation-prototype--compact-pitch {
  background: #010056;
  border-color: #8CB2FF;
}

.formation-prototype--compact-pitch .mini-pitch {
  margin: 0 0.85rem;
  background: #203B88;
  border-color: #F1F4FF;
}

.identity-layer--top-ribbon {
  border-color: #04F5FF;
}

.identity-top-ribbon {
  flex: 0 0 8.5%;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 0.44rem;
  background: #3D195B;
  border-bottom: 0.08rem solid #04F5FF;
  color: #FFFFFF;
  font-size: 0.58rem;
}

.identity-top-ribbon b {
  color: #04F5FF;
}

.identity-layer--crest-tab {
  border-color: #315DFF;
}

.crest-tab {
  position: absolute;
  top: 0.28rem;
  z-index: 8;
  width: 1.74rem;
  height: 1.74rem;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  background: #F1F4FF;
  border: 0.12rem solid #315DFF;
  border-radius: 50%;
  color: #010056;
  font-size: 0.55rem;
}

.crest-tab-left {
  left: 0.28rem;
}

.crest-tab-right {
  right: 0.28rem;
}

.identity-layer--side-rail {
  border-color: #E90052;
}

.side-rail {
  position: absolute;
  top: 0.42rem;
  bottom: 0.42rem;
  z-index: 7;
  width: 1.08rem;
  display: flex;
  align-items: center;
  justify-content: center;
  background: #E90052;
  color: #FFFFFF;
  font-size: 0.54rem;
  writing-mode: vertical-rl;
}

.side-rail-left {
  left: 0.42rem;
}

.side-rail-right {
  right: 0.42rem;
  background: #04F5FF;
  color: #06111F;
}

.identity-layer--corner-motif {
  border-color: #D4AF37;
}

.corner-motif {
  position: absolute;
  z-index: 8;
  width: 1.06rem;
  height: 1.06rem;
  background: #D4AF37;
  border: 0.12rem solid #F7F1E3;
}

.corner-motif-a {
  top: 0.38rem;
  left: 0.38rem;
  border-radius: 0 0 0.5rem 0;
}

.corner-motif-b {
  top: 0.38rem;
  right: 0.38rem;
  border-radius: 0 0 0 0.5rem;
}

.corner-motif-c {
  bottom: 0.38rem;
  left: 0.38rem;
  border-radius: 0 0.5rem 0 0;
}

.corner-motif-d {
  right: 0.38rem;
  bottom: 0.38rem;
  border-radius: 0.5rem 0 0 0;
}

.identity-layer--tournament-plate {
  border-color: #D4AF37;
}

.identity-plate {
  flex: 0 0 17%;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 0.46rem;
  background: #011E41;
  border-bottom: 0.12rem solid #D4AF37;
  color: #FFFFFF;
  font-size: 0.56rem;
}

.identity-plate span,
.identity-plate i {
  color: #D4AF37;
  font-style: normal;
}

.identity-layer--pattern-band {
  border-color: #C8102E;
}

.identity-pattern-band {
  flex: 0 0 7.5%;
  display: flex;
}

.identity-pattern-band span {
  flex: 1 1 0;
}

.identity-pattern-band span:nth-child(1) {
  background: #C8102E;
}

.identity-pattern-band span:nth-child(2) {
  background: #D4AF37;
}

.identity-pattern-band span:nth-child(3) {
  background: #000000;
}

.identity-pattern-band span:nth-child(4) {
  background: #F5F1E8;
}

.identity-pattern-band span:nth-child(5) {
  background: #003478;
}

.pitch-zones {
  position: absolute;
  inset: 0;
  display: none;
}

.pitch-zones span {
  flex: 1;
  border-right: 0.06rem solid #FFFFFF;
}

.pitch-zones span:last-child {
  border-right: 0;
}

.formation-prototype--zone-grid .pitch-zones,
.formation-prototype--half-space .pitch-zones {
  display: flex;
}

.formation-prototype--zone-grid .pitch-zones span:nth-child(even) {
  background: #253F70;
}

.formation-prototype--half-space .pitch-zones span:nth-child(2),
.formation-prototype--half-space .pitch-zones span:nth-child(4) {
  background: #E90052;
}

.formation-prototype--half-space .pitch-zones span:nth-child(3) {
  background: #12051F;
}

.half-line,
.center-circle,
.box,
.goal-area {
  position: absolute;
  display: block;
}

.half-line {
  left: 0;
  right: 0;
  top: 50%;
  border-top: 0.08rem solid #DDE7FF;
}

.center-circle {
  left: 50%;
  top: 50%;
  width: 25%;
  aspect-ratio: 1;
  border: 0.08rem solid #DDE7FF;
  border-radius: 50%;
  transform: translate(-50%, -50%);
}

.box {
  left: 25%;
  width: 50%;
  height: 17%;
  border: 0.08rem solid #DDE7FF;
}

.box-top {
  top: -0.08rem;
}

.box-bottom {
  bottom: -0.08rem;
}

.goal-area {
  left: 38%;
  width: 24%;
  height: 7%;
  border: 0.08rem solid #DDE7FF;
}

.goal-area-top {
  top: -0.08rem;
}

.goal-area-bottom {
  bottom: -0.08rem;
}

.player-dot {
  position: absolute;
  z-index: 9;
  display: flex;
  align-items: center;
  justify-content: center;
  transform: translate(-50%, -50%);
}

.player-dot b {
  width: 1.44rem;
  aspect-ratio: 1;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  background: #C8102E;
  border: 0.08rem solid #FFFFFF;
  border-radius: 50%;
  color: #FFFFFF;
  font-size: 0.66rem;
}

.player-dot i {
  position: absolute;
  left: -0.16rem;
  top: 0.96rem;
  padding: 0.05rem 0.14rem;
  background: #010B28;
  border-radius: 0.18rem;
  color: #FFFFFF;
  font-size: 0.42rem;
  font-style: normal;
}

.formation-prototype--tactical-board .player-dot b,
.formation-prototype--zone-grid .player-dot b,
.formation-prototype--compact-pitch .player-dot b {
  background: #315DFF;
}

.formation-prototype--half-space .player-dot b {
  background: #E90052;
}

.formation-prototype--radar-rings .player-dot b {
  background: #D4AF37;
  color: #000000;
}

.formation-prototype--stadium-perspective .player-dot b {
  background: #C8102E;
}

.dual-board-section {
  padding: 0.72rem;
  border-top: 0.16rem solid #D7B85D;
  background: #151B28;
}

.section-heading {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 2%;
  margin-bottom: 0.72rem;
  padding: 0.84rem 1rem;
  background: #202838;
  border: 0.1rem solid #3B465D;
  border-radius: 0.55rem;
}

.section-heading span {
  color: #D7B85D;
  font-size: 0.84rem;
  font-weight: 900;
}

.section-heading h2,
.section-heading p {
  margin: 0;
}

.section-heading h2 {
  font-size: 1.74rem;
  line-height: 1;
}

.section-heading p {
  max-width: 50%;
  color: #D8DEEC;
  font-size: 0.9rem;
  font-weight: 800;
  line-height: 1.35;
  text-align: right;
}

.dual-board-list {
  display: flex;
  flex-direction: column;
  gap: 0.72rem;
}

.dual-board-tile {
  min-height: 22rem;
  display: flex;
  gap: 0.72rem;
  padding: 0.72rem;
  background: #202838;
  border: 0.1rem solid #3B465D;
  border-radius: 0.55rem;
  box-shadow: 0.22rem 0.22rem 0 #070910;
}

.dual-meta {
  flex: 0 0 13rem;
  display: flex;
  flex-direction: column;
  justify-content: center;
  gap: 0.48rem;
  padding: 0.82rem;
  background: #121826;
  border: 0.08rem solid #3B465D;
  border-radius: 0.4rem;
}

.dual-meta b {
  width: 2.2rem;
  height: 2.2rem;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  background: #D7B85D;
  border-radius: 50%;
  color: #0B1020;
}

.dual-meta strong,
.dual-meta span,
.dual-meta i {
  display: block;
}

.dual-meta strong {
  color: #FFFFFF;
  font-size: 1.18rem;
  line-height: 1.05;
}

.dual-meta span {
  color: #B8C2D6;
  font-size: 0.8rem;
  font-weight: 800;
}

.dual-meta i {
  color: #F4D27A;
  font-size: 0.82rem;
  font-style: normal;
  font-weight: 900;
}

.dual-board {
  flex: 1 1 0;
  min-width: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  background: #07123D;
  border: 0.14rem solid #F4D27A;
  box-shadow: 0.2rem 0.2rem 0 #050609;
}

.dual-header {
  flex: 0 0 3.1rem;
  display: flex;
  align-items: center;
  justify-content: space-between;
  background: #010B28;
  border-bottom: 0.1rem solid #FFFFFF;
  color: #FFFFFF;
  font-weight: 900;
}

.dual-header span {
  flex: 1 1 0;
  padding: 0 1rem;
  font-size: 1rem;
}

.dual-header span:first-child {
  color: #F4D27A;
}

.dual-header span:last-child {
  color: #8CB2FF;
  text-align: right;
}

.dual-header b {
  flex: 0 0 10rem;
  height: 100%;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  background: #F1F4FF;
  color: #010B28;
  font-size: 0.9rem;
}

.dual-pitch {
  position: relative;
  flex: 1 1 0;
  margin: 0.72rem;
  overflow: hidden;
  background: repeating-linear-gradient(0deg, #3158A8 0 12.5%, #284B93 12.5% 25%);
  border: 0.12rem solid #DDE7FF;
}

.dual-board--phase-split .dual-pitch {
  background: linear-gradient(0deg, #203B88 0 50%, #111C3D 50% 100%);
}

.dual-board--matchup-channels .dual-pitch,
.dual-board--overload-map .dual-pitch {
  background: #243F78;
}

.dual-board--compact-dual .dual-pitch {
  margin: 0.72rem 5%;
  background: #203B88;
}

.dual-board--camera-dual .dual-pitch {
  width: 82%;
  height: 72%;
  flex: 0 0 72%;
  margin: auto;
  background: #1E3067;
  transform: perspective(28rem) rotateX(14deg);
  transform-origin: 50% 72%;
}

.dual-zones {
  position: absolute;
  inset: 0;
  display: flex;
}

.dual-zones span {
  flex: 1 1 0;
  border-right: 0.08rem solid #DDE7FF;
}

.dual-zones span:last-child {
  border-right: 0;
}

.dual-half-line,
.dual-center-circle,
.dual-box {
  position: absolute;
  display: block;
}

.dual-half-line {
  left: 0;
  right: 0;
  top: 50%;
  border-top: 0.1rem solid #DDE7FF;
}

.dual-center-circle {
  left: 50%;
  top: 50%;
  width: 16%;
  aspect-ratio: 1;
  border: 0.1rem solid #DDE7FF;
  border-radius: 50%;
  transform: translate(-50%, -50%);
}

.dual-box {
  left: 34%;
  width: 32%;
  height: 16%;
  border: 0.1rem solid #DDE7FF;
}

.dual-box-top {
  top: -0.1rem;
}

.dual-box-bottom {
  bottom: -0.1rem;
}

.phase-band {
  position: absolute;
  left: 4%;
  right: 4%;
  z-index: 3;
  height: 2rem;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #FFFFFF;
  font-size: 0.85rem;
  font-weight: 900;
}

.phase-band-home {
  bottom: 12%;
  background: #C8102E;
}

.phase-band-away {
  top: 12%;
  background: #315DFF;
}

.matchup-line {
  position: absolute;
  top: 10%;
  bottom: 10%;
  z-index: 3;
  width: 0.16rem;
  background: #F4D27A;
}

.matchup-line-left {
  left: 25%;
}

.matchup-line-center {
  left: 50%;
}

.matchup-line-right {
  left: 75%;
}

.overload-zone {
  position: absolute;
  z-index: 3;
  display: flex;
  align-items: center;
  justify-content: center;
  background: #D4AF37;
  border: 0.12rem solid #F7F1E3;
  color: #07123D;
  font-size: 0.82rem;
  font-weight: 900;
}

.overload-zone-left {
  left: 8%;
  top: 42%;
  width: 20%;
  height: 18%;
}

.overload-zone-center {
  left: 39%;
  top: 33%;
  width: 22%;
  height: 18%;
  background: #C8102E;
  color: #FFFFFF;
}

.overload-zone-right {
  right: 8%;
  top: 43%;
  width: 20%;
  height: 18%;
  background: #04F5FF;
  color: #06111F;
}

.dual-player {
  position: absolute;
  z-index: 10;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  transform: translate(-50%, -50%);
}

.dual-player b {
  width: 2rem;
  aspect-ratio: 1;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border: 0.1rem solid #FFFFFF;
  border-radius: 50%;
  color: #FFFFFF;
  font-size: 0.86rem;
}

.dual-player--home b {
  background: #C8102E;
}

.dual-player--away b {
  background: #315DFF;
}
</style>
