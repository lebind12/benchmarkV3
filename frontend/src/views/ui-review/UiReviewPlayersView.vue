<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { Search, SlidersHorizontal, UserRound, UsersRound } from 'lucide-vue-next'
import {
  generalApi,
  type CoachListItem,
  type LeagueListItem,
  type PlayerListItem,
} from '@/lib/api/general'
import { leagueName, playerName, teamName } from '@/lib/displayNames'
import type { MetricKey } from '@/types/home'

const leagues = ref<LeagueListItem[]>([])
const players = ref<PlayerListItem[]>([])
const coaches = ref<CoachListItem[]>([])
const selectedLeague = ref('39')
const query = ref('')
const metric = ref<MetricKey>('goals')
const status = ref<'idle' | 'loading' | 'ok' | 'error'>('idle')
const error = ref<string | null>(null)

const metricOptions: { key: MetricKey; label: string }[] = [
  { key: 'goals', label: '득점' },
  { key: 'assists', label: '도움' },
  { key: 'yellow_cards', label: '경고' },
  { key: 'red_cards', label: '퇴장' },
]

const selectedLeagueId = computed(() => (selectedLeague.value ? Number(selectedLeague.value) : null))
const metricLabel = computed(() => metricOptions.find((item) => item.key === metric.value)?.label ?? '수치')
const topPlayers = computed(() => players.value.slice(0, 24))
const tableRows = computed(() => players.value.slice(0, 140))
const separatedCoaches = computed(() => coaches.value)
const selectedLeagueName = computed(() => {
  const league = leagues.value.find((item) => String(item.external_id) === selectedLeague.value)
  return selectedLeague.value ? leagueName(league ?? null) : '전체 리그'
})

function playerMetric(row: PlayerListItem): number | null {
  const value = row[metric.value]
  return typeof value === 'number' ? value : row.metric_value
}

async function loadLeagues() {
  leagues.value = (await generalApi.leagues()).items
}

async function loadPlayers() {
  status.value = 'loading'
  error.value = null
  try {
    const payload = await generalApi.players({
      leagueId: selectedLeagueId.value,
      query: query.value.trim() || null,
      metric: metric.value,
      limit: 180,
    })
    players.value = payload.items
    coaches.value = payload.coaches
    status.value = 'ok'
  } catch (err) {
    players.value = []
    coaches.value = []
    error.value = (err as Error).message
    status.value = 'error'
  }
}

onMounted(async () => {
  await loadLeagues()
  await loadPlayers()
})

watch([selectedLeague, metric], () => {
  void loadPlayers()
})
</script>

