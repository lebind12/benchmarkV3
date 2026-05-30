<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import Chart from 'chart.js/auto'
import { BarChart3, Table2, Trophy } from 'lucide-vue-next'
import { generalApi, type LeagueListItem, type StatsPayload } from '@/lib/api/general'
import { leagueName, playerName, teamName } from '@/lib/displayNames'
import type { MetricKey, TopPlayerRow } from '@/types/home'

const leagues = ref<LeagueListItem[]>([])
const selectedLeague = ref('39')
const activeMetric = ref<MetricKey>('goals')
const payload = ref<StatsPayload | null>(null)
const status = ref<'idle' | 'loading' | 'ok' | 'error'>('idle')
const error = ref<string | null>(null)
const chartCanvas = ref<HTMLCanvasElement | null>(null)
let chart: Chart | null = null

const metrics: { key: MetricKey; label: string }[] = [
  { key: 'goals', label: '득점' },
  { key: 'assists', label: '도움' },
  { key: 'yellow_cards', label: '경고' },
  { key: 'red_cards', label: '퇴장' },
]

const selectedLeagueId = computed(() => Number(selectedLeague.value || 39))
const metricLabel = computed(() => metrics.find((item) => item.key === activeMetric.value)?.label ?? '수치')
const selectedLeagueName = computed(() => {
  const league = leagues.value.find((item) => String(item.external_id) === selectedLeague.value)
  return leagueName(league ?? payload.value?.leaders[activeMetric.value]?.league ?? null)
})
const activeRows = computed<TopPlayerRow[]>(() => payload.value?.leaders[activeMetric.value]?.rows ?? [])
const standingsRows = computed(() => payload.value?.standings.rows ?? [])
const maxMetricValue = computed(() => Math.max(...activeRows.value.map((row) => row.metric_value), 1))

