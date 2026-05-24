<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import {
  Check,
  DatabaseZap,
  Play,
  Plus,
  RefreshCw,
  Search,
  Trash2,
} from 'lucide-vue-next'
import {
  adminApi,
  type ApiFootballLeague,
  type ApiFootballSeason,
  type ApiFootballCatalogSyncResult,
  type SyncPlanSpec,
  type SyncTarget,
  type WorkerRun,
} from '@/lib/api/admin'

const searchText = ref('World Cup')
const leagueIdText = ref('')
const searchStatus = ref<'idle' | 'loading' | 'ok' | 'error'>('idle')
const catalogSyncStatus = ref<'idle' | 'loading' | 'ok' | 'error'>('idle')
const targetStatus = ref<'idle' | 'loading' | 'ok' | 'error'>('idle')
const runStatus = ref<'idle' | 'loading' | 'ok' | 'error'>('idle')
const error = ref<string | null>(null)
const catalogSyncResult = ref<ApiFootballCatalogSyncResult | null>(null)
const activeRun = ref<WorkerRun | null>(null)
const leagues = ref<ApiFootballLeague[]>([])
const targets = ref<SyncTarget[]>([])
const plan = ref<SyncPlanSpec[]>([])
const selectedLeague = ref<ApiFootballLeague | null>(null)
const selectedSeason = ref<ApiFootballSeason | null>(null)
const options = reactive({
  include_details: true,
  include_players: true,
  include_standings: true,
  fixture_limit: '',
})
let runPollTimer: number | null = null

const activeTargets = computed(() => targets.value.filter((target) => target.is_active))
const inactiveTargets = computed(() => targets.value.filter((target) => !target.is_active))
const runProgressText = computed(() => {
  if (!activeRun.value) return '0 / 0'
  return `${activeRun.value.completed_units} / ${activeRun.value.total_units}`
})
const runProgressPercent = computed(() => activeRun.value?.progress_percent ?? 0)
const runResult = computed(() => (
  activeRun.value?.result ? JSON.stringify(activeRun.value.result, null, 2) : null
))

function displayLeagueName(target: SyncTarget) {
  return target.league.name_ko ?? target.league.name
}

function resetSelection(league: ApiFootballLeague, season: ApiFootballSeason) {
  selectedLeague.value = league
  selectedSeason.value = season
}

async function loadTargets() {
  targetStatus.value = 'loading'
  try {
    const [targetPayload, planPayload] = await Promise.all([
      adminApi.syncTargets(),
      adminApi.syncPlan(false),
    ])
    targets.value = targetPayload.items
    plan.value = planPayload.specs
    targetStatus.value = 'ok'
  } catch (err) {
    targetStatus.value = 'error'
    error.value = (err as Error).message
  }
}

async function searchLeagues() {
  searchStatus.value = 'loading'
  error.value = null
  try {
    const id = leagueIdText.value.trim() ? Number(leagueIdText.value.trim()) : null
    const payload = await adminApi.searchApiFootballLeagues({
      id,
      search: id ? null : searchText.value.trim() || null,
    })
    leagues.value = payload.items
    searchStatus.value = 'ok'
  } catch (err) {
    leagues.value = []
    error.value = (err as Error).message
    searchStatus.value = 'error'
  }
}

async function syncApiFootballCatalog() {
  if (!window.confirm('API-Football 리그/시즌 카탈로그를 전체 최신화할까요?')) return
  catalogSyncStatus.value = 'loading'
  catalogSyncResult.value = null
  error.value = null
  try {
    const payload = await adminApi.syncApiFootballCatalog({})
    catalogSyncResult.value = payload
    catalogSyncStatus.value = 'ok'
    await searchLeagues()
  } catch (err) {
    catalogSyncStatus.value = 'error'
    error.value = (err as Error).message
  }
}

