<script setup lang="ts">
import HomePlayerWatchpoints from '@/components/home-preview/HomePlayerWatchpoints.vue'
import HomeExternalPredictions from '@/components/home-preview/HomeExternalPredictions.vue'
import HomeInjurySummary from '@/components/home-preview/HomeInjurySummary.vue'
import { RouterLink } from 'vue-router'
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { ArrowRight, ChevronLeft, ChevronRight, Clock3, Info, RotateCw, ShieldAlert } from 'lucide-vue-next'
import PreviewTeam from '@/components/home-preview/PreviewTeam.vue'
import { getHomeRecommendations, getHomePreview } from '@/lib/api/homePreview'
import type { HomeRecommendations } from '@/lib/api/homeRecommendationsSchema'
import type { HomePreviewResponse } from '@/lib/api/homePreviewResponse'
import { recentMatchResult } from '@/lib/api/homePreviewSchema'
import '@/styles/home-preview.css'

const isDevelopment = import.meta.env.DEV
const scrollPage = ref<HTMLElement | null>(null)
const recommendationResponse = ref<HomeRecommendations | null>(null)
const response = ref<HomePreviewResponse | null>(null)
const recommendationsLoading = ref(true)
const recommendationsError = ref(false)
const previewLoading = ref(false)
const previewError = ref(false)
const index = ref(0)
let recommendationRequest: AbortController | undefined
let previewRequest: AbortController | undefined
let requestId = 0
const matchRows = computed(() => recommendationResponse.value?.items ?? [])
const selectedRow = computed(() => matchRows.value[index.value])
const viewTeam = (team: { external_id: number; name: string }) => ({ id: team.external_id, name: team.name, english: '', color: '#64748b' })
const viewMatch = (row: HomeRecommendations['items'][number]) => ({ id: row.fixture_id, home: viewTeam(row.home), away: viewTeam(row.away), league: row.competition.category === 'epl' ? 'EPL' : row.competition.category === 'ucl' ? 'UCL' : row.competition.category === 'uel' ? 'UEL' : row.competition.name, round: row.competition.round, state: row.state, day: recommendationResponse.value!.display_date, time: new Intl.DateTimeFormat('en-GB', { timeZone: 'Asia/Seoul', hour: '2-digit', minute: '2-digit' }).format(new Date(row.kickoff_at)) })
const selection = computed(() => ({ day: recommendationResponse.value?.display_date ?? '', matches: matchRows.value.map(viewMatch), results: (recommendationResponse.value?.today_results ?? []).map(row => ({ id: row.fixture_id, league: row.competition.name, home: viewTeam(row.home), away: viewTeam(row.away), score: `${row.goals_home} : ${row.goals_away}`, time: new Intl.DateTimeFormat('en-GB', { timeZone: 'Asia/Seoul', hour: '2-digit', minute: '2-digit' }).format(new Date(row.kickoff_at)) })) }))
const match = computed(() => selection.value.matches[index.value])
const dateLabel = computed(() => recommendationResponse.value ? new Intl.DateTimeFormat('ko-KR', { timeZone: 'Asia/Seoul', year: 'numeric', month: 'long', day: 'numeric', weekday: 'long' }).format(new Date(`${recommendationResponse.value.requested_date}T12:00:00+09:00`)) : '오늘')
async function loadRecommendations() {
  recommendationRequest?.abort()
  recommendationRequest = new AbortController()
  const current = recommendationRequest
  recommendationsLoading.value = true; recommendationsError.value = false
  try { const value = await getHomeRecommendations(current.signal); if (current === recommendationRequest && !current.signal.aborted) { recommendationResponse.value = value; index.value = 0 } }
  catch { if (!current.signal.aborted && current === recommendationRequest) recommendationsError.value = true }
  finally { if (current === recommendationRequest) recommendationsLoading.value = false }
}
async function loadPreview() {
  previewRequest?.abort(); const id = ++requestId
  response.value = null; previewError.value = false
  const fixtureId = selectedRow.value?.fixture_id
  if (!fixtureId) { previewLoading.value = false; return }
  previewRequest = new AbortController(); const current = previewRequest
  previewLoading.value = true
  try { const value = await getHomePreview(fixtureId, current.signal); if (id === requestId && selectedRow.value?.fixture_id === value.fixture_id && !current.signal.aborted) response.value = value }
  catch { if (id === requestId && !current.signal.aborted) previewError.value = true }
  finally { if (id === requestId) previewLoading.value = false }
}
watch(() => selectedRow.value?.fixture_id, loadPreview)
const preview = computed(() => response.value?.preview ?? null)
const previewState = computed(() => previewError.value ? 'failed' : response.value?.publication.state ?? 'pending')
const readable = computed(() => preview.value !== null)
const dataItems = [
  { key: 'summary', label: '한줄 전망', target: 'preview-summary' }, { key: 'keyPoints', label: '관전 포인트', target: 'preview-points' },
  { key: 'injuries', label: '부상·출전 정보', target: 'preview-injuries' }, { key: 'homeForm', label: '홈 최근 5경기', target: 'preview-form' }, { key: 'awayForm', label: '원정 최근 5경기', target: 'preview-form' },
  { key: 'ai', label: 'AI 경기 예측', target: 'preview-ai' }, { key: 'external', label: '외부 사이트 전망', target: 'preview-external' }, { key: 'odds', label: '경기 전 배당', target: 'preview-odds' },
] as const
const blocks = computed(() => preview.value ? { summary: preview.value.analysis.summary, keyPoints: preview.value.analysis.key_points, injuries: preview.value.facts.injuries, homeForm: preview.value.facts.home_form, awayForm: preview.value.facts.away_form, ai: preview.value.analysis.ai_prediction, external: preview.value.external.predictions, odds: preview.value.external.odds } : null)
const dataStatus = computed(() => Object.fromEntries(dataItems.map(item => [item.key, blocks.value?.[item.key].status ?? 'missing'])) as Record<string, string>)
const missingData = computed(() => dataItems.filter(item => ['missing', 'unverified', 'error'].includes(dataStatus.value[item.key]!)))
const partialData = computed(() => dataItems.filter(item => dataStatus.value[item.key] === 'partial'))
const dataGaps = computed(() => [...missingData.value, ...partialData.value])
const customNotice = ''
const formData = (side: number) => side ? preview.value?.facts.away_form.data : preview.value?.facts.home_form.data
const defaultNotice = computed(() => dataGaps.value.map(item => ['homeForm', 'awayForm'].includes(item.key) && dataStatus.value[item.key] === 'partial' ? `${item.label}는 5경기 중 ${formData(item.key === 'awayForm' ? 1 : 0)?.matches.length ?? 0}경기만 확인됐습니다.` : `${item.label}: ${dataStatus.value[item.key] === 'error' ? '조회 실패' : dataStatus.value[item.key] === 'unverified' ? '미확인' : '자료 없음'}`).join(' · '))
const visibleSources = computed(() => { if (!preview.value || !blocks.value) return []; const ids = new Set(Object.values(blocks.value).filter(block => block.data !== null).flatMap(block => block.source_ids)); for (const row of preview.value.facts.injuries.data ?? []) for (const id of row.cause?.source_ids ?? []) ids.add(id); return preview.value.sources.filter(source => ids.has(source.id)) })
const availableSources = computed(() => visibleSources.value.map(source => source.title).join(' · '))
const prediction = computed(() => preview.value?.analysis.ai_prediction.data)
function formatTime(value: string | null | undefined) { return value ? new Intl.DateTimeFormat('ko-KR', { timeZone: 'Asia/Seoul', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hour12: false }).format(new Date(value)) : '확인 시각 없음' }
function formRows(side: number) { return (formData(side)?.matches ?? []).map(row => ({ date: new Intl.DateTimeFormat('en-US', { timeZone: 'Asia/Seoul', month: '2-digit', day: '2-digit' }).format(new Date(row.kickoff_at)).replace('/', '.'), opponent: row.opponent, competition: row.competition, score: `${row.goals_for}–${row.goals_against}${row.status === 'AET' ? ' (연장)' : row.status === 'PEN' ? row.penalties ? ` (승부차기 ${row.penalties.for}–${row.penalties.against})` : ' (승부차기 미확인)' : ''}`, result: recentMatchResult(row) })) }
function openData(target: string) { const section = scrollPage.value?.querySelector<HTMLElement>(`#${target}`); section?.scrollIntoView({ block: 'start', behavior: motionPreference?.matches ? 'instant' : 'smooth' }); section?.focus({ preventScroll: true }) }
function choose(next: number) { if (matchRows.value.length) index.value = (next + matchRows.value.length) % matchRows.value.length }
const statusLabel = (m: { state: string }) => m.state === 'ongoing' ? '진행 중 · 저장 기준' : '경기 예정'
const touchStart = ref<number | null>(null)
function swipe(event: TouchEvent) { const end = event.changedTouches[0]?.clientX; if (touchStart.value !== null && end !== undefined && Math.abs(end - touchStart.value) > 60) choose(index.value + (end < touchStart.value ? 1 : -1)); touchStart.value = null }
let revealFrame = 0
let motionPreference: MediaQueryList | undefined
const revealed = new WeakMap<HTMLElement, number>()
function updateReveals() {
  revealFrame = 0
  const root = scrollPage.value
  if (!root) return
  const bounds = { top: 0, height: window.innerHeight }
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
  document.addEventListener('scroll', scheduleReveal, true)
  loadRecommendations()
  updateReveals()
})
onBeforeUnmount(() => {
  recommendationRequest?.abort(); previewRequest?.abort(); requestId++
  document.removeEventListener('scroll', scheduleReveal, true)
  cancelAnimationFrame(revealFrame)
  motionPreference?.removeEventListener('change', scheduleReveal)
  window.removeEventListener('resize', scheduleReveal)
})
watch([() => selectedRow.value?.fixture_id, response], async () => { await nextTick(); scheduleReveal() })
</script>

