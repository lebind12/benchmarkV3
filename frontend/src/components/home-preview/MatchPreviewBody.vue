<script setup lang="ts">
/**
 * 저장된 프리뷰 **본문** (확정 목업 MatchPreviewBody의 실제 데이터 버전).
 *
 * 목업은 `mock/match-city-fulham.json`을 정적으로 import했다. 이 컴포넌트는 그 JSON을
 * 가져오지 않고, `preview` prop(저장 결과를 옮긴 표시 모델)만 읽는다. 배치·리듬·패널
 * 모양은 목업 그대로다.
 *
 * 지키는 것:
 *
 * - `**이름**` 강조는 `InlineEmphasis`(텍스트/`strong` 노드)로만 그린다. `v-html` 없음.
 * - 본문에 내부 진단·면책 문구를 섞지 않는다. 진단은 이 본문 **아래**의 접힌 영역 몫이다.
 * - 구조화 값이 없으면 저장된 섹션 `body`를 그대로 그린다(숨기지 않는다).
 * - 없는 섹션은 아예 그리지 않는다. 빈 카드·"데이터 없음" 배너로 채우지 않는다.
 * - 배당은 저장된 값만 세 칸에 넣는다. 없는 칸은 `—`로 비워 두고 합성값을 넣지 않는다.
 * - 사진·로고는 **서버가 준 URL이 있을 때만** `<img>`다. 없으면 이름을 그대로 두고 사진만
 *   생략한다(추측 URL 금지). 내부 선수 ID(533)는 API-Football 사진 ID(1100)가 아니므로
 *   내부 ID로 주소를 조립하지 않는다. 이 컴포넌트는 원본 **홈 추천 API 계약**
 *   (`/api/v1/home/...`)을 읽지 않고, 프리뷰 저장 계약(`previewView`)만 읽는다.
 * - 로드는 실패해도 흐름을 막지 않는다. 깨진 이미지는 `@error`로 사진 자리만 비운다.
 */
import { computed, ref } from 'vue'
import InlineEmphasis from '@/features/match-preview/InlineEmphasis.vue'
import {
  bodyBlocks,
  resolveSides,
  teamGroups,
  type MatchPreviewView,
  type PlacedGroup,
} from '@/lib/api/previewView'
import '@/styles/match-preview/tokens.css'
import '@/styles/match-preview/body.css'

const props = withDefaults(
  defineProps<{
    preview: MatchPreviewView
    /** 'embedded'는 관리 탭 안쪽, 'standalone'은 머리글까지 그린다. */
    variant?: 'standalone' | 'embedded'
  }>(),
  { variant: 'embedded' },
)

const view = computed(() => props.preview)

const kickoff = computed<{ date: string; time: string } | null>(() => {
  const raw = view.value.fixture.kickoff_at
  if (!raw) return null
  const at = new Date(raw)
  if (Number.isNaN(at.getTime())) return null
  return {
    date: new Intl.DateTimeFormat('ko-KR', {
      timeZone: 'Asia/Seoul',
      month: 'long',
      day: 'numeric',
      weekday: 'long',
    }).format(at),
    time: new Intl.DateTimeFormat('ko-KR', {
      timeZone: 'Asia/Seoul',
      hour: '2-digit',
      minute: '2-digit',
      hour12: false,
    }).format(at),
  }
})

/**
 * 팀별 좌우 묶음.
 *
 * 좌우는 **확인된 팀 ID → 저장된 팀 이름** 순서로 정하고, 확인되지 않은 묶음만 남은 자리에
 * 들어간다. 배열 순서로 홈/원정을 만들지 않는다(`resolveSides`).
 */
function sides<T extends { team: string | null }>(rows: T[]): PlacedGroup<T>[] {
  return resolveSides(teamGroups(rows, view.value))
}

const playerGroups = computed(() => sides(view.value.players))
const injuryGroups = computed(() => sides(view.value.injuries))

