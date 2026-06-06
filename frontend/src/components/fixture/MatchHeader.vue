<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { MonitorPlay, UsersRound, X } from 'lucide-vue-next'
import type { MatchDetail } from '@/types/fixtureDetail'
import GoalHistoryInline from './GoalHistoryInline.vue'

const props = defineProps<{ match: MatchDetail }>()
const isBroadcastPickerOpen = ref(false)
const canOpenBroadcast = computed(
  () => typeof localStorage !== 'undefined' && localStorage.getItem('mockRole') === 'ADMIN',
)

const isFinished = computed(() =>
  ['FT', 'AET', 'PEN'].includes(props.match.status_short),
)
const isLive = computed(() =>
  ['1H', 'HT', '2H', 'ET', 'BT', 'P'].includes(props.match.status_short),
)
const isCancelled = computed(() =>
  ['PST', 'CANC', 'SUSP'].includes(props.match.status_short),
)

const scoreLabel = computed(() => {
  const { status_short, goals_home, goals_away, penalty_home, penalty_away } =
    props.match
  if (status_short === 'NS') return 'vs'
  if (isCancelled.value) return '—'
  if (status_short === 'PEN' && penalty_home != null && penalty_away != null) {
    return `${goals_home}(${penalty_home}) - ${goals_away}(${penalty_away})`
  }
  return `${goals_home ?? 0} - ${goals_away ?? 0}`
})

const cancelLabel = computed(() => {
  if (props.match.status_short === 'PST') return '연기됨'
  if (props.match.status_short === 'CANC') return '취소됨'
  if (props.match.status_short === 'SUSP') return '중단됨'
  return null
})

function fmtKST(iso: string): string {
  const d = new Date(iso)
  // 'sv-SE' yields YYYY-MM-DD HH:MM:SS in local; use Asia/Seoul
  const parts = new Intl.DateTimeFormat('sv-SE', {
    timeZone: 'Asia/Seoul',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  }).formatToParts(d)
  const get = (t: string) => parts.find((p) => p.type === t)?.value
  return `${get('year')}-${get('month')}-${get('day')} ${get('hour')}:${get('minute')}`
}

const kickoffKst = computed(() => fmtKST(props.match.kickoff_at))
const kickoffTime = computed(() => kickoffKst.value.split(' ')[1])

const metaParts = computed(() => {
  const parts: string[] = []
  parts.push(
    props.match.league.name_ko ?? props.match.league.name,
  )
  if (props.match.round) parts.push(props.match.round)
  parts.push(props.match.status_short)
  if (props.match.venue?.name) parts.push(props.match.venue.name)
  if (props.match.referee) parts.push(props.match.referee)
  parts.push(`${kickoffKst.value} KST`)
  return parts
})

const homeName = computed(
  () => props.match.home.name_ko ?? props.match.home.name,
)
const awayName = computed(
  () => props.match.away.name_ko ?? props.match.away.name,
)

const broadcastQuery = computed(() => {
  const query = new URLSearchParams({
    fixtureId: String(props.match.external_id),
    league: props.match.league.slug,
  })
  return query.toString()
})

const watchTogetherHref = computed(() => `/broadcast.html?${broadcastQuery.value}`)
const programHref = computed(() => `/broadcast-program.html?${broadcastQuery.value}`)

function openBroadcastPicker() {
  if (!canOpenBroadcast.value) return
  isBroadcastPickerOpen.value = true
}

function closeBroadcastPicker() {
  isBroadcastPickerOpen.value = false
}

function onKeydown(event: KeyboardEvent) {
  if (event.key === 'Escape') closeBroadcastPicker()
}

watch(isBroadcastPickerOpen, (isOpen) => {
  if (typeof window === 'undefined') return
  if (isOpen) {
    window.addEventListener('keydown', onKeydown)
    return
  }
  window.removeEventListener('keydown', onKeydown)
})

onBeforeUnmount(() => {
  if (typeof window === 'undefined') return
  window.removeEventListener('keydown', onKeydown)
})
</script>