<template>
  <section ref="scrollPage" class="hp-page hp-live-section" data-testid="home-preview-real">
    <div class="hp-container">
      <header class="hp-heading">
        <div><p class="hp-date">{{ dateLabel }} <span>한국 시간</span></p><h1>오늘의 매치</h1></div>
        <RouterLink to="/fixtures" class="hp-text-link">전체 경기 <ArrowRight :size="16" /></RouterLink>
      </header>
      <p v-if="isDevelopment" class="hp-freshness"><RouterLink to="/home/single-call/1557445" data-testid="single-call-review-link">맨유–본머스 · 1회 호출 결과 보기 →</RouterLink></p>
      <p class="hp-freshness"><Clock3 :size="14" />경기 상태 기준 {{ formatTime(recommendationResponse?.as_of) }} KST · 6시간 간격 갱신</p>
      <div v-if="recommendationResponse?.fallback_reason" class="hp-date-notice"><Info :size="18" /><span>오늘 추천할 경기가 없어 <b>{{ selection.day.replaceAll('-', '.') }}</b>의 가장 가까운 예정 경기를 보여드립니다.</span></div>

      <template v-if="match">
        <section class="hp-hero" aria-label="추천 경기" aria-roledescription="캐러셀" @touchstart="touchStart = $event.touches[0]?.clientX ?? null" @touchend="swipe" @keydown.left.prevent="choose(index - 1)" @keydown.right.prevent="choose(index + 1)">
          <header class="hp-hero__meta"><span>{{ match.league === 'EPL' ? '프리미어리그' : match.league === 'UCL' ? '챔피언스리그' : match.league === 'UEL' ? '유로파리그' : match.league }} <span class="hp-muted">/ {{ match.round }}</span></span><span class="hp-reason">{{ selectedRow?.reason }}</span></header>
          <div class="hp-duel" :key="match.id" data-testid="selected-match">
            <PreviewTeam :team="match.home" side="home"  />
            <div class="hp-versus"><span :class="['hp-status', { 'hp-status--ongoing': match.state === 'ongoing' }]">{{ statusLabel(match) }}</span><strong>vs</strong><time>{{ match.time }}</time><span class="hp-muted">KST 킥오프</span></div>
            <PreviewTeam :team="match.away" side="away"  />
          </div>
          <nav class="hp-carousel" aria-label="추천 경기 전환">
            <button aria-label="이전 추천 경기" :disabled="selection.matches.length < 2" @click="choose(index - 1)"><ChevronLeft :size="21" /></button>
            <p aria-live="polite" aria-atomic="true"><b>{{ index + 1 }}</b> / {{ selection.matches.length }} <span class="hp-sr-only">{{ match.home.name }} 대 {{ match.away.name }}</span></p>
            <button aria-label="다음 추천 경기" :disabled="selection.matches.length < 2" @click="choose(index + 1)"><ChevronRight :size="21" /></button>
          </nav>
        </section>

        <nav class="hp-match-strip" aria-label="추천 경기 목록">
          <button v-for="(item, i) in selection.matches" :key="item.id" :aria-pressed="i === index" :data-fixture-id="item.id" @click="choose(i)">
            <span>{{ item.league }} <span>{{ item.state === 'ongoing' ? '진행 중 · 저장 기준' : item.time }}</span></span>
            <strong>{{ item.home.name }} <small>vs</small> {{ item.away.name }}</strong>
          </button>
        </nav>

        <div class="hp-preview-stage" :style="{ '--home-tint': match.home.color, '--away-tint': match.away.color }">
        <section class="hp-preview" :key="`preview-${match.id}`" aria-labelledby="preview-heading" data-testid="selected-preview" :data-fixture-id="match.id">
          <header class="hp-section-head hp-reveal"><h2 id="preview-heading">경기 전 프리뷰</h2><RouterLink :to="{ name: 'fixture-detail', params: { externalId: match.id } }" class="hp-action hp-detail-link" data-testid="preview-detail-link">경기 상세 보기<ArrowRight :size="15" /></RouterLink></header>
          <div v-if="response?.publication.served === 'previous'" class="hp-state-note" data-testid="previous-publication"><Info :size="18" />{{ response.refresh.state === 'failed' ? '갱신에 실패하여 이전 유효본을 표시합니다.' : '갱신 중이므로 이전 유효본을 표시합니다.' }} 생성 {{ formatTime(response.publication.generated_at) }} · 자료 {{ formatTime(response.publication.as_of) }} KST</div>
          <section v-if="readable && dataGaps.length" class="hp-data-summary" aria-labelledby="data-gap-heading" data-testid="data-gap-summary">
            <header><Info :size="18" /><h3 id="data-gap-heading">자료 확인 현황</h3><span>미제공 {{ missingData.length }} · 일부 제공 {{ partialData.length }}</span></header>
            <ul><li v-for="item in dataGaps" :key="item.key"><button @click="openData(item.target)"><b>{{ item.label }}</b><span>{{ dataStatus[item.key] === 'missing' ? '미제공' : dataStatus[item.key] === 'unverified' ? '미확인' : dataStatus[item.key] === 'error' ? '조회 실패' : ['homeForm', 'awayForm'].includes(item.key) ? `${formData(item.key === 'awayForm' ? 1 : 0)?.matches.length ?? 0} / 5경기` : '일부 제공' }}</span><ArrowRight :size="13" /></button></li></ul>
            <p aria-live="polite">{{ customNotice.trim() || defaultNotice }}</p>
          </section>
          <div v-if="!readable" class="hp-preview-empty" role="status">
            <ShieldAlert v-if="previewState === 'failed'" :size="32" /><Clock3 v-else :size="32" />
            <h3>{{ previewLoading ? '저장된 프리뷰를 불러오는 중입니다' : previewState === 'failed' ? '프리뷰를 불러오지 못했습니다' : response?.publication.reason === 'outside_generation_window' ? '킥오프 24시간 전부터 프리뷰를 준비합니다' : previewState === 'unavailable' ? '경기 전 저장된 프리뷰가 없습니다' : '이 경기의 프리뷰를 준비하고 있습니다' }}</h3>
            <p>{{ previewState === 'failed' ? '잠시 후 저장된 프리뷰를 다시 확인해주세요.' : '자료가 준비되면 관전 포인트와 경기 전망을 확인할 수 있습니다.' }}</p>
            <button v-if="previewState !== 'unavailable' && !previewLoading" class="hp-action" @click="loadPreview()"><RotateCw :size="15" />다시 확인</button>
          </div>
          <template v-else>
            <p id="preview-summary" tabindex="-1" class="hp-lead hp-reveal">{{ preview?.analysis.summary.data?.text || '한줄 전망 자료가 없습니다.' }}</p>
            <div class="hp-analysis-grid hp-reveal">
              <article id="preview-points" tabindex="-1" class="hp-points"><h3>관전 포인트</h3><ol v-if="preview?.analysis.key_points.data"><li v-for="(point, i) in preview.analysis.key_points.data" :key="i"><b>{{ point.title }}</b><p>{{ point.description }}</p></li></ol><p v-else class="hp-unavailable">관전 포인트 자료가 없습니다.</p></article>
              <aside id="preview-ai" tabindex="-1" class="hp-prediction"><span>AI 경기 예측</span><p v-if="!prediction" class="hp-unavailable">AI 경기 예측 자료가 없습니다.</p><template v-else><div class="hp-prediction__score"><b>{{ prediction.home_goals }}</b><span>:</span><b>{{ prediction.away_goals }}</b></div><strong>{{ prediction.home_goals === prediction.away_goals ? '무승부 예상' : `${prediction.home_goals > prediction.away_goals ? match.home.name : match.away.name} 우세 예상` }}</strong><p>{{ prediction.reason }}</p></template></aside>
            </div>

            <HomePlayerWatchpoints :preview="preview" />
            <HomeInjurySummary :preview="preview" />

            <section id="preview-form" tabindex="-1" class="hp-form-section hp-reveal"><header class="hp-subhead"><h3>최근 5경기</h3><span>킥오프 이전 완료 경기 · 모든 대회</span></header><div class="hp-form-grid"><article v-for="(team, side) in [match.home, match.away]" :key="team.id" class="hp-form"><header><b>{{ team.name }}</b><div><span v-for="(row, r) in formRows(side)" :key="r" :class="['hp-form-badge', `hp-form-badge--${row.result}`]">{{ row.result }}</span></div></header><p v-if="formRows(side).length === 0" class="hp-unavailable">최근 경기 자료가 없습니다.</p><template v-else><p v-if="formRows(side).length < 5" class="hp-inline-note">확인 가능한 완료 경기 {{ formRows(side).length }}개만 표시합니다.</p><table><caption class="hp-sr-only">{{ team.name }} 최근 5경기</caption><thead><tr><th>날짜</th><th>대회</th><th>상대</th><th>결과</th></tr></thead><tbody><tr v-for="row in formRows(side)" :key="row.date"><td>{{ row.date }}</td><td>{{ row.competition }}</td><td>{{ row.opponent }}</td><td><b>{{ row.score }}</b></td></tr></tbody></table></template></article></div></section>

            <div class="hp-evidence-grid hp-reveal"><HomeExternalPredictions :preview="preview" /><section id="preview-odds" tabindex="-1"><header class="hp-subhead"><h3>경기 전 배당</h3><span>90분 승무패 · Decimal</span></header><p v-if="!preview?.external.odds.data" class="hp-unavailable">이 경기의 경기 전 배당이 없습니다.</p><template v-else><article v-for="(item, i) in preview.external.odds.data" :key="i"><p class="hp-inline-note">{{ item.bookmaker }}</p><div class="hp-odds"><div><span>{{ preview?.fixture.home.name }} 승</span><b>{{ item.home.toFixed(2) }}</b></div><div><span>무승부</span><b>{{ item.draw.toFixed(2) }}</b></div><div><span>{{ preview?.fixture.away.name }} 승</span><b>{{ item.away.toFixed(2) }}</b></div></div><p class="hp-inline-note">제공자 자료 {{ formatTime(preview.external.odds.as_of) }} KST · 수집 {{ formatTime(item.collected_at) }} KST</p></article></template></section></div>
            <iframe v-if="preview?.search_suggestions" title="Google 검색 제안" :srcdoc="preview.search_suggestions.rendered_content" sandbox="allow-popups allow-popups-to-escape-sandbox" style="width:100%;height:150px;border:0" loading="lazy" />
            <iframe v-for="(suggestion, i) in preview?.search_suggestions_extra ?? []" :key="i" :title="`Google 검색 제안 ${i + 2}`" :srcdoc="suggestion.rendered_content" sandbox="allow-popups allow-popups-to-escape-sandbox" style="width:100%;height:150px;border:0" loading="lazy" />
            <footer class="hp-sources hp-reveal"><h3>출처와 자료 시점</h3><p>{{ availableSources || '표시할 출처가 없습니다.' }}</p><ul v-if="visibleSources.some(source => source.url)" class="hp-source-links"><template v-for="source in visibleSources" :key="source.id"><li v-if="source.url"><a :href="source.url" target="_blank" rel="noopener noreferrer">{{ source.title }}</a><span> · 확인 {{ formatTime(source.retrieved_at) }} KST</span></li></template></ul><p>자료 기준 {{ formatTime(preview?.as_of) }} KST / {{ preview?.generated_at ? `생성 ${formatTime(preview.generated_at)} KST` : 'AI 분석 미생성' }}</p></footer>
          </template>
        </section>
        </div>
      </template>
      <section v-else class="hp-empty"><Clock3 :size="36" /><h2>{{ recommendationsLoading ? '추천 경기를 불러오는 중입니다' : recommendationsError ? '추천 경기를 불러오지 못했습니다' : '아직 추천할 경기가 없습니다' }}</h2><p>{{ recommendationsError ? '저장된 경기 목록을 다시 확인해주세요.' : '예정 경기가 준비되면 이곳에서 확인할 수 있습니다.' }}</p><button v-if="recommendationsError" class="hp-action" @click="loadRecommendations">다시 확인</button><RouterLink to="/fixtures" class="hp-text-link">전체 일정 확인 <ArrowRight :size="16" /></RouterLink></section>

      <section class="hp-results" aria-labelledby="results-heading"><header class="hp-subhead"><h2 id="results-heading">오늘 결과</h2><span>저장된 종료 경기</span></header><div v-if="selection.results.length" class="hp-results__list"><article v-for="result in selection.results" :key="result.id"><span>{{ result.league }} · 종료</span><strong>{{ result.home.name }} <b>{{ result.score }}</b> {{ result.away.name }}</strong><small>{{ result.time }} KST</small></article></div><p v-else class="hp-inline-note">아직 저장된 종료 경기가 없습니다.</p></section>

    </div>
  </section>
</template>
<style scoped>
.hp-live-section { height: auto; overflow: visible; }
.hp-live-section .hp-container { padding: 18px 0 28px; }
</style>