/**
 * 팀 로고 주소(서버가 준 값). 홈/원정이 **확인된** 묶음에만 그 열의 로고를 붙인다.
 * 확인되지 않은 묶음에 다른 팀 로고를 붙이면 없는 사실을 만든다.
 */
const badgeOf = (column: 0 | 1, side: 0 | 1 | null): string | null => {
  if (side === null) return null
  return column === 0 ? view.value.fixture.home.badge_url : view.value.fixture.away.badge_url
}

/**
 * 팀 로고의 깨짐 여부를 **섹션별로** 구분하는 키.
 *
 * 주목 선수와 부상·결장은 같은 팀 로고를 쓰지만 서로 다른 섹션이다. 키를 열 번호만으로
 * 두면 한 섹션에서 로고가 깨졌을 때 다른 섹션의 로고까지 함께 사라진다(실측: 한 번의
 * `error`로 두 섹션 로고가 모두 사라졌다). 섹션 이름을 붙여 서로 영향을 주지 않게 한다.
 */
const teamPhotoKey = (section: 'players' | 'injuries', column: 0 | 1): string =>
  `team-${section}-${column}`

const forecast = computed(() => view.value.forecast)
const hasForecast = computed(
  () =>
    forecast.value.forecastLines.length > 0 ||
    forecast.value.reasoning.length > 0 ||
    forecast.value.score !== null,
)

/** 카드가 그리는 섹션. 저장 본문이 남아 있으면 카드 아래에 그대로 잇는다. */
const CARD_SECTIONS = new Set([
  'section_players',
  'section_availability',
  'section_outlook',
  'section_odds',
  'section_ai_forecast',
])

/**
 * 카드로 그리지 않는 섹션의 저장 본문. 가진 내용을 숨기지 않는다.
 * 모르는 섹션(서버가 새로 추가한 것)도 여기서 그대로 보여준다.
 */
const textSections = computed(() => {
  const out: { id: string; title: string; blocks: ReturnType<typeof bodyBlocks> }[] = []
  for (const [id, section] of Object.entries(view.value.sections)) {
    if (CARD_SECTIONS.has(id)) continue
    if (!section.body.trim()) continue
    out.push({ id, title: section.title, blocks: bodyBlocks(section.body) })
  }
  return out
})

/**
 * 카드가 **아예 그리지 못한** 카드 섹션의 저장 본문.
 *
 * 규칙은 하나다. 카드를 그린 섹션은 그 카드 **안에서** 저장된 의미 있는 문장을 모두
 * 보여주므로(주목 선수의 도입 문장은 카드 위, 전망 본문·근거는 카드 안) 같은 제목의
 * 섹션을 아래에 한 번 더 만들지 않는다. 카드가 없을 때(구조화 값 없음)만 본문 전체를
 * 그 섹션 제목으로 한 번 그린다.
 *
 * 이전에는 카드가 그린 줄까지 다시 넘겨 같은 제목·같은 문장이 두 번 나왔다. 그래서
 * 주목 선수 카드 뒤에 "이번 경기의 주목 선수 4명입니다." 섹션이, AI 전망 카드 뒤에
 * 전망 본문 섹션이 한 번 더 표시됐다.
 */
const cardLeftovers = computed(() => {
  const out: { id: string; title: string; blocks: ReturnType<typeof bodyBlocks> }[] = []
  const push = (id: string, cardShown: boolean) => {
    const section = view.value.sections[id]
    if (!section) return
    if (cardShown) return
    if (!section.body.trim()) return
    out.push({ id, title: section.title, blocks: bodyBlocks(section.body) })
  }
  push('section_players', view.value.players.length > 0)
  push('section_ai_forecast', hasForecast.value)
  push('section_availability', view.value.injuries.length > 0)
  push('section_outlook', view.value.media.length > 0)
  push('section_odds', view.value.odds.length > 0)
  return out
})

const broken = ref<Record<string, boolean>>({})
const photoOk = (key: string) => !broken.value[key]
const markBroken = (key: string) => {
  broken.value = { ...broken.value, [key]: true }
}