<template>
  <header class="match-header" data-testid="match-header">
    <div class="match-header__actions">
      <button
        v-if="canOpenBroadcast"
        type="button"
        class="match-header__broadcast-button"
        data-testid="broadcast-picker-trigger"
        :aria-expanded="isBroadcastPickerOpen"
        aria-controls="broadcast-picker"
        :aria-label="`${homeName} 대 ${awayName} 스트리밍 화면 선택`"
        @click="openBroadcastPicker"
      >
        <MonitorPlay :size="16" aria-hidden="true" />
        <span>스트리밍</span>
      </button>
    </div>

    <div
      v-if="isBroadcastPickerOpen"
      class="broadcast-picker"
      data-testid="broadcast-picker"
      role="presentation"
      @click.self="closeBroadcastPicker"
    >
      <section
        id="broadcast-picker"
        class="broadcast-picker__panel"
        role="dialog"
        aria-modal="true"
        aria-labelledby="broadcast-picker-title"
      >
        <div class="broadcast-picker__header">
          <div>
            <p class="broadcast-picker__eyebrow">STREAMING</p>
            <h2 id="broadcast-picker-title">방송 화면 선택</h2>
          </div>
          <button
            type="button"
            class="broadcast-picker__close"
            data-testid="broadcast-picker-close"
            aria-label="닫기"
            @click="closeBroadcastPicker"
          >
            <X :size="18" aria-hidden="true" />
          </button>
        </div>

        <div class="broadcast-picker__options">
          <a
            class="broadcast-picker__option"
            data-testid="watch-together-link"
            :href="watchTogetherHref"
            target="_blank"
            rel="noopener noreferrer"
            @click="closeBroadcastPicker"
          >
            <span class="broadcast-picker__icon" aria-hidden="true">
              <UsersRound :size="22" />
            </span>
            <span class="broadcast-picker__copy">
              <strong>같이보기 화면</strong>
              <span>캐릭터 중심</span>
            </span>
          </a>

          <a
            class="broadcast-picker__option broadcast-picker__option--program"
            data-testid="program-link"
            :href="programHref"
            target="_blank"
            rel="noopener noreferrer"
            @click="closeBroadcastPicker"
          >
            <span class="broadcast-picker__icon" aria-hidden="true">
              <MonitorPlay :size="22" />
            </span>
            <span class="broadcast-picker__copy">
              <strong>중계용 화면</strong>
              <span>경기 화면 포함</span>
            </span>
          </a>
        </div>
      </section>
    </div>

    <div class="match-header__top">
      <div class="match-header__team match-header__team--home">
        <div class="match-header__logo" aria-hidden="true" />
        <div class="match-header__team-name">{{ homeName }}</div>
      </div>
      <div class="match-header__score" data-testid="match-score">
        <div class="match-header__score-value">{{ scoreLabel }}</div>
        <div v-if="match.status_short === 'NS'" class="match-header__kickoff">
          kickoff {{ kickoffTime }} KST
        </div>
        <div v-else-if="cancelLabel" class="match-header__status">
          {{ cancelLabel }}
        </div>
        <div v-else-if="isLive" class="match-header__status">
          {{ match.status_short }}
        </div>
      </div>
      <div class="match-header__team match-header__team--away">
        <div class="match-header__logo" aria-hidden="true" />
        <div class="match-header__team-name">{{ awayName }}</div>
      </div>
    </div>

    <div class="match-header__meta" data-testid="match-meta">
      <template v-for="(part, i) in metaParts" :key="i">
        <span>{{ part }}</span>
        <span v-if="i < metaParts.length - 1" class="match-header__dot">·</span>
      </template>
    </div>

    <GoalHistoryInline
      v-if="isFinished || isLive"
      :events="match.goal_events"
    />

    <p
      v-if="isCancelled"
      class="match-header__placeholder"
      data-testid="cancelled-placeholder"
    >
      경기가 진행되지 않았습니다
    </p>

    <p class="match-header__sla">이 페이지는 6시간마다 갱신됩니다</p>
  </header>
</template>

