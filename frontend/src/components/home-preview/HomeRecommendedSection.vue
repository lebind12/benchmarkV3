<script setup lang="ts">
import BroadcastPickerButton from '@/components/common/BroadcastPickerButton.vue'
import { slugFromId } from '@/lib/league-colors'
import { RouterLink } from 'vue-router'
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { ArrowRight, ChevronLeft, ChevronRight, Clock3, Info, RotateCw, ShieldAlert } from 'lucide-vue-next'
import PreviewTeam from '@/components/home-preview/PreviewTeam.vue'
import MatchPreviewBody from '@/components/home-preview/MatchPreviewBody.vue'
import { getHomeRecommendations, getHomePreviewDocument } from '@/lib/api/homePreview'
import type { HomeRecommendations } from '@/lib/api/homeRecommendationsSchema'
import { toStoredPreviewView, type HomePreviewDocument } from '@/lib/api/homePreviewDocument'
import type { MatchPreviewView } from '@/lib/api/previewView'
import '@/styles/home-preview.css'

const isDevelopment = import.meta.env.DEV
const replayParams = import.meta.env.DEV ? new URLSearchParams(window.location.search) : null
const replayDateValue = replayParams?.get('previewDate') ?? ''
const replayDate = /^\d{4}-\d{2}-\d{2}$/.test(replayDateValue) ? replayDateValue : undefined
const replayFixtureId = Number(replayParams?.get('fixtureId'))
const scrollPage = ref<HTMLElement | null>(null)
const recommendationResponse = ref<HomeRecommendations | null>(null)
const recommendationsLoading = ref(true)
const recommendationsError = ref(false)
/**
 * 저장 문서(`preview_dev`) 상태. 조회 중과 오류를 **문서 없음과 구분**한다.
 *
 * - `loading`: 아직 응답이 없다.
 * - `ready`: 표시할 저장 문서가 있다.
 * - `none`: 이 경기에 저장 문서가 없다. 안내 문구 하나만 보여준다.
 * - `failed`: 조회 오류. 문서 없음으로 바꾸지 않고 다시 확인을 제공한다.
 */
const documentState = ref<'loading' | 'ready' | 'none' | 'failed'>('loading')
const storedDocument = ref<HomePreviewDocument | null>(null)
const storedView = ref<MatchPreviewView | null>(null)
const index = ref(0)
let recommendationRequest: AbortController | undefined
let documentRequest: AbortController | undefined
let documentId = 0
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
  try { const value = await getHomeRecommendations(current.signal, replayDate); if (current === recommendationRequest && !current.signal.aborted) { recommendationResponse.value = value; index.value = Math.max(0, value.items.findIndex(row => row.fixture_id === replayFixtureId)) } }
  catch { if (!current.signal.aborted && current === recommendationRequest) recommendationsError.value = true }
  finally { if (current === recommendationRequest) recommendationsLoading.value = false }
}
/**
 * 이 경기의 최신 공개 저장 문서를 읽는다.
 *
 * 경기를 바꾸면 앞 경기의 본문을 **먼저 비우고** 새 응답만 받는다. 늦게 도착한 앞
 * 경기 응답은 순번이 달라 무시하므로 새 경기 본문을 덮지 않는다. 첫 진입에서도
 * 기본 선택 경기의 문서를 바로 읽으므로 별도 선택 클릭이 필요 없다.
 */
async function loadDocument() {
  documentRequest?.abort()
  const id = ++documentId
  storedDocument.value = null
  storedView.value = null
  documentState.value = 'loading'
  const fixtureId = selectedRow.value?.fixture_id
  if (!fixtureId) { documentState.value = 'none'; return }
  documentRequest = new AbortController()
  const current = documentRequest
  try {
    const value = await getHomePreviewDocument(fixtureId, current.signal)
    if (id !== documentId || selectedRow.value?.fixture_id !== value.fixture_id || current.signal.aborted) return
    storedDocument.value = value
    if (value.status === 'available') {
      storedView.value = toStoredPreviewView(value)
      documentState.value = 'ready'
    } else {
      documentState.value = 'none'
    }
  } catch {
    if (id === documentId && !current.signal.aborted) documentState.value = 'failed'
  }
}
watch(() => selectedRow.value?.fixture_id, () => { loadDocument() })
/**
 * 문서가 없을 때의 **단일 안내**. 시각 분기는 서버가 정한 `absence` 하나만 읽는다.
 *
 * - `upcoming_overdue`(킥오프까지 6시간 이하): 아직 생성되지 않았다는 문제 안내.
 *   실제 실패 기록이 없으므로 생성 실패로 단정하지 않는다.
 * - `upcoming`(6시간 초과 미래): 기본 생성 시점 안내.
 * - `past`(킥오프 시각 이후): 앞으로 생성될 예정이라고 표현하지 않는다.
 */