<template>
  <main class="players-page app-container" data-testid="ui-review-players-page">
    <header class="page-head">
      <div>
        <span class="eyebrow">선수 보드</span>
        <h1>선수 목록을 선수 중심으로 재정렬</h1>
        <p>감독 정보는 별도 패널로 분리하고, 선수 검색과 랭킹 스캔을 먼저 노출합니다.</p>
      </div>
      <form class="search-box" @submit.prevent="loadPlayers">
        <Search :size="16" aria-hidden="true" />
        <input v-model="query" type="search" placeholder="선수명 검색" />
        <button type="submit">검색</button>
      </form>
    </header>

    <section class="control-bar" aria-label="선수 필터">
      <label>
        <span>리그</span>
        <select v-model="selectedLeague">
          <option value="">전체</option>
          <option v-for="league in leagues" :key="league.external_id" :value="String(league.external_id)">
            {{ leagueName(league) }}
          </option>
        </select>
      </label>
      <div class="metric-tabs" role="tablist" aria-label="정렬 기준">
        <button
          v-for="option in metricOptions"
          :key="option.key"
          type="button"
          role="tab"
          :aria-selected="metric === option.key"
          :class="['metric-tab', { 'metric-tab--active': metric === option.key }]"
          @click="metric = option.key"
        >
          {{ option.label }}
        </button>
      </div>
      <div class="summary-chip">
        <SlidersHorizontal :size="15" aria-hidden="true" />
        <span>{{ selectedLeagueName }} · {{ metricLabel }}순</span>
      </div>
    </section>

    <section class="players-grid" aria-label="선수 후보 대시보드">
      <aside class="panel top-panel">
        <header class="panel__head">
          <span><UserRound :size="16" aria-hidden="true" /> 상위 선수</span>
          <strong>{{ metricLabel }}</strong>
        </header>
        <div v-if="status === 'loading'" class="state">선수 로딩 중</div>
        <div v-else-if="status === 'error'" class="state state--error">{{ error }}</div>
        <div v-else class="top-list">
          <article v-for="row in topPlayers" :key="row.player.external_id" class="top-card">
            <img v-if="row.player.photo_url" :src="row.player.photo_url" :alt="playerName(row.player)" />
            <div v-else class="avatar-fallback">{{ playerName(row.player).slice(0, 1) }}</div>
            <div>
              <router-link :to="{ name: 'player-detail', params: { slug: row.player.slug } }">
                {{ playerName(row.player) }}
              </router-link>
              <span>{{ teamName(row.player.team) }}</span>
            </div>
            <strong>{{ playerMetric(row) ?? '-' }}</strong>
          </article>
          <div v-if="topPlayers.length === 0" class="state">조건에 맞는 선수가 없습니다</div>
        </div>
      </aside>

      <section class="panel table-panel">
        <header class="panel__head">
          <span><UsersRound :size="16" aria-hidden="true" /> 선수 테이블</span>
          <strong>{{ tableRows.length }}명</strong>
        </header>
        <div class="table-scroll">
          <table>
            <thead>
              <tr>
                <th>#</th>
                <th class="name-col">선수</th>
                <th>팀</th>
                <th>리그</th>
                <th>포지션</th>
                <th>출전</th>
                <th>평점</th>
                <th>{{ metricLabel }}</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="(row, index) in tableRows" :key="`${row.player.external_id}-${row.player.team.external_id}`">
                <td>{{ index + 1 }}</td>
                <td class="player-cell">
                  <img v-if="row.player.photo_url" :src="row.player.photo_url" alt="" />
                  <div v-else class="table-avatar">{{ playerName(row.player).slice(0, 1) }}</div>
                  <router-link :to="{ name: 'player-detail', params: { slug: row.player.slug } }">
                    {{ playerName(row.player) }}
                  </router-link>
                </td>
                <td>{{ teamName(row.player.team) }}</td>
                <td>{{ leagueName(row.player.league) }}</td>
                <td>{{ row.position ?? '-' }}</td>
                <td>{{ row.appearances ?? '-' }}</td>
                <td>{{ row.rating ?? '-' }}</td>
                <td class="metric-value">{{ playerMetric(row) ?? '-' }}</td>
              </tr>
            </tbody>
          </table>
          <div v-if="status === 'loading'" class="state">선수 데이터를 불러오는 중입니다.</div>
          <div v-else-if="status === 'error'" class="state state--error">{{ error }}</div>
          <div v-else-if="tableRows.length === 0" class="state">조건에 맞는 선수가 없습니다.</div>
        </div>
      </section>

      <aside class="panel coach-panel">
        <header class="panel__head">
          <span>감독 정보</span>
          <strong>분리 표시</strong>
        </header>
        <div class="coach-list">
          <article v-for="row in separatedCoaches" :key="`${row.team.external_id}-${row.coach.slug}`">
            <div class="coach-avatar">{{ playerName(row.coach).slice(0, 1) }}</div>
            <div>
              <strong>{{ playerName(row.coach) }}</strong>
              <span>{{ teamName(row.team) }}</span>
            </div>
          </article>
          <div v-if="separatedCoaches.length === 0" class="state">감독 데이터 없음</div>
        </div>
      </aside>
    </section>
  </main>
</template>

<style scoped>
.players-page {
  display: grid;
  grid-template-rows: auto auto minmax(0, 1fr);
  gap: 12px;
  height: calc(100vh - var(--header-height));
  min-height: 0;
  overflow: hidden;
  padding-block: 16px;
}

.page-head,
.control-bar,
.panel {
  border: 1px solid var(--color-border);
  border-radius: 8px;
  background: var(--color-card);
}

.page-head {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(320px, 420px);
  align-items: center;
  gap: 16px;
  padding: 14px;
}

.eyebrow {
  display: block;
  margin-bottom: 4px;
  color: var(--color-muted);
  font-size: 11px;
  font-weight: 900;
  text-transform: uppercase;
}

h1 {
  margin: 0;
  color: var(--color-fg);
  font-size: 22px;
  line-height: 1.2;
}

.page-head p {
  margin: 6px 0 0;
  color: var(--color-muted);
  font-size: 12px;
}

.search-box {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr) auto;
  align-items: center;
  gap: 8px;
  height: 40px;
  border: 1px solid var(--color-border);
  border-radius: 999px;
  padding: 4px 5px 4px 12px;
  background: var(--color-bg);
}

.search-box input {
  min-width: 0;
  border: 0;
  outline: 0;
  color: var(--color-fg);
  background: transparent;
}

.search-box button,
.metric-tab {
  border: 1px solid var(--color-border);
  border-radius: 999px;
  color: var(--color-fg);
  background: var(--color-card);
  cursor: pointer;
}