/**
 * "홈"/"원정" 글자는 **확인된 경우에만** 붙인다. 확인하지 못한 묶음은 팀 이름만 보여준다
 * (배열 순서로 홈/원정을 만들지 않는다).
 */
const sideLabel = (side: 0 | 1 | null) => (side === 0 ? '홈' : side === 1 ? '원정' : null)
const tintOf = (column: 0 | 1) => (column === 0 ? 'home' : 'away')
</script>

<template>
  <div :class="['mpv', `mpv--${variant}`]" data-testid="match-preview-body">
    <header v-if="variant === 'standalone'" class="mpv-head">
      <h1 class="mpv-head__title">경기 전 프리뷰</h1>
      <p class="mpv-head__fixture">
        <b>{{ view.fixture.home.name }}</b>
        <span class="mpv-head__vs">vs</span>
        <b>{{ view.fixture.away.name }}</b>
        <span v-if="view.fixture.league" class="mpv-head__meta">{{ view.fixture.league }}</span>
        <time v-if="view.fixture.kickoff_at && kickoff" :datetime="view.fixture.kickoff_at">
          {{ kickoff.date }} {{ kickoff.time }} KST
        </time>
      </p>
    </header>

    <!-- AI 경기 전망: 본문 2/3 + 점수 1/3, 근거는 본문 아래 별도 큰 글씨 -->
    <section v-if="hasForecast" class="mpv-section" aria-labelledby="mpv-forecast-title">
      <h2 id="mpv-forecast-title" class="mpv-section__title">AI 경기 전망</h2>
      <div class="mpv-analysis">
        <div class="mpv-analysis__body">
          <div v-if="forecast.forecastLines.length" class="mpv-lead">
            <p v-for="(paragraph, index) in forecast.forecastLines" :key="index">
              <InlineEmphasis :text="paragraph" />
            </p>
          </div>
          <div v-if="forecast.reasoning.length" class="mpv-reasons" aria-labelledby="mpv-reasons-title">
            <h3 id="mpv-reasons-title" class="mpv-reasons__title">전망 근거</h3>
            <ul class="mpv-reasons__list">
              <li v-for="(reason, index) in forecast.reasoning" :key="index">
                <span class="mpv-reasons__index" aria-hidden="true">{{ index + 1 }}</span>
                <span><InlineEmphasis :text="reason" /></span>
              </li>
            </ul>
          </div>
        </div>
        <aside v-if="forecast.score" class="mpv-prediction" aria-labelledby="mpv-prediction-title">
          <p id="mpv-prediction-title" class="mpv-prediction__label">AI 예상 스코어</p>
          <p class="mpv-prediction__score">
            <b>{{ forecast.score.home }}</b>
            <span aria-hidden="true">:</span>
            <b>{{ forecast.score.away }}</b>
          </p>
          <strong v-if="forecast.lean_label" class="mpv-prediction__lean">{{ forecast.lean_label }}</strong>
        </aside>
      </div>
    </section>

    <!-- 주목 선수: 팀별 좌우, 개별 옅은 그라데이션 패널, 세로 중앙 사진 -->
    <section v-if="view.players.length" class="mpv-section" aria-labelledby="mpv-players-title">
      <h2 id="mpv-players-title" class="mpv-section__title">주목 선수</h2>
      <!-- 저장된 도입 문장(예: "이번 경기의 주목 선수 4명입니다.")은 카드 안에 그대로 둔다. -->
      <div v-if="view.playerIntro.length" class="mpv-lead mpv-lead--intro">
        <p v-for="(intro, index) in view.playerIntro" :key="`player-intro-${index}`">
          <InlineEmphasis :text="intro" />
        </p>
      </div>
      <div class="mpv-teams">
        <div
          v-for="entry in playerGroups"
          :key="`player-team-${entry.group.team ?? 'unknown'}-${entry.column}`"
          :class="['mpv-team', `mpv-team--${tintOf(entry.column)}`]"
        >
          <p class="mpv-team__head">
            <img
              v-if="badgeOf(entry.column, entry.side) && photoOk(teamPhotoKey('players', entry.column))"
              :src="badgeOf(entry.column, entry.side) as string"
              alt=""
              loading="lazy"
              decoding="async"
              @error="markBroken(teamPhotoKey('players', entry.column))"
            />
            <b v-if="entry.group.team">{{ entry.group.team }}</b>
            <span v-if="sideLabel(entry.side)">{{ sideLabel(entry.side) }}</span>
          </p>
          <article v-for="(player, index) in entry.group.rows" :key="`${player.team}-${player.player}-${index}`" class="mpv-entry">
            <div class="mpv-entry__body">
              <h3 class="mpv-entry__name">{{ player.player }}</h3>
              <p class="mpv-entry__text"><InlineEmphasis :text="player.reason" /></p>
            </div>
            <div class="mpv-entry__photo">
              <img
                v-if="player.photo_url && photoOk(`player-${player.player}`)"
                :src="player.photo_url"
                :alt="`${player.player} 선수 사진`"
                loading="lazy"
                decoding="async"
                @error="markBroken(`player-${player.player}`)"
              />
              <span v-else role="img" :aria-label="`${player.player} 사진 없음`">{{ player.player }}</span>
            </div>
          </article>
        </div>
      </div>
    </section>

    <!-- 부상·결장: 같은 좌우 구조 -->
    <section v-if="view.injuries.length" class="mpv-section" aria-labelledby="mpv-injuries-title">
      <h2 id="mpv-injuries-title" class="mpv-section__title">부상·결장</h2>
      <div class="mpv-teams">
        <div
          v-for="entry in injuryGroups"
          :key="`injury-team-${entry.group.team ?? 'unknown'}-${entry.column}`"
          :class="['mpv-team', `mpv-team--${tintOf(entry.column)}`]"
        >
          <p class="mpv-team__head">
            <img
              v-if="badgeOf(entry.column, entry.side) && photoOk(teamPhotoKey('injuries', entry.column))"
              :src="badgeOf(entry.column, entry.side) as string"
              alt=""
              loading="lazy"
              decoding="async"
              @error="markBroken(teamPhotoKey('injuries', entry.column))"
            />
            <b v-if="entry.group.team">{{ entry.group.team }}</b>
            <span v-if="sideLabel(entry.side)">{{ sideLabel(entry.side) }}</span>
          </p>
          <article v-for="(injury, index) in entry.group.rows" :key="`${injury.team}-${injury.player}-${index}`" class="mpv-entry">
            <div class="mpv-entry__body">
              <p class="mpv-entry__name">
                <b>{{ injury.player }}</b>
                <span :class="['mpv-tag', injury.status === 'out' ? 'mpv-tag--out' : 'mpv-tag--doubt']">
                  {{ injury.status_label }}
                </span>
              </p>
              <p v-if="injury.detail" class="mpv-entry__text"><InlineEmphasis :text="injury.detail" /></p>
            </div>
            <div class="mpv-entry__photo">
              <img
                v-if="injury.photo_url && photoOk(`injury-${injury.player}`)"
                :src="injury.photo_url"
                :alt="`${injury.player} 선수 사진`"
                loading="lazy"
                decoding="async"
                @error="markBroken(`injury-${injury.player}`)"
              />
              <span v-else role="img" :aria-label="`${injury.player} 사진 없음`">{{ injury.player }}</span>
            </div>
          </article>
        </div>
      </div>
    </section>

    <!-- 매체 2/3 + 배당 1/3 -->
    <section
      v-if="view.media.length || view.odds.length"
      class="mpv-section mpv-section--last"
      aria-labelledby="mpv-media-title"
    >
      <div :class="['mpv-evidence', { 'mpv-evidence--single': !view.media.length || !view.odds.length }]">
        <div v-if="view.media.length" class="mpv-panel">
          <h2 id="mpv-media-title" class="mpv-section__title">외부 매체 전망</h2>
          <ul class="mpv-media">
            <li v-for="(item, index) in view.media" :key="`${item.publisher}-${index}`">
              <p class="mpv-media__head">
                <b>{{ item.publisher }}</b>
                <a v-if="item.url" :href="item.url" target="_blank" rel="noopener noreferrer">기사 열기</a>
              </p>
              <p class="mpv-media__text"><InlineEmphasis :text="item.statement" /></p>
            </li>
          </ul>
        </div>
        <div v-if="view.odds.length" class="mpv-panel mpv-evidence__odds">
          <h2 class="mpv-section__title">배당</h2>
          <div class="mpv-odds">
            <div v-for="(row, index) in view.odds" :key="`${row.source}-${index}`">
              <p class="mpv-odds__heading">
                {{ row.source }}
                <span v-if="row.observed_at" class="mpv-odds__source">{{ row.observed_at }}</span>
              </p>
              <dl class="mpv-odds__cells">
                <div v-for="cell in row.cells" :key="cell.label" class="mpv-odds__cell">
                  <dt>{{ cell.label }}</dt>
                  <dd :class="{ 'mpv-odds__empty': !cell.value }">{{ cell.value ?? '—' }}</dd>
                </div>
              </dl>
            </div>
          </div>
        </div>
      </div>
    </section>

    <!-- 구조화 값이 없어 카드로 그리지 못한 저장 본문. 내용을 숨기지 않고 그대로 잇는다. -->
    <section
      v-for="section in [...cardLeftovers, ...textSections]"
      :key="`body-${section.id}`"
      class="mpv-section mpv-section--body"
      :data-testid="`preview-body-section-${section.id}`"
    >
      <h2 class="mpv-section__title">{{ section.title }}</h2>
      <div class="mpv-saved-body">
        <template v-for="(block, index) in section.blocks" :key="index">
          <h3 v-if="block.kind === 'heading'" :class="block.level === 2 ? 'mpv-saved-h2' : 'mpv-saved-h3'">
            {{ block.text }}
          </h3>
          <p v-else-if="block.kind === 'paragraph'"><InlineEmphasis :text="block.text" /></p>
          <ul v-else class="mpv-saved-list">
            <li v-for="(item, itemIndex) in block.items" :key="itemIndex">
              <InlineEmphasis :text="item" />
            </li>
          </ul>
        </template>
      </div>
    </section>
  </div>