<style scoped>
.match-header {
  position: relative;
  display: flex;
  flex-direction: column;
  justify-content: center;
  height: 25vh;
  padding: 0.75rem 1rem;
  background: linear-gradient(
    180deg,
    color-mix(in srgb, var(--theme-primary) 14%, transparent),
    color-mix(in srgb, var(--theme-primary) 3%, transparent)
  );
  border-left: 6px solid var(--theme-primary);
  border-bottom: 1px solid color-mix(in srgb, var(--theme-primary) 25%, transparent);
  box-sizing: border-box;
}
.match-header__actions {
  position: absolute;
  top: 0.75rem;
  right: 1rem;
  display: flex;
  justify-content: flex-end;
}
.match-header__broadcast-button {
  display: inline-flex;
  align-items: center;
  gap: 0.35rem;
  min-height: 2rem;
  padding: 0 0.7rem;
  border: 1px solid var(--theme-primary);
  border-radius: 999px;
  background: var(--theme-primary);
  color: var(--theme-on-primary);
  cursor: pointer;
  font-size: 0.75rem;
  font-weight: 700;
  font-family: inherit;
  line-height: 1;
  white-space: nowrap;
  box-shadow: 0 0 0 2px color-mix(in srgb, var(--theme-primary) 18%, var(--color-bg));
}
.match-header__broadcast-button:hover,
.match-header__broadcast-button:focus-visible {
  background: var(--theme-accent);
  border-color: var(--theme-accent);
  outline: none;
}
.broadcast-picker {
  position: fixed;
  inset: 0;
  z-index: 80;
  display: grid;
  place-items: center;
  padding: 1rem;
  background:
    radial-gradient(circle at 50% 35%, color-mix(in srgb, var(--theme-primary) 18%, transparent), transparent 34rem),
    color-mix(in srgb, var(--color-bg) 76%, black 24%);
}
.broadcast-picker__panel {
  width: min(31rem, 100%);
  border: 1px solid color-mix(in srgb, var(--theme-primary) 24%, var(--border));
  border-radius: 8px;
  background: color-mix(in srgb, var(--color-bg) 96%, white 4%);
  color: var(--color-fg);
  box-shadow: 0 24px 80px color-mix(in srgb, black 40%, transparent);
}
.broadcast-picker__header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 1rem;
  padding: 1rem 1rem 0.85rem;
  border-bottom: 1px solid color-mix(in srgb, var(--theme-primary) 18%, var(--border));
}
.broadcast-picker__eyebrow {
  margin: 0 0 0.2rem;
  color: var(--theme-primary);
  font-size: 0.68rem;
  font-weight: 800;
  letter-spacing: 0.12em;
}
.broadcast-picker__header h2 {
  margin: 0;
  font-size: 1rem;
  line-height: 1.25;
}
.broadcast-picker__close {
  display: grid;
  place-items: center;
  flex: 0 0 auto;
  width: 2rem;
  height: 2rem;
  border: 1px solid color-mix(in srgb, var(--theme-primary) 18%, var(--border));
  border-radius: 50%;
  background: var(--color-bg);
  color: var(--color-fg);
  cursor: pointer;
}
.broadcast-picker__close:hover,
.broadcast-picker__close:focus-visible {
  border-color: var(--theme-primary);
  outline: none;
}
.broadcast-picker__options {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 0.75rem;
  padding: 1rem;
}
.broadcast-picker__option {
  display: grid;
  grid-template-columns: 2.5rem minmax(0, 1fr);
  align-items: center;
  gap: 0.75rem;
  min-height: 5.25rem;
  padding: 0.9rem;
  border: 1px solid color-mix(in srgb, var(--theme-primary) 16%, var(--border));
  border-radius: 8px;
  background: color-mix(in srgb, var(--theme-primary) 5%, var(--color-bg));
  color: var(--color-fg);
  text-decoration: none;
  transition: transform 140ms ease, border-color 140ms ease, background 140ms ease;
}
.broadcast-picker__option:hover,
.broadcast-picker__option:focus-visible {
  transform: translateY(-1px);
  border-color: var(--theme-primary);
  background: color-mix(in srgb, var(--theme-primary) 10%, var(--color-bg));
  outline: none;
}
.broadcast-picker__option--program {
  background: color-mix(in srgb, var(--theme-accent) 8%, var(--color-bg));
}
.broadcast-picker__icon {
  display: grid;
  place-items: center;
  width: 2.5rem;
  height: 2.5rem;
  border-radius: 8px;
  background: var(--theme-primary);
  color: var(--theme-on-primary);
}
.broadcast-picker__copy {
  display: flex;
  min-width: 0;
  flex-direction: column;
  gap: 0.2rem;
}
.broadcast-picker__copy strong {
  font-size: 0.95rem;
  line-height: 1.2;
}
.broadcast-picker__copy span {
  color: var(--muted-foreground);
  font-size: 0.78rem;
  line-height: 1.25;
}
.match-header__top {
  display: grid;
  grid-template-columns: 1fr auto 1fr;
  align-items: center;
  gap: 1rem;
}
.match-header__team {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}
.match-header__team--away {
  justify-content: flex-end;
}
.match-header__logo {
  width: 36px;
  height: 36px;
  border-radius: 50%;
  background: var(--muted);
}
.match-header__team-name {
  font-weight: 600;
  font-size: 1rem;
}
.match-header__score {
  text-align: center;
  min-width: 6rem;
}
.match-header__score-value {
  font-size: 2rem;
  font-weight: 700;
  font-variant-numeric: tabular-nums;
}
.match-header__kickoff,
.match-header__status {
  font-size: 0.75rem;
  color: var(--muted-foreground);
  text-transform: uppercase;
  letter-spacing: 0.04em;
}
.match-header__meta {
  margin-top: 0.5rem;
  font-size: 0.8rem;
  color: var(--muted-foreground);
  display: flex;
  flex-wrap: wrap;
  gap: 0.25rem;
}
.match-header__dot {
  margin: 0 0.25rem;
}
.match-header__placeholder {
  margin-top: 0.25rem;
  font-size: 0.85rem;
  color: var(--muted-foreground);
}
.match-header__sla {
  margin: 0.25rem 0 0;
  font-size: 0.7rem;
  color: var(--muted-foreground);
  opacity: 0.7;
}

@media (max-width: 640px) {
  .match-header {
    height: auto;
    min-height: 15.5rem;
    padding-top: 3.35rem;
  }
  .match-header__actions {
    left: 1rem;
    justify-content: flex-start;
  }
  .broadcast-picker__options {
    grid-template-columns: 1fr;
  }
}
</style>