async function saveTarget() {
  if (!selectedLeague.value || !selectedSeason.value) return
  targetStatus.value = 'loading'
  error.value = null
  try {
    await adminApi.createSyncTarget({
      league_external_id: selectedLeague.value.external_id,
      season_year: selectedSeason.value.year,
      include_details: options.include_details,
      include_players: options.include_players,
      include_standings: options.include_standings,
      fixture_limit: options.fixture_limit ? Number(options.fixture_limit) : null,
      is_active: true,
    })
    await loadTargets()
  } catch (err) {
    targetStatus.value = 'error'
    error.value = (err as Error).message
  }
}

async function toggleTarget(target: SyncTarget) {
  await adminApi.patchSyncTarget(target.id, { is_active: !target.is_active })
  await loadTargets()
}

async function removeTarget(target: SyncTarget) {
  if (!window.confirm(`${displayLeagueName(target)} ${target.season_year} target을 삭제할까요?`)) return
  await adminApi.deleteSyncTarget(target.id)
  await loadTargets()
}

async function runDailySync() {
  if (!window.confirm('현재 활성 target 기준으로 daily-sync를 실행할까요?')) return
  runStatus.value = 'loading'
  activeRun.value = null
  error.value = null
  try {
    const run = await adminApi.runDailySync({ fallback_defaults: false })
    activeRun.value = run
    runStatus.value = run.status === 'failed' ? 'error' : 'loading'
    scheduleRunPolling(run.id)
  } catch (err) {
    runStatus.value = 'error'
    error.value = (err as Error).message
  }
}

function clearRunPolling() {
  if (runPollTimer !== null) {
    window.clearTimeout(runPollTimer)
    runPollTimer = null
  }
}

function scheduleRunPolling(runId: string) {
  clearRunPolling()
  runPollTimer = window.setTimeout(() => pollRun(runId), 1500)
}

async function pollRun(runId: string) {
  try {
    const run = await adminApi.workerRun(runId)
    activeRun.value = run
    if (run.status === 'queued' || run.status === 'running') {
      runStatus.value = 'loading'
      scheduleRunPolling(runId)
      return
    }
    clearRunPolling()
    runStatus.value = run.status === 'succeeded' ? 'ok' : 'error'
    await loadTargets()
  } catch (err) {
    clearRunPolling()
    runStatus.value = 'error'
    error.value = (err as Error).message
  }
}

onMounted(async () => {
  await Promise.all([searchLeagues(), loadTargets()])
})

onBeforeUnmount(clearRunPolling)
</script>