const absenceNotice = computed(() => {
  const state = storedDocument.value?.absence?.state ?? 'upcoming'
  if (state === 'upcoming_overdue') {
    return { title: '경기 시작이 6시간 이내로 다가왔지만 프리뷰가 아직 생성되지 않았습니다.', body: null }
  }
  if (state === 'past') {
    return { title: '이 경기의 저장된 프리뷰가 없습니다.', body: null }
  }
  return { title: '이 경기의 저장된 프리뷰가 없습니다.', body: '킥오프 6시간 이내의 마지막 정기 수집에서 프리뷰를 생성합니다.' }
})
function formatTime(value: string | null | undefined) { return value ? new Intl.DateTimeFormat('ko-KR', { timeZone: 'Asia/Seoul', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hour12: false }).format(new Date(value)) : '확인 시각 없음' }
function choose(next: number) { if (matchRows.value.length) index.value = (next + matchRows.value.length) % matchRows.value.length }
const statusLabel = (m: { state: string }) => m.state === 'ongoing' ? '진행 중 · 저장 기준' : '경기 예정'
const touchStart = ref<number | null>(null)
function swipe(event: TouchEvent) { const end = event.changedTouches[0]?.clientX; if (touchStart.value !== null && end !== undefined && Math.abs(end - touchStart.value) > 60) choose(index.value + (end < touchStart.value ? 1 : -1)); touchStart.value = null }
let revealFrame = 0
let motionPreference: MediaQueryList | undefined
const revealed = new WeakMap<HTMLElement, number>()
/**
 * 스크롤 진입에 따라 각 섹션을 점차 선명하게 한다.
 *
 * 저장 본문은 공통 `MatchPreviewBody`를 그대로 쓰므로 그 안의 `.mpv-section`을 홈 컨테이너
 * 범위에서 같은 규칙으로 대상에 넣는다(공통 본문 파일은 고치지 않는다). 한 번 선명해진
 * 값은 최대값으로 유지되어 위로 되돌아가도 다시 흐려지지 않는다.
 */
