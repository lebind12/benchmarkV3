<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { ArrowLeft, ArrowRight, ChevronLeft, ChevronRight, Clock3, Info, RotateCw, ShieldAlert } from 'lucide-vue-next'
import PreviewTeam from '@/components/home-preview/PreviewTeam.vue'
import { recommendationReason, sampleDay, sampleMatches, selectRecommendations, type Match } from '@/mocks/home-preview/data'
import { buildMockPreview, parsePreviewFile, previewBlocks } from '@/mocks/home-preview/preview'
import type { HomePreview } from '@/lib/api/homePreviewSchema'
import '@/styles/home-preview.css'

const scrollPage = ref<HTMLElement | null>(null)
let revealFrame = 0
let motionPreference: MediaQueryList | undefined
const revealed = new WeakMap<HTMLElement, number>()
function updateReveals() {
  revealFrame = 0
  const root = scrollPage.value
  if (!root) return
  const bounds = root.getBoundingClientRect()
  root.querySelectorAll<HTMLElement>('.hp-reveal').forEach(element => {
    const distance = element.getBoundingClientRect().top - bounds.top
    const progress = motionPreference?.matches ? 1 : Math.min(1, Math.max(0, (bounds.height * .96 - distance) / (bounds.height * .32)))
    // Keep revealed text readable when it leaves the viewport or the user scrolls back.
    const value = Math.max(revealed.get(element) ?? 0, progress)
    revealed.set(element, value)
    element.style.setProperty('--reveal', String(value))
  })
}
function scheduleReveal() {
  if (!revealFrame) revealFrame = requestAnimationFrame(updateReveals)
}
onMounted(() => {
  motionPreference = window.matchMedia('(prefers-reduced-motion: reduce)')
  motionPreference.addEventListener('change', scheduleReveal)
  window.addEventListener('resize', scheduleReveal)
  updateReveals()
})
onBeforeUnmount(() => {
  cancelAnimationFrame(revealFrame)
  motionPreference?.removeEventListener('change', scheduleReveal)
  window.removeEventListener('resize', scheduleReveal)
})
const scenario = ref('normal')
const index = ref(0)
const override = ref('auto')
const recovered = ref(false)
const missingLogo = ref(false)
const scenarioOptions = [
  ['normal', '진행 중 + 오늘 예정'], ['scheduled', '예정 경기만'], ['single', '추천 1개'],
  ['results', '오늘 종료 → 다음 일정'], ['empty', '추천 없음'],
]
const collection = computed(() => {
  const matches = sampleMatches.map(m => ({ ...m }))
  if (scenario.value === 'empty') return []
  if (scenario.value === 'single') return matches.filter(m => m.id === 90001)
  if (scenario.value === 'scheduled') return matches.map(m => m.state === 'ongoing' ? { ...m, state: 'scheduled' as const } : m)
  if (scenario.value === 'results') return matches.map(m => m.day === sampleDay ? { ...m, state: 'finished' as const, score: '1 : 1' } : m)
  return matches
})
const selection = computed(() => selectRecommendations(collection.value, sampleDay))
const match = computed(() => selection.value.matches[index.value])
const previewState = computed(() => recovered.value ? 'ready' : override.value === 'auto' ? match.value?.preview : override.value)
const readable = computed(() => ['ready', 'partial', 'previous'].includes(previewState.value ?? ''))
type DataKey = 'summary' | 'keyPoints' | 'injuries' | 'homeForm' | 'awayForm' | 'ai' | 'external' | 'odds'
type DataStatus = 'available' | 'partial' | 'missing'
const dataItems: { key: DataKey; label: string; target: string; partial?: boolean }[] = [
  { key: 'summary', label: '한줄 전망', target: 'preview-summary' },
  { key: 'keyPoints', label: '관전 포인트', target: 'preview-points' },
  { key: 'injuries', label: '부상·출전 정보', target: 'preview-injuries' },
  { key: 'homeForm', label: '홈 최근 5경기', target: 'preview-form', partial: true },
  { key: 'awayForm', label: '원정 최근 5경기', target: 'preview-form', partial: true },
  { key: 'ai', label: 'AI 경기 예측', target: 'preview-ai' },
  { key: 'external', label: '외부 사이트 전망', target: 'preview-external' },
  { key: 'odds', label: '경기 전 배당', target: 'preview-odds' },
]
const dataEdits = reactive<Record<number, Partial<Record<DataKey, DataStatus>>>>({})
const noticeEdits = reactive<Record<number, string>>({})
const importedPreviews = reactive<Record<number, HomePreview>>({})
const jsonDraft = ref('')
const jsonError = ref('')
const preview = computed(() => match.value ? importedPreviews[match.value.id] ?? buildMockPreview(match.value, previewState.value, dataEdits[match.value.id]) : null)
const dataStatus = computed(() => {
  const blocks = preview.value && previewBlocks(preview.value)
  return Object.fromEntries(dataItems.map(item => [item.key, blocks?.[item.key].status ?? 'missing'])) as Record<DataKey, string>
})
const visibleSources = computed(() => {
  if (!preview.value) return []
  const blocks = [...Object.values(preview.value.analysis), ...Object.values(preview.value.facts), ...Object.values(preview.value.external)]
  const ids = new Set(blocks.filter(block => block.data !== null).flatMap(block => block.source_ids))
  return preview.value.sources.filter(source => ids.has(source.id))
})
const availableSources = computed(() => visibleSources.value.map(source => source.title).join(' · '))
const prediction = computed(() => preview.value?.analysis.ai_prediction.data)
const formData = (side: number) => side ? preview.value?.facts.away_form.data : preview.value?.facts.home_form.data
function showJson() {
  if (preview.value) { jsonDraft.value = JSON.stringify(preview.value, null, 2); jsonError.value = '' }
}
function applyJson() {
  if (!match.value) return
  try { importedPreviews[match.value.id] = parsePreviewFile(jsonDraft.value, match.value.id); jsonError.value = '' }
  catch { jsonError.value = 'JSON 형식·경기 ID·출처·자료 상태·경기 전 시각을 확인해주세요. 기존 화면은 유지됩니다.' }
}
function formatTime(value: string | null | undefined) {
  return value ? new Intl.DateTimeFormat('ko-KR', { timeZone: 'Asia/Seoul', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hour12: false }).format(new Date(value)) : '확인 시각 없음'
}
function sourceTitle(ids: string[]) { return preview.value?.sources.filter(source => ids.includes(source.id)).map(source => source.title).join(' · ') ?? '' }
const missingData = computed(() => dataItems.filter(item => ['missing', 'unverified', 'error'].includes(dataStatus.value[item.key])))
const partialData = computed(() => dataItems.filter(item => dataStatus.value[item.key] === 'partial'))
const dataGaps = computed(() => [...missingData.value, ...partialData.value])
const defaultNotice = computed(() => {
  const parts: string[] = []
  for (const [status, message] of [['missing', '자료가 없습니다.'], ['unverified', '자료가 아직 확인되지 않았습니다.'], ['error', '자료를 불러오지 못했습니다.']]) {
    const items = missingData.value.filter(item => dataStatus.value[item.key] === status)
    if (items.length) parts.push(`${items.map(item => item.label).join(' · ')} ${message}`)
  }
  for (const item of partialData.value) parts.push(['homeForm', 'awayForm'].includes(item.key) ? `${item.label}는 5경기 중 ${formData(item.key === 'awayForm' ? 1 : 0)?.matches.length ?? 0}경기만 확인됐습니다.` : `${item.label} 자료가 일부만 있습니다.`)
  return parts.join(' ')
})
const customNotice = computed({
  get: () => noticeEdits[match.value?.id ?? 0] ?? '',
  set: (value: string) => { if (match.value) noticeEdits[match.value.id] = value },
})
function setDataStatus(key: DataKey, event: Event) {
  if (!match.value) return
  delete importedPreviews[match.value.id]
  dataEdits[match.value.id] ??= {}
  dataEdits[match.value.id]![key] = (event.target as HTMLSelectElement).value as DataStatus
}
function resetData() {
  if (!match.value) return
  delete importedPreviews[match.value.id]
  delete dataEdits[match.value.id]
  delete noticeEdits[match.value.id]
}
function openData(target: string) {
  const section = scrollPage.value?.querySelector<HTMLElement>(`#${target}`)
  if (!section) return
  section.scrollIntoView({ block: 'start', behavior: motionPreference?.matches ? 'instant' : 'smooth' })
  section.focus({ preventScroll: true })
}
watch([() => match.value?.id, previewState, dataStatus], async () => { await nextTick(); scheduleReveal() })
const statusLabel = (m: Match) => m.state === 'ongoing' ? '진행 중 · 저장 기준' : '경기 예정'
function choose(next: number) {
  const count = selection.value.matches.length
  if (!count) return
  index.value = (next + count) % count
  override.value = 'auto'
  recovered.value = false
}
watch(scenario, () => { index.value = 0; override.value = 'auto'; recovered.value = false })
watch(override, () => { recovered.value = false })
function formRows(side: number) {
  return (formData(side)?.matches ?? []).map(row => ({
    date: new Intl.DateTimeFormat('en-US', { timeZone: 'Asia/Seoul', month: '2-digit', day: '2-digit' }).format(new Date(row.kickoff_at)).replace('/', '.'),
    opponent: row.opponent, competition: row.competition, score: `${row.goals_for}–${row.goals_against}`,
    result: row.goals_for > row.goals_against ? '승' : row.goals_for < row.goals_against ? '패' : '무',
  }))
}
const touchStart = ref<number | null>(null)
function swipe(event: TouchEvent) {
  const start = touchStart.value
  const end = event.changedTouches[0]?.clientX
  if (start !== null && end !== undefined && Math.abs(end - start) > 60) choose(index.value + (end < start ? 1 : -1))
  touchStart.value = null
}
</script>