function renderChart() {
  if (!chartCanvas.value) return
  chart?.destroy()
  const rows = activeRows.value.slice(0, 10)
  chart = new Chart(chartCanvas.value, {
    type: 'bar',
    data: {
      labels: rows.map((row) => playerName(row.player)),
      datasets: [
        {
          label: metricLabel.value,
          data: rows.map((row) => row.metric_value),
          borderWidth: 0,
          borderRadius: 6,
          backgroundColor: '#38bdf8',
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      indexAxis: 'y',
      animation: { duration: 450 },
      plugins: {
        legend: { display: false },
        tooltip: { enabled: true },
      },
      scales: {
        x: {
          beginAtZero: true,
          grid: { color: 'rgba(148, 163, 184, 0.18)' },
          ticks: { precision: 0 },
        },
        y: {
          grid: { display: false },
          ticks: { font: { size: 11 } },
        },
      },
    },
  })
}

async function loadLeagues() {
  leagues.value = (await generalApi.leagues()).items
}

async function loadStats() {
  status.value = 'loading'
  error.value = null
  try {
    payload.value = await generalApi.stats(selectedLeagueId.value)
    status.value = 'ok'
    await nextTick()
    renderChart()
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

onBeforeUnmount(() => {
  chart?.destroy()
})

watch(selectedLeague, () => {
  void loadStats()
})

watch([activeMetric, payload], async () => {
  await nextTick()
  renderChart()
})
</script>

<template>
  <main class="stats-page app-container" data-testid="ui-review-stats-page">
    <header class="page-head">
      <div>
        <span class="eyebrow">스탯 센터</span>
        <h1>차트와 테이블을 함께 보는 리그 스탯</h1>
        <p>{{ selectedLeagueName }} · 상위 선수와 순위 흐름을 한 화면에서 확인합니다.</p>
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

    <section class="metric-strip" aria-label="스탯 지표">
      <button
        v-for="metric in metrics"
        :key="metric.key"
        type="button"
        :class="['metric-card', { 'metric-card--active': activeMetric === metric.key }]"
        @click="activeMetric = metric.key"
      >
        <span>{{ metric.label }}</span>
        <strong>{{ payload?.leaders[metric.key]?.rows[0]?.metric_value ?? '-' }}</strong>
        <em>{{ playerName(payload?.leaders[metric.key]?.rows[0]?.player ?? null) }}</em>
      </button>
    </section>

    <section class="stats-grid">
      <article class="panel chart-panel">
        <header class="panel__head">
          <span><BarChart3 :size="16" aria-hidden="true" /> {{ metricLabel }} Top 10</span>
          <strong>Chart.js</strong>
        </header>
        <div v-if="status === 'loading'" class="state">스탯 로딩 중</div>
        <div v-else-if="status === 'error'" class="state state--error">{{ error }}</div>
        <div v-else class="chart-wrap">
          <canvas ref="chartCanvas" aria-label="상위 선수 막대 차트" />
        </div>
      </article>

      <article class="panel table-panel">
        <header class="panel__head">
          <span><Table2 :size="16" aria-hidden="true" /> 선수 테이블</span>
          <strong>{{ metricLabel }}</strong>
        </header>
        <div class="table-scroll">
          <table>
            <thead>
              <tr>
                <th>#</th>
                <th class="name-col">선수</th>
                <th>팀</th>
                <th>{{ metricLabel }}</th>
                <th>비중</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="row in activeRows" :key="row.player.external_id">
                <td>{{ row.rank }}</td>
                <td class="name-col">
                  <router-link :to="{ name: 'player-detail', params: { slug: row.player.slug } }">
                    {{ playerName(row.player) }}
                  </router-link>
                </td>
                <td>{{ teamName(row.player.team) }}</td>
                <td class="metric-value">{{ row.metric_value }}</td>
                <td>
                  <span class="bar-cell">
                    <i :style="{ width: `${Math.round((row.metric_value / maxMetricValue) * 100)}%` }" />
                  </span>
                </td>
              </tr>
            </tbody>
          </table>
          <div v-if="status === 'ok' && activeRows.length === 0" class="state">해당 지표 데이터가 없습니다.</div>
        </div>
      </article>

      <aside class="panel standings-panel">
        <header class="panel__head">
          <span><Trophy :size="16" aria-hidden="true" /> 순위 요약</span>
          <strong>Top 8</strong>
        </header>
        <ol class="standings-list">
          <li v-for="row in standingsRows" :key="row.team.external_id">
            <span>{{ row.rank }}</span>
            <strong>{{ teamName(row.team) }}</strong>
            <em>{{ row.points }}점</em>
          </li>
        </ol>
      </aside>
    </section>
  </main>
</template>

<style scoped>
.stats-page {
  display: grid;
  grid-template-rows: auto auto minmax(0, 1fr);
  gap: 12px;
  height: calc(100vh - var(--header-height));
  min-height: 0;
  overflow: hidden;
  padding-block: 16px;
}

.page-head,
.metric-card,
.panel {
  border: 1px solid var(--color-border);
  border-radius: 8px;
  background: var(--color-card);
}

.page-head {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 260px;
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
}

.page-head p {
  margin: 6px 0 0;
  color: var(--color-muted);
  font-size: 12px;
}

.league-picker {
  display: grid;
  gap: 6px;
  color: var(--color-muted);
  font-size: 11px;
  font-weight: 800;
}

select {
  height: 36px;
  border: 1px solid var(--color-border);
  border-radius: 6px;
  padding: 0 10px;
  color: var(--color-fg);
  background: var(--color-bg);
}

.metric-strip {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 10px;
}

.metric-card {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  align-items: end;
  gap: 2px 8px;
  min-height: 72px;
  padding: 10px 12px;
  color: var(--color-fg);
  text-align: left;
  cursor: pointer;
}

.metric-card span {
  color: var(--color-muted);
  font-size: 12px;
  font-weight: 900;
}

.metric-card strong {
  grid-row: span 2;
  font-size: 28px;
  line-height: 1;
}

.metric-card em {
  overflow: hidden;
  color: var(--color-fg);
  font-size: 12px;
  font-style: normal;
  font-weight: 800;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.metric-card--active {
  box-shadow: inset 0 0 0 1px var(--color-fg);
}

.stats-grid {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(360px, 0.85fr);
  grid-template-rows: minmax(0, 1fr) minmax(0, 0.8fr);
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

.chart-panel {
  grid-row: 1 / 2;
}

.table-panel {
  grid-row: 2 / 3;
}

.standings-panel {
  grid-column: 2 / 3;
  grid-row: 1 / 3;
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

.chart-wrap {
  min-height: 0;
  padding: 14px;
  overflow: hidden;
}

.chart-wrap canvas {
  width: 100%;
  height: 100%;
}

.table-scroll {
  min-height: 0;
  overflow-y: auto;
  overflow-x: auto;
  scrollbar-width: none;
}

.table-scroll::-webkit-scrollbar,
.standings-list::-webkit-scrollbar {
  display: none;
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
  color: var(--color-muted);
  background: var(--color-bg);
}

.name-col {
  text-align: left;
}

a {
  color: var(--color-fg);
  text-decoration: none;
  font-weight: 900;
}

.metric-value {
  font-weight: 900;
}

.bar-cell {
  display: block;
  width: 96px;
  height: 7px;
  border-radius: 999px;
  background: var(--color-border);
  overflow: hidden;
}

.bar-cell i {
  display: block;
  height: 100%;
  border-radius: inherit;
  background: #38bdf8;
}

.standings-list {
  display: grid;
  align-content: start;
  gap: 4px;
  min-height: 0;
  margin: 0;
  padding: 10px;
  list-style: none;
  overflow-y: auto;
  overflow-x: hidden;
  scrollbar-width: none;
}

.standings-list li {
  display: grid;
  grid-template-columns: 28px minmax(0, 1fr) auto;
  align-items: center;
  gap: 8px;
  border-bottom: 1px solid var(--color-border);
  padding: 8px 0;
  font-size: 12px;
}

.standings-list span,
.standings-list em {
  color: var(--color-muted);
  font-style: normal;
  font-weight: 800;
}

.standings-list strong {
  overflow: hidden;
  color: var(--color-fg);
  text-overflow: ellipsis;
  white-space: nowrap;
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