function updateReveals() {
  revealFrame = 0
  const root = scrollPage.value
  if (!root) return
  const bounds = { top: 0, height: window.innerHeight }
  root.querySelectorAll<HTMLElement>('.hp-reveal, .hp-stored-document .mpv-section').forEach(element => {
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
  recommendationRequest?.abort(); documentRequest?.abort(); documentId++
  document.removeEventListener('scroll', scheduleReveal, true)
  cancelAnimationFrame(revealFrame)
  motionPreference?.removeEventListener('change', scheduleReveal)
  window.removeEventListener('resize', scheduleReveal)
})
watch([() => selectedRow.value?.fixture_id, storedView], async () => { await nextTick(); scheduleReveal() })
</script>

<template>
  <section ref="scrollPage" class="hp-page hp-live-section" data-testid="home-preview-real">
    <div class="hp-container">
      <header class="hp-heading">
        <div><p class="hp-date">{{ dateLabel }} <span>한국 시간</span></p><h1>오늘의 매치</h1></div>
        <div class="hp-heading-actions">
          <BroadcastPickerButton :fixture-id="selectedRow?.fixture_id" :league-slug="slugFromId(selectedRow?.competition.external_id)" :match-label="selectedRow ? `${selectedRow.home.name} 대 ${selectedRow.away.name}` : undefined" />
          <RouterLink to="/fixtures" class="hp-text-link">전체 경기 <ArrowRight :size="16" /></RouterLink>
        </div>
      </header>
      <p v-if="isDevelopment" class="hp-freshness"><RouterLink to="/home/single-call/1557445" data-testid="single-call-review-link">이전 1회 호출 실험 보기 · 과거 파일 →</RouterLink></p>
      <p v-if="replayDate" class="hp-freshness" data-testid="local-replay-date">로컬 재현 · {{ replayDate }}</p>
      <details class="hp-freshness"><summary>경기 자료 시점</summary><p>경기 상태 기준 {{ formatTime(recommendationResponse?.as_of) }} KST · 6시간 간격 수집</p></details>
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
          <div class="hp-preview-backdrop" aria-hidden="true"></div>
        <section class="hp-preview" :key="`preview-${match.id}`" aria-labelledby="preview-heading" data-testid="selected-preview" :data-fixture-id="match.id">
          <header class="hp-section-head hp-reveal"><h2 id="preview-heading">경기 전 프리뷰</h2><RouterLink :to="{ name: 'fixture-detail', params: { externalId: match.id } }" class="hp-action hp-detail-link" data-testid="preview-detail-link">경기 상세 보기<ArrowRight :size="15" /></RouterLink></header>

          <!-- 저장 문서가 있을 때만 저장 시각과 생성 설명을 보여준다. 문서가 없을 때는 아래
               단일 안내만 남겨 생성 예정 문구와 자료 시점 설명이 겹치지 않게 한다. -->
          <template v-if="documentState === 'ready'">
            <p class="hp-freshness">경기 시작 전 6시간 이내의 마지막 정기 수집에서 한 번 생성됩니다.</p>
            <p v-if="storedDocument?.saved_at" class="hp-generation-time" data-testid="preview-generation-time"><Clock3 :size="14" />저장 프리뷰 {{ formatTime(storedDocument.saved_at) }} KST 저장</p>
          </template>

          <div v-if="documentState === 'loading'" class="hp-preview-empty" role="status" data-testid="stored-document-loading">
            <Clock3 :size="32" />
            <h3>저장된 프리뷰를 불러오는 중입니다</h3>
          </div>
          <div v-else-if="documentState === 'failed'" class="hp-preview-empty" role="status" data-testid="stored-document-error">
            <ShieldAlert :size="32" />
            <h3>저장된 프리뷰를 불러오지 못했습니다</h3>
            <p>잠시 후 저장된 프리뷰를 다시 확인해주세요.</p>
            <button class="hp-action" @click="loadDocument()"><RotateCw :size="15" />다시 확인</button>
          </div>
          <div v-else-if="documentState === 'none'" class="hp-preview-empty" role="status" data-testid="stored-document-absent">
            <Clock3 :size="32" />
            <h3>{{ absenceNotice.title }}</h3>
            <p v-if="absenceNotice.body">{{ absenceNotice.body }}</p>
          </div>
          <div v-else-if="storedView" class="hp-stored-document" data-testid="stored-preview-document">
            <MatchPreviewBody :key="`stored-${storedDocument?.run_id}`" :preview="storedView" />
          </div>
        </section>
        </div>
      </template>
      <section v-else class="hp-empty"><Clock3 :size="36" /><h2>{{ recommendationsLoading ? '추천 경기를 불러오는 중입니다' : recommendationsError ? '추천 경기를 불러오지 못했습니다' : '아직 추천할 경기가 없습니다' }}</h2><p>{{ recommendationsError ? '저장된 경기 목록을 다시 확인해주세요.' : '예정 경기가 준비되면 이곳에서 확인할 수 있습니다.' }}</p><button v-if="recommendationsError" class="hp-action" @click="loadRecommendations">다시 확인</button><RouterLink to="/fixtures" class="hp-text-link">전체 일정 확인 <ArrowRight :size="16" /></RouterLink></section>
    </div>
  </section>
</template>
<style scoped>
.hp-heading { flex-wrap: wrap; }
.hp-heading-actions { display: flex; align-items: center; gap: 12px; margin-left: auto; }
.hp-generation-time { display: flex; align-items: center; gap: 8px; margin: 16px 0; color: var(--color-muted); font-size: 12px; }
.hp-live-section { height: auto; overflow: visible; }
.hp-live-section .hp-container { padding: 18px 0 28px; }
</style>