<template>
  <main ref="scrollPage" class="hp-page" data-testid="home-preview-mock" @scroll.passive="scheduleReveal">
    <div class="hp-container">
      <div class="hp-mock-notice">
        <span><b>디자인 목업</b> 일정·기록·분석·배당은 모두 가상 샘플입니다.</span>
        <details class="hp-tools">
          <summary>평가 도구</summary>
          <div class="hp-tools__body">
            <label>경기 상황<select v-model="scenario" aria-label="경기 상황"><option v-for="[value, label] in scenarioOptions" :key="value" :value="value">{{ label }}</option></select></label>
            <label>프리뷰 상태<select v-model="override" aria-label="프리뷰 상태"><option value="auto">경기별 기본 상태</option><option value="ready">준비 완료</option><option value="partial">일부 자료 부족</option><option value="pending">준비 중</option><option value="failed">불러오기 실패</option><option value="previous">이전 유효본</option></select></label>
            <label class="hp-check"><input v-model="missingLogo" type="checkbox" />로고 없음</label>
            <fieldset v-if="match" class="hp-data-controls"><legend>선택 경기 자료</legend>
              <label v-for="item in dataItems" :key="item.key">{{ item.label }}<select :aria-label="`${item.label} 자료 상태`" :value="dataStatus[item.key]" @change="setDataStatus(item.key, $event)"><option value="available">있음</option><option v-if="item.partial" value="partial">일부 있음 (3/5)</option><option value="missing">없음</option></select></label>
            </fieldset>
            <label v-if="match">누락 안내 문구<textarea v-model="customNotice" aria-label="누락 안내 문구" rows="3" placeholder="비워두면 누락 항목에 맞춰 자동 표시" /></label>
            <button v-if="match" class="hp-action" @click="resetData">자료 설정 초기화</button>
            <details v-if="match" class="hp-json-tools"><summary @click="showJson">프리뷰 JSON</summary><label>프리뷰 JSON<textarea v-model="jsonDraft" aria-label="프리뷰 JSON" rows="10" /></label><button class="hp-action" @click="applyJson">JSON 적용</button><p v-if="jsonError" role="alert">{{ jsonError }}</p></details>
          </div>
        </details>
      </div>

      <header class="hp-heading">
        <div><p class="hp-date">2026년 10월 25일 일요일 <span>한국 시간</span></p><h1>오늘의 매치</h1></div>
        <RouterLink to="/fixtures" class="hp-text-link">전체 경기 <ArrowRight :size="16" /></RouterLink>
      </header>
      <p class="hp-freshness"><Clock3 :size="14" />자료 기준 10.25 19:20 KST · 6시간 간격 갱신 · 실시간 정보가 아닙니다.</p>
      <div v-if="selection.day !== sampleDay" class="hp-date-notice"><Info :size="18" /><span>오늘 추천할 경기가 없어 <b>{{ selection.day.replaceAll('-', '.') }}</b>의 가장 가까운 예정 경기를 보여드립니다.</span></div>

      <template v-if="match">
        <section class="hp-hero" aria-label="추천 경기" aria-roledescription="캐러셀" @touchstart="touchStart = $event.touches[0]?.clientX ?? null" @touchend="swipe" @keydown.left.prevent="choose(index - 1)" @keydown.right.prevent="choose(index + 1)">
          <header class="hp-hero__meta"><span>{{ match.league === 'EPL' ? '프리미어리그' : match.league === 'UCL' ? '챔피언스리그' : match.league === 'UEL' ? '유로파리그' : match.league }} <span class="hp-muted">/ {{ match.round }}</span></span><span class="hp-reason">{{ recommendationReason(match) }}</span></header>
          <div class="hp-duel" :key="match.id" data-testid="selected-match">
            <PreviewTeam :team="match.home" side="home" :no-logo="missingLogo" />
            <div class="hp-versus"><span :class="['hp-status', { 'hp-status--ongoing': match.state === 'ongoing' }]">{{ statusLabel(match) }}</span><strong>vs</strong><time>{{ match.time }}</time><span class="hp-muted">KST 킥오프</span></div>
            <PreviewTeam :team="match.away" side="away" :no-logo="missingLogo" />
          </div>
          <nav class="hp-carousel" aria-label="추천 경기 전환">
            <button aria-label="이전 추천 경기" :disabled="selection.matches.length < 2" @click="choose(index - 1)"><ChevronLeft :size="21" /></button>
            <p aria-live="polite" aria-atomic="true"><b>{{ index + 1 }}</b> / {{ selection.matches.length }} <span class="hp-sr-only">{{ match.home.name }} 대 {{ match.away.name }}</span></p>
            <button aria-label="다음 추천 경기" :disabled="selection.matches.length < 2" @click="choose(index + 1)"><ChevronRight :size="21" /></button>
          </nav>
        </section>

        <nav class="hp-match-strip" aria-label="추천 경기 목록">
          <button v-for="(item, i) in selection.matches" :key="item.id" :aria-pressed="i === index" @click="choose(i)">
            <span>{{ item.league }} <span>{{ item.state === 'ongoing' ? '진행 중 · 저장 기준' : item.time }}</span></span>
            <strong>{{ item.home.name }} <small>vs</small> {{ item.away.name }}</strong>
          </button>
        </nav>

        <div class="hp-preview-stage" :style="{ '--home-tint': match.home.color, '--away-tint': match.away.color }">
        <section class="hp-preview" :key="`preview-${match.id}`" aria-labelledby="preview-heading" data-testid="selected-preview" :data-fixture-id="match.id">
          <header class="hp-section-head hp-reveal"><h2 id="preview-heading">경기 전 프리뷰</h2></header>
          <div v-if="previewState === 'previous'" class="hp-state-note"><Info :size="18" />최신 프리뷰를 준비하고 있어 이전 유효본을 표시합니다. 생성 10.25 12:00 · 자료 10.25 11:40 KST</div>
          <section v-if="readable && dataGaps.length" class="hp-data-summary" aria-labelledby="data-gap-heading" data-testid="data-gap-summary">
            <header><Info :size="18" /><h3 id="data-gap-heading">자료 확인 현황</h3><span>미제공 {{ missingData.length }} · 일부 제공 {{ partialData.length }}</span></header>
            <ul><li v-for="item in dataGaps" :key="item.key"><button @click="openData(item.target)"><b>{{ item.label }}</b><span>{{ dataStatus[item.key] === 'missing' ? '미제공' : dataStatus[item.key] === 'unverified' ? '미확인' : dataStatus[item.key] === 'error' ? '조회 실패' : ['homeForm', 'awayForm'].includes(item.key) ? `${formData(item.key === 'awayForm' ? 1 : 0)?.matches.length ?? 0} / 5경기` : '일부 제공' }}</span><ArrowRight :size="13" /></button></li></ul>
            <p aria-live="polite">{{ customNotice.trim() || defaultNotice }}</p>
          </section>
          <div v-if="!readable" class="hp-preview-empty" role="status">
            <ShieldAlert v-if="previewState === 'failed'" :size="32" /><Clock3 v-else :size="32" />
            <h3>{{ previewState === 'failed' ? '프리뷰를 불러오지 못했습니다' : '이 경기의 프리뷰를 준비하고 있습니다' }}</h3>
            <p>{{ previewState === 'failed' ? '잠시 후 저장된 프리뷰를 다시 확인해주세요.' : '자료가 준비되면 관전 포인트와 경기 전망을 확인할 수 있습니다.' }}</p>
            <button class="hp-action" @click="recovered = true"><RotateCw :size="15" />다시 확인 <span class="hp-muted">(샘플)</span></button>
          </div>
          <template v-else>
            <p id="preview-summary" tabindex="-1" class="hp-lead hp-reveal">{{ preview?.analysis.summary.data?.text || '한줄 전망 자료가 없습니다.' }}</p>
            <div class="hp-analysis-grid hp-reveal">
              <article id="preview-points" tabindex="-1" class="hp-points"><h3>관전 포인트</h3><ol v-if="preview?.analysis.key_points.data"><li v-for="(point, i) in preview.analysis.key_points.data" :key="i"><b>{{ point.title }}</b><p>{{ point.description }}</p></li></ol><p v-else class="hp-unavailable">관전 포인트 자료가 없습니다.</p></article>
              <aside id="preview-ai" tabindex="-1" class="hp-prediction"><span>AI 경기 예측</span><p v-if="!prediction" class="hp-unavailable">AI 경기 예측 자료가 없습니다.</p><template v-else><div class="hp-prediction__score"><b>{{ prediction.home_goals }}</b><span>:</span><b>{{ prediction.away_goals }}</b></div><strong>{{ prediction.home_goals === prediction.away_goals ? '무승부 예상' : `${prediction.home_goals > prediction.away_goals ? match.home.name : match.away.name} 우세 예상` }}</strong><p>{{ prediction.reason }}</p></template></aside>
            </div>

            <section id="preview-injuries" tabindex="-1" class="hp-injuries hp-reveal"><div><h3>주요 부상·출전 변수</h3><p>확정 결장과 출전 불확실을 구분합니다.</p></div><p v-if="!preview?.facts.injuries.data" class="hp-unavailable hp-injury-empty">부상·출전 정보가 없습니다.</p><p v-else-if="preview.facts.injuries.data.length === 0" class="hp-inline-note">확인된 결장자가 없습니다.</p><template v-else><div v-for="(injury, i) in preview.facts.injuries.data" :key="i" class="hp-injury-item"><span :class="['hp-tag', { 'hp-tag--uncertain': injury.availability === 'doubtful' }]">{{ injury.availability === 'out' ? '확정 결장' : '출전 불확실' }}</span><b>{{ injury.player_name }}</b><span>{{ injury.detail }} · {{ injury.impact }}</span><small>{{ sourceTitle(injury.source_ids) }} · {{ formatTime(preview.facts.injuries.as_of) }} KST</small></div></template></section>

            <section id="preview-form" tabindex="-1" class="hp-form-section hp-reveal"><header class="hp-subhead"><h3>최근 5경기</h3><span>킥오프 이전 완료 경기 · 모든 대회 · 샘플</span></header><div class="hp-form-grid"><article v-for="(team, side) in [match.home, match.away]" :key="team.id" class="hp-form"><header><b>{{ team.name }}</b><div><span v-for="(row, r) in formRows(side)" :key="r" :class="['hp-form-badge', `hp-form-badge--${row.result}`]">{{ row.result }}</span></div></header><p v-if="formRows(side).length === 0" class="hp-unavailable">최근 경기 자료가 없습니다.</p><template v-else><p v-if="formRows(side).length < 5" class="hp-inline-note">확인 가능한 완료 경기 {{ formRows(side).length }}개만 표시합니다.</p><table><caption class="hp-sr-only">{{ team.name }} 최근 5경기 샘플</caption><thead><tr><th>날짜</th><th>대회</th><th>상대</th><th>결과</th></tr></thead><tbody><tr v-for="row in formRows(side)" :key="row.date"><td>{{ row.date }}</td><td>{{ row.competition }}</td><td>{{ row.opponent }}</td><td><b>{{ row.score }}</b></td></tr></tbody></table></template></article></div></section>

            <div class="hp-evidence-grid hp-reveal"><section id="preview-external" tabindex="-1"><header class="hp-subhead"><h3>외부 사이트 전망</h3><span>AI 예측과 별도</span></header><p v-if="!preview?.external.predictions.data" class="hp-unavailable">확인한 외부 전망이 없습니다.</p><template v-else><div v-for="(item, i) in preview.external.predictions.data" :key="i" class="hp-external"><span>{{ sourceTitle([item.source_id]) }}</span><b>{{ item.outlook }}</b><p>{{ item.summary }}</p><small>자료 {{ formatTime(preview.external.predictions.as_of) }} KST</small></div></template></section><section id="preview-odds" tabindex="-1"><header class="hp-subhead"><h3>경기 전 배당</h3><span>90분 승무패 · Decimal</span></header><p v-if="!preview?.external.odds.data" class="hp-unavailable">이 경기의 경기 전 배당이 없습니다.</p><template v-else><article v-for="(item, i) in preview.external.odds.data" :key="i"><p class="hp-inline-note">{{ item.bookmaker }}</p><div class="hp-odds"><div><span>홈승</span><b>{{ item.home.toFixed(2) }}</b></div><div><span>무승부</span><b>{{ item.draw.toFixed(2) }}</b></div><div><span>원정승</span><b>{{ item.away.toFixed(2) }}</b></div></div><p class="hp-inline-note">수집 기준 {{ formatTime(item.collected_at) }} KST</p></article></template></section></div>
            <footer class="hp-sources hp-reveal"><h3>출처와 자료 시점</h3><p>{{ availableSources || '표시할 출처가 없습니다.' }}</p><ul v-if="visibleSources.some(source => source.url)" class="hp-source-links"><template v-for="source in visibleSources" :key="source.id"><li v-if="source.url"><a :href="source.url" target="_blank" rel="noopener noreferrer">{{ source.title }}</a><span> · 확인 {{ formatTime(source.retrieved_at) }} KST</span></li></template></ul><p>자료 기준 {{ formatTime(preview?.as_of) }} KST / 생성 {{ formatTime(preview?.generated_at) }} KST</p></footer>
          </template>
        </section>
        </div>
      </template>
      <section v-else class="hp-empty"><Clock3 :size="36" /><h2>아직 추천할 경기가 없습니다</h2><p>예정 경기가 준비되면 이곳에서 확인할 수 있습니다.</p><RouterLink to="/fixtures" class="hp-text-link">전체 일정 확인 <ArrowRight :size="16" /></RouterLink></section>

      <section class="hp-results" aria-labelledby="results-heading"><header class="hp-subhead"><h2 id="results-heading">오늘 결과</h2><span>저장된 종료 경기 · 샘플</span></header><div v-if="selection.results.length" class="hp-results__list"><article v-for="result in selection.results" :key="result.id"><span>{{ result.league }} · 종료</span><strong>{{ result.home.name }} <b>{{ result.score }}</b> {{ result.away.name }}</strong><small>{{ result.time }} KST</small></article></div><p v-else class="hp-inline-note">아직 저장된 종료 경기가 없습니다.</p></section>
      <footer class="hp-footer"><RouterLink to="/" class="hp-text-link"><ArrowLeft :size="15" />기존 홈</RouterLink><span>샘플 경기의 상세 페이지는 제공하지 않습니다.</span></footer>
    </div>
  </main>
</template>
