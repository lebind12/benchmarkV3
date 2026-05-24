<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { BarChart3 } from 'lucide-vue-next'
import { generalApi, type LeagueListItem, type StatsPayload } from '@/lib/api/general'
import { leagueName, playerName, teamName } from '@/lib/displayNames'
import type { MetricKey } from '@/types/home'

const leagues = ref<LeagueListItem[]>([])
const selectedLeague = ref('39')
const payload = ref<StatsPayload | null>(null)
const status = ref<'idle' | 'loading' | 'ok' | 'error'>('idle')
const error = ref<string | null>(null)

const selectedLeagueId = computed(() => Number(selectedLeague.value || 39))
const metrics: { key: MetricKey; label: string }[] = [
  { key: 'goals', label: '득점' },
  { key: 'assists', label: '도움' },
  { key: 'yellow_cards', label: '경고' },
  { key: 'red_cards', label: '퇴장' },
]

async function loadLeagues() {
  leagues.value = (await generalApi.leagues()).items
}

async function loadStats() {
  status.value = 'loading'
  error.value = null
  try {
    payload.value = await generalApi.stats(selectedLeagueId.value)
    status.value = 'ok'
  } catch (err) {
    payload.value = null
    error.value = (err as Error).message
    status.value = 'error'
  }
}

onMounted(async () => {
  await loadLeagues()
  await loadStats()
})

watch(selectedLeague, () => {
  void loadStats()
})
</script>

<template>
  <main class="page app-container">
    <header class="page__header">
      <div>
        <p class="eyebrow">Statistics</p>
        <h1>스탯</h1>
      </div>
      <label class="league-picker">
        <span>리그</span>
        <select v-model="selectedLeague">
          <option v-for="league in leagues" :key="league.external_id" :value="String(league.external_id)">
            {{ leagueName(league) }}
          </option>
        </select>
      </label>
    </header>

    <div v-if="status === 'loading'" class="state">스탯 데이터를 불러오는 중입니다.</div>
    <div v-else-if="status === 'error'" class="state state--error">{{ error }}</div>
    <section v-else-if="payload" class="stats-grid">
      <article v-for="metric in metrics" :key="metric.key" class="leader-card">
        <header>
          <BarChart3 :size="17" />
          <h2>{{ metric.label }}</h2>
        </header>
        <ol>
          <li v-for="row in payload.leaders[metric.key].rows" :key="row.player.external_id">
            <span class="rank">{{ row.rank }}</span>
            <router-link :to="{ name: 'player-detail', params: { slug: row.player.slug } }">
              {{ playerName(row.player) }}
            </router-link>
            <small>{{ teamName(row.player.team) }}</small>
            <strong>{{ row.metric_value }}</strong>
          </li>
        </ol>
      </article>
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
  align-items: end;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 20px;
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
.league-picker {
  display: grid;
  gap: 6px;
  min-width: 220px;
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
.stats-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(280px, 1fr));
  gap: 14px;
}
.leader-card {
  border: 1px solid var(--color-border);
  border-radius: 8px;
  background: var(--color-card);
  overflow: hidden;
}
.leader-card header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 12px 14px;
  border-bottom: 1px solid var(--color-border);
}
h2 {
  margin: 0;
  font-size: 16px;
}
ol {
  list-style: none;
  margin: 0;
  padding: 0;
}
li {
  display: grid;
  grid-template-columns: 32px 1fr 120px 42px;
  align-items: center;
  gap: 8px;
  min-height: 42px;
  padding: 8px 14px;
  border-bottom: 1px solid var(--color-border);
  font-size: 13px;
}
li:last-child {
  border-bottom: 0;
}
.rank,
small {
  color: var(--color-muted);
}
a {
  text-decoration: none;
  font-weight: 600;
}
strong {
  text-align: right;
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
@media (max-width: 900px) {
  .stats-grid {
    grid-template-columns: 1fr;
  }
  li {
    grid-template-columns: 28px 1fr 38px;
  }
  small {
    display: none;
  }
}
</style>