.search-box button {
  height: 30px;
  padding: 0 12px;
}

.control-bar {
  display: flex;
  align-items: end;
  gap: 12px;
  padding: 10px 12px;
}

label {
  display: grid;
  gap: 5px;
  min-width: 220px;
  color: var(--color-muted);
  font-size: 11px;
  font-weight: 800;
}

select {
  height: 34px;
  border: 1px solid var(--color-border);
  border-radius: 6px;
  padding: 0 10px;
  color: var(--color-fg);
  background: var(--color-bg);
}

.metric-tabs {
  display: inline-flex;
  gap: 4px;
  border: 1px solid var(--color-border);
  border-radius: 999px;
  padding: 3px;
  background: var(--color-bg);
}

.metric-tab {
  height: 28px;
  padding: 0 10px;
  color: var(--color-muted);
  background: transparent;
  font-size: 12px;
  font-weight: 800;
}

.metric-tab--active {
  color: var(--color-bg);
  background: var(--color-fg);
}

.summary-chip {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  margin-left: auto;
  border: 1px solid var(--color-border);
  border-radius: 999px;
  padding: 8px 11px;
  color: var(--color-muted);
  background: var(--color-bg);
  font-size: 12px;
  font-weight: 800;
}

.players-grid {
  display: grid;
  grid-template-columns: 280px minmax(0, 1fr) 260px;
  gap: 12px;
  min-height: 0;
  overflow: hidden;
}

.panel {
  display: grid;
  grid-template-rows: auto minmax(0, 1fr);
  min-width: 0;
  min-height: 0;
  overflow: hidden;
}

.panel__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  min-height: 42px;
  padding: 10px 12px;
  border-bottom: 1px solid var(--color-border);
  background: var(--color-bg);
}

.panel__head span {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  color: var(--color-fg);
  font-size: 13px;
  font-weight: 900;
}

.panel__head strong {
  color: var(--color-muted);
  font-size: 12px;
}

.top-list,
.coach-list {
  display: grid;
  align-content: start;
  gap: 8px;
  min-height: 0;
  overflow-y: auto;
  overflow-x: hidden;
  padding: 10px;
  scrollbar-width: none;
}

.top-list::-webkit-scrollbar,
.coach-list::-webkit-scrollbar,
.table-scroll::-webkit-scrollbar {
  display: none;
}

.top-card,
.coach-list article {
  display: grid;
  align-items: center;
  gap: 8px;
  min-width: 0;
  border: 1px solid var(--color-border);
  border-radius: 8px;
  padding: 9px;
  background: var(--color-bg);
}

.top-card {
  grid-template-columns: 42px minmax(0, 1fr) auto;
}

.coach-list article {
  grid-template-columns: 36px minmax(0, 1fr);
}

.top-card img,
.avatar-fallback,
.coach-avatar,
.table-avatar,
.player-cell img {
  border-radius: 999px;
  background: var(--color-card);
  object-fit: cover;
}

.top-card img,
.avatar-fallback {
  width: 42px;
  height: 42px;
}

.coach-avatar {
  width: 36px;
  height: 36px;
}

.table-avatar,
.player-cell img {
  width: 28px;
  height: 28px;
}

.avatar-fallback,
.coach-avatar,
.table-avatar {
  display: grid;
  place-items: center;
  border: 1px solid var(--color-border);
  color: var(--color-muted);
  font-weight: 900;
}

.top-card a,
.coach-list strong,
.player-cell a {
  overflow: hidden;
  color: var(--color-fg);
  text-decoration: none;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-weight: 900;
}

.top-card span,
.coach-list span {
  display: block;
  overflow: hidden;
  color: var(--color-muted);
  font-size: 11px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.top-card > strong {
  color: var(--color-fg);
  font-size: 22px;
}

.table-scroll {
  min-height: 0;
  overflow-y: auto;
  overflow-x: auto;
  scrollbar-width: none;
}

table {
  width: 100%;
  border-collapse: collapse;
  font-size: 12px;
}

th,
td {
  border-bottom: 1px solid var(--color-border);
  padding: 8px 10px;
  text-align: center;
  white-space: nowrap;
}

th {
  position: sticky;
  top: 0;
  z-index: 1;
  color: var(--color-muted);
  background: var(--color-bg);
  font-weight: 800;
}

.name-col,
.player-cell {
  text-align: left;
}

.player-cell {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 220px;
}

.metric-value {
  color: var(--color-fg);
  font-weight: 900;
}

.state {
  display: grid;
  place-items: center;
  min-height: 72px;
  padding: 12px;
  color: var(--color-muted);
  font-size: 12px;
}

.state--error {
  color: #b91c1c;
}
</style>
