<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { Search } from 'lucide-vue-next'
import { generalApi, type CoachListItem, type LeagueListItem, type PlayerListItem } from '@/lib/api/general'
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

const selectedLeagueId = computed(() =>
  selectedLeague.value ? Number(selectedLeague.value) : null,
)

const metricLabels: Record<MetricKey, string> = {
  goals: '득점',
  assists: '도움',
  yellow_cards: '경고',
  red_cards: '퇴장',
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
  <main class="page app-container">
    <header class="page__header">
      <div>
        <p class="eyebrow">Players</p>
        <h1>선수</h1>
      </div>
      <form class="search" @submit.prevent="loadPlayers">
        <Search :size="16" />
        <input v-model="query" type="search" placeholder="선수명 검색" />
        <button type="submit">검색</button>
      </form>
    </header>

    <section class="toolbar" aria-label="선수 필터">
      <label>
        <span>리그</span>
        <select v-model="selectedLeague">
          <option value="">전체</option>
          <option v-for="league in leagues" :key="league.external_id" :value="String(league.external_id)">
            {{ leagueName(league) }}
          </option>
        </select>
      </label>
      <label>
        <span>정렬</span>
        <select v-model="metric">
          <option value="goals">득점</option>
          <option value="assists">도움</option>
          <option value="yellow_cards">경고</option>
          <option value="red_cards">퇴장</option>
        </select>
      </label>
    </section>

    <div v-if="status === 'loading'" class="state">선수 데이터를 불러오는 중입니다.</div>
    <div v-else-if="status === 'error'" class="state state--error">{{ error }}</div>
    <div v-else-if="players.length === 0 && coaches.length === 0" class="state">조건에 맞는 선수/감독이 없습니다.</div>
    <section v-else-if="coaches.length" class="coach-strip" aria-label="감독">
      <article v-for="row in coaches" :key="`${row.team.external_id}-${row.coach.slug}`" class="coach-card">
        <img v-if="row.coach.photo_url" :src="row.coach.photo_url" alt="" />
        <div v-else class="coach-card__fallback">{{ playerName(row.coach).slice(0, 1) }}</div>
        <div>
          <span>감독</span>
          <strong>{{ playerName(row.coach) }}</strong>
          <router-link :to="{ name: 'team-detail', params: { slug: row.team.slug } }">
            {{ teamName(row.team) }}
          </router-link>
        </div>
      </article>
    </section>
    <section v-if="players.length" class="table-wrap">
      <table>
        <thead>
          <tr>
            <th class="player-col">선수</th>
            <th>팀</th>
            <th>리그</th>
            <th>포지션</th>
            <th>출전</th>
            <th>{{ metricLabels[metric] }}</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in players" :key="`${row.player.external_id}-${row.player.team.external_id}`">
            <td class="player-cell">
              <img v-if="row.player.photo_url" :src="row.player.photo_url" alt="" />
              <router-link :to="{ name: 'player-detail', params: { slug: row.player.slug } }">
                {{ playerName(row.player) }}
              </router-link>
            </td>
            <td>
              <router-link :to="{ name: 'team-detail', params: { slug: row.player.team.slug } }">
                {{ teamName(row.player.team) }}
              </router-link>
            </td>
            <td>{{ leagueName(row.player.league) }}</td>
            <td>{{ row.position ?? '-' }}</td>
            <td>{{ row.appearances ?? '-' }}</td>
            <td class="metric">{{ row.metric_value }}</td>
          </tr>
        </tbody>
      </table>
    </section>
  </main>
</template>

<style scoped>
.page {
  height: calc(100vh - var(--header-height));
  overflow-y: auto;
  padding-block: 24px 48px;
}
.page__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 18px;
}
.eyebrow {
  margin: 0 0 4px;
  color: var(--color-muted);
  font-size: 12px;
  text-transform: uppercase;
  letter-spacing: 0;
}
h1 {
  margin: 0;
  font-size: 28px;
}
.search {
  display: flex;
  align-items: center;
  gap: 8px;
  width: min(360px, 100%);
  height: 38px;
  border: 1px solid var(--color-border);
  border-radius: 6px;
  padding-inline: 10px 4px;
}
.search input {
  flex: 1;
  min-width: 0;
  border: 0;
  background: transparent;
  color: var(--color-fg);
}
.search button {
  height: 30px;
  border: 1px solid var(--color-border);
  border-radius: 5px;
  background: var(--color-card);
  cursor: pointer;
}
.toolbar {
  display: flex;
  gap: 12px;
  margin-bottom: 18px;
}
.coach-strip {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
  gap: 10px;
  margin-bottom: 18px;
}
.coach-card {
  display: grid;
  grid-template-columns: 46px 1fr;
  align-items: center;
  gap: 10px;
  padding: 12px;
  border: 1px solid var(--color-border);
  border-radius: 8px;
  background: var(--color-card);
}
.coach-card img,
.coach-card__fallback {
  width: 46px;
  height: 46px;
  border-radius: 50%;
}
.coach-card img {
  object-fit: cover;
}
.coach-card__fallback {
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--color-bg);
  border: 1px solid var(--color-border);
  font-weight: 700;
}
.coach-card span,
.coach-card a {
  display: block;
  color: var(--color-muted);
  font-size: 12px;
}
.coach-card strong {
  display: block;
  margin: 2px 0;
}
label {
  display: grid;
  gap: 6px;
  min-width: 180px;
  color: var(--color-muted);
  font-size: 12px;
}
select {
  height: 36px;
  border: 1px solid var(--color-border);
  border-radius: 6px;
  background: var(--color-bg);
  color: var(--color-fg);
  padding-inline: 10px;
}
.table-wrap {
  border: 1px solid var(--color-border);
  border-radius: 8px;
  overflow: hidden;
  background: var(--color-card);
}
table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}
th,
td {
  padding: 10px 12px;
  border-bottom: 1px solid var(--color-border);
  text-align: center;
}
th {
  color: var(--color-muted);
  font-weight: 600;
}
tr:last-child td {
  border-bottom: 0;
}
a {
  text-decoration: none;
}
.player-col,
.player-cell {
  text-align: left;
}
.player-cell {
  display: flex;
  align-items: center;
  gap: 8px;
  font-weight: 600;
}
.player-cell img {
  width: 30px;
  height: 30px;
  border-radius: 50%;
  object-fit: cover;
}
.metric {
  font-weight: 700;
}
.state {
  padding: 28px;
  border: 1px solid var(--color-border);
  border-radius: 8px;
  background: var(--color-card);
  color: var(--color-muted);
}
.state--error {
  color: #b91c1c;
}
</style>