</template>

<style scoped>
/* 주목 선수 카드의 저장된 도입 문장. 팀 2열 위에 한 줄로 놓는다. */
.mpv-lead--intro {
  margin-top: var(--mpv-space-3);
}

/* 저장 본문 폴백 블록. 카드로 그리지 못한 섹션도 같은 리듬으로 읽히게 한다. */
.mpv-saved-body {
  display: grid;
  gap: var(--mpv-space-3);
  margin-top: var(--mpv-space-3);
  max-width: 72ch;
  color: var(--mpv-ink-2);
  font-size: var(--mpv-text-md);
  line-height: 1.85;
  word-break: keep-all;
}

.mpv-saved-h2 {
  font-size: var(--mpv-text-title);
  font-weight: 700;
  color: var(--mpv-ink);
}

.mpv-saved-h3 {
  font-size: var(--mpv-text-lead);
  font-weight: 700;
  color: var(--mpv-ink);
}

.mpv-saved-list {
  display: grid;
  gap: var(--mpv-space-2);
  padding-left: var(--mpv-space-4);
  list-style: disc;
}

.mpv-saved-body :deep(strong) {
  color: var(--mpv-ink);
  font-weight: 750;
}

/* 한쪽만 있는 경우(매체만/배당만) 빈 칸을 만들지 않고 폭을 다 쓴다. */
.mpv-evidence--single {
  grid-template-columns: minmax(0, 1fr);
}
</style>