<template>
  <main class="admin app-container">
    <header class="admin__header">
      <div>
        <p class="eyebrow">Crawler Control</p>
        <h1>ADMIN 동기화 기준 관리</h1>
      </div>
      <div class="header-actions">
        <button type="button" class="icon-btn" aria-label="새로고침" @click="loadTargets">
          <RefreshCw :size="17" />
        </button>
        <button type="button" class="run-btn" :disabled="runStatus === 'loading'" @click="runDailySync">
          <Play :size="16" />
          동기화 실행
        </button>
      </div>
    </header>

    <p v-if="error" class="error">{{ error }}</p>

    <section class="admin-grid">
      <section class="search-panel" aria-label="API-Football 리그 조회">
        <div class="section-title">
          <Search :size="18" />
          <h2>API-Football 리그/시즌 카탈로그</h2>
        </div>
        <div class="search-row">
          <label>
            <span>검색어</span>
            <input v-model="searchText" type="search" placeholder="World Cup, Premier League" @keyup.enter="searchLeagues" />
          </label>
          <label class="id-field">
            <span>리그 ID</span>
            <input v-model="leagueIdText" inputmode="numeric" placeholder="1" @keyup.enter="searchLeagues" />
          </label>
          <button type="button" class="primary-btn" :disabled="searchStatus === 'loading'" @click="searchLeagues">
            <Search :size="16" />
            DB 조회
          </button>
          <button
            type="button"
            class="secondary-btn"
            :disabled="catalogSyncStatus === 'loading'"
            @click="syncApiFootballCatalog"
          >
            <RefreshCw :size="16" />
            카탈로그 최신화
          </button>
        </div>
        <p v-if="catalogSyncResult" class="sync-note">
          API {{ catalogSyncResult.api_count }}건 확인 · {{ catalogSyncResult.synced_count }}건 저장 · DB 총 {{ catalogSyncResult.catalog_count }}건
        </p>

        <div class="league-list">
          <article v-for="league in leagues" :key="league.external_id" class="league-row">
            <div class="league-main">
              <img v-if="league.logo_url" :src="league.logo_url" alt="" />
              <div>
                <strong>{{ league.name }}</strong>
                <span>{{ league.external_id }} · {{ league.type }} · {{ league.country.name ?? '-' }}</span>
              </div>
            </div>
            <div class="season-pills" aria-label="시즌 선택">
              <button
                v-for="season in league.seasons"
                :key="season.year"
                type="button"
                :class="{ selected: selectedLeague?.external_id === league.external_id && selectedSeason?.year === season.year }"
                @click="resetSelection(league, season)"
              >
                {{ season.year }}
                <small v-if="season.current">현재</small>
              </button>
            </div>
          </article>
          <div v-if="searchStatus === 'ok' && leagues.length === 0" class="empty">조회 결과가 없습니다.</div>
        </div>
      </section>

      <aside class="target-editor" aria-label="크롤링 target 저장">
        <div class="section-title">
          <DatabaseZap :size="18" />
          <h2>Target 저장</h2>
        </div>
        <div class="selected-box">
          <span>선택</span>
          <strong v-if="selectedLeague && selectedSeason">
            {{ selectedLeague.name }} · {{ selectedSeason.year }}
          </strong>
          <strong v-else>시즌을 선택하세요</strong>
        </div>

        <div class="option-list">
          <label><input v-model="options.include_details" type="checkbox" /> 경기 상세</label>
          <label><input v-model="options.include_players" type="checkbox" /> 선수 스탯</label>
          <label><input v-model="options.include_standings" type="checkbox" /> 순위</label>
          <label>
            <span>Fixture 제한</span>
            <input v-model="options.fixture_limit" inputmode="numeric" placeholder="비워두면 전체" />
          </label>
        </div>

        <button type="button" class="save-btn" :disabled="!selectedLeague || !selectedSeason" @click="saveTarget">
          <Plus :size="16" />
          크롤링 대상 저장
        </button>
      </aside>
    </section>

    <section class="targets" aria-label="저장된 크롤링 대상">
      <div class="section-title">
        <Check :size="18" />
        <h2>저장된 크롤링 대상</h2>
        <span>{{ activeTargets.length }} active / {{ inactiveTargets.length }} inactive</span>
      </div>
      <div class="target-table">
        <div class="target-head">
          <span>상태</span>
          <span>리그</span>
          <span>시즌</span>
          <span>옵션</span>
          <span>제한</span>
          <span></span>
        </div>
        <div v-for="target in targets" :key="target.id" class="target-row">
          <button type="button" class="toggle" :class="{ off: !target.is_active }" @click="toggleTarget(target)">
            {{ target.is_active ? 'ACTIVE' : 'OFF' }}
          </button>
          <span>{{ displayLeagueName(target) }} <small>#{{ target.league.external_id }}</small></span>
          <strong>{{ target.season_year }}</strong>
          <span class="option-tags">
            <em v-if="target.include_details">상세</em>
            <em v-if="target.include_players">선수</em>
            <em v-if="target.include_standings">순위</em>
          </span>
          <span>{{ target.fixture_limit ?? '전체' }}</span>
          <button type="button" class="delete-btn" aria-label="삭제" @click="removeTarget(target)">
            <Trash2 :size="16" />
          </button>
        </div>
        <div v-if="targetStatus === 'ok' && targets.length === 0" class="empty">아직 저장된 target이 없습니다.</div>
      </div>
    </section>

    <section class="plan" aria-label="워커 실행 계획">
      <div class="section-title">
        <DatabaseZap :size="18" />
        <h2>워커 실행 계획</h2>
      </div>
      <pre>{{ JSON.stringify(plan, null, 2) }}</pre>
      <div v-if="activeRun" class="run-monitor">
        <div class="run-monitor__head">
          <strong>{{ activeRun.worker_name }} · {{ activeRun.status }}</strong>
          <span>{{ runProgressText }}</span>
        </div>
        <div class="progress-track" aria-label="워커 진행도">
          <div class="progress-fill" :style="{ width: `${runProgressPercent}%` }"></div>
        </div>
        <ol class="run-logs">
          <li v-for="line in activeRun.logs" :key="`${line.ts}-${line.message}`">
            <time>{{ new Date(line.ts).toLocaleTimeString('ko-KR') }}</time>
            <span>{{ line.message }}</span>
          </li>
        </ol>
        <pre v-if="runResult" class="run-result">{{ runResult }}</pre>
      </div>
    </section>
  </main>
</template>

<style scoped>
.admin {
  height: calc(100vh - var(--header-height));
  overflow-y: auto;
  padding-block: 24px 56px;
}
.admin__header,
.header-actions,
.section-title,
.search-row,
.league-main,
.target-head,
.target-row {
  display: flex;
  align-items: center;
}
.admin__header {
  justify-content: space-between;
  gap: 18px;
  margin-bottom: 18px;
}
.eyebrow {
  margin: 0 0 4px;
  color: var(--color-muted);
  font-size: 12px;
  text-transform: uppercase;
}
h1,
h2 {
  margin: 0;
}
h1 {
  font-size: 28px;
}
h2 {
  font-size: 15px;
}
.header-actions,
.section-title,
.search-row {
  gap: 10px;
}
.section-title {
  margin-bottom: 14px;
}
.section-title span {
  margin-left: auto;
  color: var(--color-muted);
  font-size: 12px;
}
.admin-grid {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 340px;
  gap: 16px;
  align-items: start;
}
.search-panel,
.target-editor,
.targets,
.plan {
  border: 1px solid var(--color-border);
  border-radius: 8px;
  background: var(--color-card);
  padding: 16px;
}
.targets,
.plan {
  margin-top: 16px;
}
label {
  display: grid;
  gap: 6px;
  color: var(--color-muted);
  font-size: 12px;
}
input {
  height: 36px;
  border: 1px solid var(--color-border);
  border-radius: 6px;
  background: var(--color-bg);
  color: var(--color-fg);
  padding: 0 10px;
}
.search-row label {
  flex: 1;
}
.search-row .id-field {
  flex: 0 0 120px;
}
button {
  border: 1px solid var(--color-border);
  border-radius: 6px;
  background: var(--color-bg);
  cursor: pointer;
}
button:disabled {
  cursor: not-allowed;
  opacity: 0.55;
}
.primary-btn,
.secondary-btn,
.run-btn,
.save-btn,
.icon-btn {
  height: 36px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding-inline: 12px;
}
.primary-btn,
.save-btn {
  background: #0f766e;
  border-color: #0f766e;
  color: white;
}
.secondary-btn {
  background: #111827;
  border-color: #111827;
  color: white;
}
.run-btn {
  background: #1d4ed8;
  border-color: #1d4ed8;
  color: white;
}
.icon-btn {
  width: 36px;
  padding: 0;
}
.league-list {
  display: grid;
  gap: 10px;
  margin-top: 14px;
}
.sync-note {
  margin: 10px 0 0;
  color: var(--color-muted);
  font-size: 12px;
}
.league-row {
  display: grid;
  grid-template-columns: 260px minmax(0, 1fr);
  gap: 14px;
  padding: 12px;
  border: 1px solid var(--color-border);
  border-radius: 8px;
  background: var(--color-bg);
}
.league-main {
  gap: 10px;
  min-width: 0;
}
.league-main img {
  width: 34px;
  height: 34px;
  object-fit: contain;
}
.league-main div {
  min-width: 0;
}
.league-main strong,
.league-main span {
  display: block;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.league-main span,
.target-row small {
  color: var(--color-muted);
  font-size: 12px;
}
.season-pills {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
.season-pills button {
  min-width: 72px;
  height: 30px;
  padding-inline: 8px;
}
.season-pills .selected {
  border-color: #0f766e;
  background: #0f766e;
  color: white;
}
.season-pills small {
  margin-left: 4px;
  font-size: 10px;
}
.selected-box {
  display: grid;
  gap: 6px;
  padding: 12px;
  border: 1px solid var(--color-border);
  border-radius: 8px;
  background: var(--color-bg);
}
.selected-box span {
  color: var(--color-muted);
  font-size: 12px;
}
.option-list {
  display: grid;
  gap: 12px;
  margin-block: 14px;
}
.option-list label:has(input[type='checkbox']) {
  display: flex;
  align-items: center;
  gap: 8px;
  color: var(--color-fg);
  font-size: 14px;
}
.target-table {
  display: grid;
  gap: 6px;
}
.target-head,
.target-row {
  display: grid;
  grid-template-columns: 90px minmax(200px, 1fr) 90px minmax(190px, 260px) 80px 40px;
  gap: 10px;
  align-items: center;
}
.target-head {
  color: var(--color-muted);
  font-size: 12px;
  padding-inline: 8px;
}
.target-row {
  min-height: 44px;
  padding: 8px;
  border: 1px solid var(--color-border);
  border-radius: 8px;
  background: var(--color-bg);
}
.toggle {
  height: 28px;
  border-color: #0f766e;
  color: #0f766e;
  font-size: 12px;
  font-weight: 700;
}
.toggle.off {
  border-color: var(--color-border);
  color: var(--color-muted);
}
.option-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
.option-tags em {
  padding: 3px 7px;
  border-radius: 999px;
  background: var(--color-card-hover);
  font-style: normal;
  font-size: 12px;
}
.delete-btn {
  width: 32px;
  height: 32px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  color: #b91c1c;
}
.empty,
.error {
  padding: 14px;
  border-radius: 8px;
  color: var(--color-muted);
}
.error {
  margin-bottom: 14px;
  border: 1px solid #fecaca;
  background: #fef2f2;
  color: #b91c1c;
}
pre {
  max-height: 320px;
  overflow: auto;
  margin: 0;
  padding: 14px;
  border-radius: 8px;
  background: #0b1020;
  color: #e5e7eb;
  font-size: 12px;
  line-height: 1.5;
}
.run-result {
  margin-top: 12px;
}
.run-monitor {
  margin-top: 12px;
  padding: 14px;
  border: 1px solid var(--color-border);
  border-radius: 8px;
  background: var(--color-bg);
}
.run-monitor__head {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 10px;
  font-size: 13px;
}
.run-monitor__head span {
  color: var(--color-muted);
}
.progress-track {
  height: 10px;
  overflow: hidden;
  border-radius: 999px;
  background: var(--color-card-hover);
}
.progress-fill {
  height: 100%;
  min-width: 2px;
  border-radius: inherit;
  background: #0f766e;
  transition: width 180ms ease;
}
.run-logs {
  display: grid;
  gap: 6px;
  max-height: 260px;
  overflow: auto;
  margin: 12px 0 0;
  padding: 0;
  list-style: none;
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
  font-size: 12px;
  line-height: 1.45;
}
.run-logs li {
  display: grid;
  grid-template-columns: 96px minmax(0, 1fr);
  gap: 8px;
}
.run-logs time {
  color: var(--color-muted);
}
@media (max-width: 980px) {
  .admin-grid,
  .league-row {
    grid-template-columns: 1fr;
  }
  .target-head {
    display: none;
  }
  .target-row {
    grid-template-columns: 90px 1fr;
  }
  .target-row > *:nth-child(n+3) {
    grid-column: 2;
  }
}
</style>
