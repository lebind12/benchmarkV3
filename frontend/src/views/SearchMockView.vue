<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { ArrowUp, ArrowUpRight, Search, SlidersHorizontal, RotateCcw, ChartNoAxesColumnIncreasing, Users, GitCompareArrows, LoaderCircle } from 'lucide-vue-next'

type Scenario = 'ranking' | 'players' | 'comparison' | 'clarification' | 'no_matches' | 'data_unavailable' | 'unsupported' | 'limited' | 'failed' | 'unconnected'
const query = ref('')
const queryInput = ref<HTMLTextAreaElement | null>(null)
let inputObserver: ResizeObserver | undefined
let inputWidth = 0
function resizeInput() {
  const input = queryInput.value
  if (!input) return
  const currentHeight = input.getBoundingClientRect().height
  input.style.transition = 'none'
  input.style.height = 'auto'
  const maxHeight = 182
  const contentHeight = input.scrollHeight
  input.style.height = `${currentHeight}px`
  // Measure without a transition, then animate from the currently displayed height.
  void input.offsetHeight
  input.style.transition = ''
  input.style.height = `${Math.min(contentHeight, maxHeight)}px`
  input.style.overflowY = contentHeight > maxHeight ? 'auto' : 'hidden'
}
watch(query, async () => { await nextTick(); resizeInput() })
onMounted(() => {
  resizeInput()
  inputObserver = new ResizeObserver(entries => {
    const width = entries[0]?.contentRect.width ?? 0
    if (width !== inputWidth) { inputWidth = width; resizeInput() }
  })
  if (queryInput.value) inputObserver.observe(queryInput.value)
  void document.fonts.ready.then(resizeInput)
})
onBeforeUnmount(() => { inputObserver?.disconnect(); cancelSearch() })
function moveLight(event: PointerEvent) {
  if (event.pointerType === 'touch') return
  const form = event.currentTarget as HTMLFormElement
  const bounds = form.getBoundingClientRect()
  form.style.setProperty('--light-x', `${event.clientX - bounds.left}px`)
  form.style.setProperty('--light-y', `${event.clientY - bounds.top}px`)
}
const isSearching = ref(false)
const loadingMessages = [
  '기록을 찾고 있어요',
  '궁금한 기록까지, 잠시만요',
  '검색이 진행 중이에요',
  '조금만 더 기다려 주세요',
  '아직 검색 중이에요',
  '기다려 주셔서 고마워요',
]
const loadingMessageIndex = ref(0)
const longSearchPreview = ref(false)
const resultVersion = ref(0)
let searchTimer: ReturnType<typeof setTimeout> | undefined
let messageTimer: ReturnType<typeof setInterval> | undefined
function cancelSearch() {
  clearTimeout(searchTimer)
  clearInterval(messageTimer)
  searchTimer = undefined
  messageTimer = undefined
  isSearching.value = false
}
function beginSearch(value: Scenario, selectedMetric = '도움') {
  cancelSearch()
  editing.value = false
  loadingMessageIndex.value = 0
  isSearching.value = true
  messageTimer = setInterval(() => {
    loadingMessageIndex.value = (loadingMessageIndex.value + 1) % loadingMessages.length
  }, 2800)
  // Simulate latency only for this UI mock; no API request is made.
  searchTimer = setTimeout(() => {
    scenario.value = value
    rankingMetric.value = selectedMetric
    resultVersion.value += 1
    cancelSearch()
  }, longSearchPreview.value ? 18000 : 900)
}
const submitted = ref('')
const scenario = ref<Scenario | null>(null)
const season = ref('2026/27')
const rankingMetric = ref('도움')
const editing = ref(false)
const examples = [
  { icon: ChartNoAxesColumnIncreasing, label: '기록으로 찾기', question: '이번 시즌 EPL 도움 순위 알려줘', scenario: 'ranking' as const },
  { icon: Users, label: '조건으로 좁히기', question: 'EPL에서 900분 이상 뛰고 10골 이상 넣은 선수', scenario: 'players' as const },
  { icon: GitCompareArrows, label: '두 팀 비교하기', question: '리버풀과 첼시의 리그 득점·실점 비교', scenario: 'comparison' as const },
]
const states: { value: Scenario; label: string }[] = [
  { value: 'ranking', label: '순위' }, { value: 'players', label: '선수 목록' }, { value: 'comparison', label: '비교' },
  { value: 'clarification', label: '조건 확인' }, { value: 'no_matches', label: '0건' },
  { value: 'data_unavailable', label: '미수집' }, { value: 'unsupported', label: '미지원' },
  { value: 'limited', label: '조회 제한' }, { value: 'failed', label: '오류' },
]
// Layout fixtures only. These are deliberately not represented as verified football statistics.
const players = [
  { name: '예시 선수 A', team: '예시 팀 A', minutes: 1080, goals: 12, assists: 8 },
  { name: '예시 선수 B', team: '예시 팀 B', minutes: 990, goals: 11, assists: 6 },
  { name: '예시 선수 C', team: '예시 팀 C', minutes: 945, goals: 10, assists: 5 },
]
const isResults = computed(() => ['ranking', 'players', 'comparison'].includes(scenario.value ?? ''))
const metric = computed(() => scenario.value === 'players' ? '득점' : rankingMetric.value)
const notice = computed(() => {
  const messages: Partial<Record<Scenario, { title: string; text: string }>> = {
    no_matches: { title: '조건에 맞는 결과가 없어요', text: '출전 시간이나 득점 조건을 넓혀 다시 검색해 보세요. 수집된 기록 안에서 일치하는 결과가 없는 상태입니다.' },
    data_unavailable: { title: '아직 수집되지 않은 기록이에요', text: '이 대회·시즌의 기록이 준비되지 않았습니다. 기록이 없다는 뜻은 아니며, 0으로 표시하지 않습니다.' },
    unsupported: { title: '이 정보는 검색 범위에 없어요', text: '저장된 축구 기록을 검색할 수 있습니다. 실시간 기록, 시장가치와 보관 범위 밖 시즌은 제공하지 않습니다.' },
    limited: { title: '잠시 후 다시 검색해 주세요', text: '조회 한도에 도달했습니다. 입력한 질문과 조건은 그대로 유지됩니다.' },
    failed: { title: '검색 결과를 불러오지 못했어요', text: '잠시 후 다시 시도해 주세요. 입력한 질문과 조건은 그대로 유지됩니다.' },
    unconnected: { title: '입력한 질문을 확인했어요', text: '자유로운 질문을 입력할 수 있는 화면 목업입니다. 실제 검색은 아직 연결되지 않았어요. 아래 예시 질문으로 결과 화면을 살펴보세요.' },
  }
  return scenario.value ? messages[scenario.value] : undefined
})
function submit() {
  if (!query.value.trim() || isSearching.value) return
  submitted.value = query.value.trim()
  beginSearch(examples.find(item => item.question === submitted.value)?.scenario ?? 'unconnected')
}
function preview(value: Scenario, question?: string, selectedMetric = '도움') {
  query.value = question ?? (value === 'clarification' ? '이번 시즌 잘한 선수 알려줘' : examples.find(item => item.scenario === value)?.question ?? query.value)
  submitted.value = query.value || '검색 상태 미리보기'
  beginSearch(value, selectedMetric)
}
function chooseMetric(value: string) {
  preview('ranking', `이번 시즌 EPL ${value} 순위`, value)
}
function reset() { cancelSearch(); scenario.value = null; query.value = ''; submitted.value = ''; editing.value = false }
</script>

<template>
  <main class="search-page" :class="{ 'has-search': scenario || isSearching }">
    <div class="search-content">
      <div class="page-top"><span class="mock-label">자연어 검색 <span>목업</span></span><button v-if="scenario || isSearching" class="reset" @click="reset"><RotateCcw :size="14" /> 새 검색</button></div>

      <section class="search-intro" aria-labelledby="search-heading">
        <div class="search-symbol" aria-hidden="true"><Search :size="27" :stroke-width="1.6" /></div>
        <h1 id="search-heading">궁금한 축구 기록,<br v-if="!scenario && !isSearching" /> 말하듯 검색하세요.</h1>
        <p v-if="!scenario && !isSearching">선수부터 경기까지. 조건을 더하면 원하는 기록에 가까워집니다.</p>
      </section>

      <form class="query-form" :class="{ 'is-searching': isSearching }" :aria-busy="isSearching" @submit.prevent="submit" @pointermove="moveLight">
        <Search class="query-icon" :size="21" :stroke-width="1.7" aria-hidden="true" />
        <label class="sr-only" for="football-question">궁금한 축구 기록</label>
        <textarea id="football-question" ref="queryInput" v-model="query" :readonly="isSearching" maxlength="500" rows="1" placeholder="어떤 축구 기록이 궁금하세요?" @keydown.enter.exact.prevent="!$event.isComposing && submit()" />
        <button class="submit" type="submit" :disabled="!query.trim() || isSearching" aria-label="검색하기"><LoaderCircle v-if="isSearching" class="search-spinner" :size="20" /><ArrowUp v-else :size="22" /></button>
      </form>
      <p class="search-hint">저장된 데이터 기준으로 검색합니다. 실시간 기록은 제공하지 않습니다.</p>

      <section v-if="!isSearching && (!scenario || scenario === 'unconnected')" class="examples" aria-label="예시 질문">
        <button v-for="item in examples" :key="item.scenario" @click="preview(item.scenario, item.question)"><component :is="item.icon" :size="19" /><span class="example-label">{{ item.label }}</span><span class="example-question">{{ item.question }}<ArrowUpRight :size="16" /></span></button>
      </section>

      <Transition name="search-feedback" mode="out-in">
      <section v-if="isSearching" key="searching" class="response loading-response" role="status" aria-live="polite">
        <div class="loading-caption"><span class="loading-wave" aria-hidden="true"><i></i><i></i><i></i></span><div><div class="loading-message"><Transition name="loading-copy" mode="out-in"><strong :key="loadingMessageIndex">{{ loadingMessages[loadingMessageIndex] }}</strong></Transition></div><p>예시 검색 과정을 보여주고 있습니다.</p></div></div>
        <div class="loading-skeleton" aria-hidden="true"><span></span><span></span><span></span></div>
      </section>
      <section v-else-if="scenario" :key="resultVersion" class="response" aria-label="검색 응답" aria-live="polite">
        <p class="fixture-note">화면 확인용 예시입니다. 수치·대상·기준 시각은 실제 조회 결과가 아닙니다.</p>
        <template v-if="isResults || scenario === 'clarification' || scenario === 'no_matches'">
          <div class="conditions"><span>{{ season }}</span><span>프리미어리그</span><template v-if="scenario === 'players' || scenario === 'no_matches'"><span>출전 900분 이상</span><span>10골 이상</span></template><button :aria-expanded="editing" @click="editing = !editing"><SlidersHorizontal :size="13" /> 조건 수정</button></div>
          <form v-if="editing" class="condition-editor" @submit.prevent="editing = false"><label for="search-season">시즌</label><select id="search-season" v-model="season"><option>2026/27</option><option>2025/26</option></select><span>시즌 변경은 화면 예시에만 적용됩니다.</span><button type="submit">적용</button></form>
        </template>

        <div v-if="scenario === 'clarification'" class="clarify"><h2>어떤 기록으로 살펴볼까요?</h2><p>‘잘한 선수’를 판단할 기록을 선택해 주세요.</p><div><button @click="chooseMetric('득점')">득점</button><button @click="chooseMetric('도움')">도움</button></div></div>

        <template v-else-if="isResults">
          <div class="result-heading"><h2>{{ scenario === 'comparison' ? '리버풀과 첼시의 기록 비교' : scenario === 'players' ? '조건에 맞는 선수' : `${metric} 순위` }}</h2><span>{{ scenario === 'comparison' ? '2개 팀' : '3명' }}</span></div>
          <p class="result-description">{{ scenario === 'comparison' ? '같은 시즌의 리그 기록을 나란히 비교합니다.' : `선수별 시즌 합계 기준 · ${metric} 내림차순` }}</p>
          <div class="table-wrap">
            <table v-if="scenario !== 'comparison'"><caption class="sr-only">{{ metric }} 기준 선수 예시 결과</caption><thead><tr><th scope="col">순위</th><th scope="col">선수 / 소속팀</th><th scope="col">출전 시간</th><th scope="col">{{ metric }}</th></tr></thead><tbody><tr v-for="(player, index) in players" :key="player.name"><td class="rank">{{ index + 1 }}</td><td><strong>{{ player.name }}</strong><small>{{ player.team }}</small></td><td>{{ player.minutes.toLocaleString() }}<small class="unit">분</small></td><td class="metric">{{ metric === '득점' ? player.goals : player.assists }}</td></tr></tbody></table>
            <table v-else><caption class="sr-only">리버풀과 첼시 비교 예시</caption><thead><tr><th scope="col">기록</th><th scope="col">리버풀</th><th scope="col">첼시</th></tr></thead><tbody><tr><th scope="row">득점</th><td class="metric">24</td><td class="metric">20</td></tr><tr><th scope="row">실점</th><td>10</td><td>12</td></tr><tr><th scope="row">경기 수</th><td>10</td><td>10</td></tr></tbody></table>
          </div>
          <div class="result-foot"><span>예시 기준 시각 2026. 10. 25. 12:00 KST</span><span>일부 기록 미수집</span></div>
          <p class="coverage-note">수집된 기록만 표시한 예시입니다. 미수집 기록은 순위·집계에서 제외됩니다. 상세 링크는 실제 데이터 연결 후 제공됩니다.</p>
        </template>

        <div v-else-if="notice" class="notice"><Search :size="23" aria-hidden="true" /><h2>{{ notice.title }}</h2><p>{{ notice.text }}</p><button v-if="scenario === 'failed' || scenario === 'limited'" @click="submit">다시 시도</button><button v-else-if="scenario === 'no_matches'" @click="editing = true">조건 수정</button></div>
      </section>
      </Transition>

      <details class="preview-tools"><summary>목업 상태 살펴보기</summary><p>실제 검색 연결 전, 각 응답 화면을 확인할 수 있습니다.</p><label class="long-search-option"><input v-model="longSearchPreview" type="checkbox" /> 긴 검색 미리보기 (18초)</label><div><button v-for="state in states" :key="state.value" :aria-pressed="scenario === state.value" @click="preview(state.value)">{{ state.label }}</button></div></details>
    </div>
  </main>
</template>

<style scoped>
.search-page { position: relative; isolation: isolate; height: calc(100dvh - var(--header-height)); overflow-y: auto; padding: 30px 24px 40px; box-sizing: border-box; --search-accent: #5846af; --search-soft: #e9e3fa; --glass: rgb(255 255 255 / 40%); --glass-border: rgb(255 255 255 / 78%); background: radial-gradient(ellipse at 18% 26%, #d4ddfa 0%, transparent 53%), radial-gradient(ellipse at 85% 56%, #dfd3f6 0%, transparent 49%), radial-gradient(ellipse at 48% 94%, #cce9ea 0%, transparent 52%), #edf1f8; }
.search-page::before { content: ''; position: absolute; z-index: -1; inset: 0; pointer-events: none; background: linear-gradient(125deg, transparent 25%, rgb(255 255 255 / 32%) 25.1%, transparent 55%); }
.search-content { position: relative; }
.search-content { max-width: 880px; margin: 0 auto; }
.page-top { display: flex; align-items: center; justify-content: space-between; min-height: 24px; font-size: 13px; }
.mock-label { font-weight: 650; color: var(--color-muted); }
.mock-label span { margin-left: 8px; padding: 3px 7px; border: 1px solid var(--color-border); border-radius: 5px; font-size: 11px; font-weight: 400; }
.reset { display: inline-flex; align-items: center; gap: 6px; border: 0; background: none; color: var(--color-muted); cursor: pointer; }
.search-intro { margin: 65px 0 30px; text-align: center; }
.search-symbol { display: inline-flex; padding: 13px; border-radius: 18px; background: var(--search-soft); color: var(--search-accent); margin-bottom: 18px; }
h1 { font-size: clamp(28px, 3.5vw, 40px); font-weight: 720; line-height: 1.4; letter-spacing: -1.7px; margin: 0; }
.search-intro p { color: var(--color-muted); margin: 16px 0 0; font-size: 14px; }
.query-form { --light-x: 50%; --light-y: 0px; position: relative; display: flex; align-items: flex-end; gap: 14px; padding: 12px 14px 12px 22px; border: 1px solid var(--glass-border); border-radius: 25px; background: var(--glass); backdrop-filter: blur(28px) saturate(150%); -webkit-backdrop-filter: blur(28px) saturate(150%); box-shadow: inset 0 1px 0 rgb(255 255 255 / 65%), 0 12px 40px rgb(60 65 120 / 9%), 0 2px 5px rgb(60 65 120 / 3%); transition: box-shadow 180ms ease, border-color 180ms ease, background 180ms ease; }
.query-form::before { content: ''; position: absolute; inset: 0; border-radius: inherit; pointer-events: none; background: radial-gradient(240px circle at var(--light-x) var(--light-y), rgb(255 255 255 / 55%), transparent 75%); opacity: 0; transition: opacity 180ms ease; }
.query-form:hover::before { opacity: 1; }
.query-form:focus-within { border-color: rgb(139 119 214 / 75%); background: rgb(255 255 255 / 54%); box-shadow: inset 0 1px 0 rgb(255 255 255 / 85%), 0 0 0 4px rgb(133 113 204 / 9%), 0 18px 50px rgb(76 65 134 / 13%); }
.query-icon { position: relative; flex-shrink: 0; align-self: flex-start; margin-top: 8px; color: var(--color-muted); transition: color 180ms ease; }
.query-form:focus-within .query-icon { color: var(--search-accent); }
textarea { position: relative; flex: 1; min-width: 0; width: 100%; box-sizing: border-box; border: 0; padding: 0; margin: 6px 0; background: transparent; color: var(--color-fg); resize: none; font: inherit; font-size: 16px; line-height: 26px; height: 26px; min-height: 26px; max-height: 182px; outline: none; overflow-y: hidden; scrollbar-width: thin; transition: height 260ms cubic-bezier(.22, 1, .36, 1); }
textarea::placeholder { color: var(--color-muted); }
.submit { position: relative; display: grid; flex-shrink: 0; place-items: center; width: 38px; height: 38px; background: var(--search-accent); color: white; border: 1px solid rgb(255 255 255 / 25%); border-radius: 50%; box-shadow: inset 0 1px 1px rgb(255 255 255 / 25%), 0 3px 9px rgb(83 65 156 / 18%); cursor: pointer; transition: transform 160ms ease, background 160ms ease; }
.submit:not(:disabled):hover { transform: translateY(-2px); }
.submit:not(:disabled):active { transform: scale(.94); }
.submit:disabled { background: rgb(255 255 255 / 38%); color: var(--color-muted); box-shadow: inset 0 1px 0 rgb(255 255 255 / 60%); cursor: default; }
.search-hint { text-align: center; font-size: 12px; color: var(--color-muted); margin: 14px 0 0; }
.examples { display: grid; grid-template-columns: repeat(3, 1fr); margin-top: 36px; gap: 12px; }
.examples > button { text-align: left; padding: 20px 18px; border: 1px solid var(--glass-border); border-radius: 12px; background: var(--glass); backdrop-filter: blur(18px); -webkit-backdrop-filter: blur(18px); box-shadow: inset 0 1px 0 rgb(255 255 255 / 60%); cursor: pointer; transition: background 180ms ease, transform 180ms ease; }
.examples > button:hover { background: rgb(255 255 255 / 60%); transform: translateY(-3px); }
.examples > button > svg { color: var(--search-accent); margin-bottom: 16px; }
.example-label { display: block; font-size: 12px; color: var(--color-muted); margin-bottom: 7px; }
.example-question { display: flex; justify-content: space-between; gap: 12px; font-size: 14px; font-weight: 600; line-height: 1.65; }
.example-question svg { flex-shrink: 0; margin-top: 4px; color: var(--color-muted); }
.has-search .search-intro { margin: 26px 0 24px; text-align: left; }
.has-search .search-symbol { display: none; }
.has-search h1 { font-size: 26px; letter-spacing: -1px; }
.response { margin-top: 32px; padding: 24px; border: 1px solid var(--glass-border); border-radius: 20px; background: var(--glass); backdrop-filter: blur(24px); -webkit-backdrop-filter: blur(24px); }
.query-form.is-searching { border-color: var(--search-accent); }
.search-spinner { animation: search-spin 1s linear infinite; }
.loading-response { overflow: hidden; }
.loading-caption { display: flex; align-items: center; gap: 16px; }
.loading-caption strong { font-weight: 600; font-size: 15px; }
.loading-message { display: grid; align-items: center; min-height: 24px; }
.loading-message strong { display: block; }
.loading-copy-enter-active { transition: opacity 180ms ease, transform 180ms ease; }
.loading-copy-leave-active { transition: opacity 120ms ease, transform 120ms ease; }
.loading-copy-enter-from { opacity: 0; transform: translateY(5px); }
.loading-copy-leave-to { opacity: 0; transform: translateY(-5px); }
.loading-caption p { color: var(--color-muted); font-size: 12px; margin: 6px 0 0; }
.loading-wave { display: flex; align-items: center; gap: 4px; height: 32px; padding: 0 8px; color: var(--search-accent); }
.loading-wave i { width: 4px; height: 18px; border-radius: 4px; background: currentColor; animation: search-wave 1s ease-in-out infinite; }
.loading-wave i:nth-child(2) { animation-delay: 140ms; }
.loading-wave i:nth-child(3) { animation-delay: 280ms; }
.loading-skeleton { display: grid; gap: 14px; margin-top: 28px; }
.loading-skeleton span { display: block; height: 12px; border-radius: 6px; background: linear-gradient(100deg, var(--search-soft) 20%, var(--glass) 45%, var(--search-soft) 70%); background-size: 220% 100%; animation: search-shimmer 1.5s ease-in-out infinite; }
.loading-skeleton span:nth-child(2) { width: 83%; }
.loading-skeleton span:nth-child(3) { width: 61%; }
.search-feedback-enter-active { transition: opacity 320ms ease, transform 400ms cubic-bezier(.22, 1, .36, 1); }
.search-feedback-leave-active { transition: opacity 140ms ease, transform 140ms ease; }
.search-feedback-enter-from { opacity: 0; transform: translateY(14px); }
.search-feedback-leave-to { opacity: 0; transform: translateY(-6px); }
.response:not(.loading-response) tbody tr { animation: search-row-in 380ms ease both; }
.response tbody tr:nth-child(2) { animation-delay: 65ms; }
.response tbody tr:nth-child(3) { animation-delay: 130ms; }
@keyframes search-spin { to { transform: rotate(360deg); } }
@keyframes search-wave { 0%, 100% { transform: scaleY(.45); opacity: .5; } 50% { transform: scaleY(1); opacity: 1; } }
@keyframes search-shimmer { from { background-position: 150% 0; } to { background-position: -70% 0; } }
@keyframes search-row-in { from { opacity: 0; transform: translateY(7px); } to { opacity: 1; transform: translateY(0); } }
.fixture-note { color: var(--color-muted); font-size: 12px; margin: 0 0 16px; }
.conditions { display: flex; align-items: center; flex-wrap: wrap; gap: 8px; margin-bottom: 26px; }
.conditions > span { padding: 6px 10px; border-radius: 6px; background: var(--color-card); border: 1px solid var(--color-border); font-size: 12px; }
.conditions button { display: inline-flex; align-items: center; gap: 5px; border: 0; color: var(--search-accent); background: none; font-size: 12px; cursor: pointer; padding: 6px; }
.condition-editor { display: flex; flex-wrap: wrap; align-items: center; gap: 12px; margin-bottom: 24px; font-size: 13px; }
.condition-editor select { padding: 6px; border: 1px solid var(--color-border); background: var(--color-bg); border-radius: 5px; color: var(--color-fg); }
.condition-editor > span { color: var(--color-muted); font-size: 12px; }
.result-heading { display: flex; align-items: baseline; gap: 10px; }
h2 { font-size: 20px; letter-spacing: -.6px; font-weight: 700; margin: 0; }
.result-heading > span, .result-description { font-size: 12px; color: var(--color-muted); }
.result-description { margin: 8px 0 20px; }
.table-wrap { overflow-x: auto; }
table { border-collapse: collapse; width: 100%; text-align: left; font-size: 14px; white-space: nowrap; }
thead { color: var(--color-muted); font-size: 12px; background: var(--color-card); }
th { font-weight: 500; }
th, td { padding: 14px 18px; border-bottom: 1px solid var(--color-border); }
td strong { display: block; font-weight: 600; }
td small { display: block; color: var(--color-muted); font-size: 12px; margin-top: 4px; }
td .unit { display: inline; margin-left: 3px; }
.rank { width: 55px; color: var(--color-muted); }
.metric { font-size: 20px; font-weight: 700; color: var(--search-accent); font-variant-numeric: tabular-nums; }
.result-foot { display: flex; flex-wrap: wrap; justify-content: space-between; gap: 8px; margin-top: 15px; color: var(--color-muted); font-size: 11px; }
.coverage-note { font-size: 12px; line-height: 1.7; color: var(--color-muted); margin-top: 12px; }
.notice { text-align: center; padding: 35px 20px; background: var(--color-card); border-radius: 12px; }
.notice > svg { color: var(--color-muted); margin-bottom: 14px; }
.notice p, .clarify p { font-size: 14px; line-height: 1.8; color: var(--color-muted); max-width: 520px; margin: 10px auto 18px; }
.notice button, .clarify button, .condition-editor button { border: 1px solid var(--color-border); background: var(--color-bg); border-radius: 8px; padding: 8px 16px; font-size: 13px; cursor: pointer; }
.clarify { padding: 24px; border: 1px solid var(--color-border); border-radius: 12px; }
.clarify p { margin-left: 0; }
.clarify > div { display: flex; gap: 8px; }
.preview-tools { margin-top: 48px; border-top: 1px solid var(--color-border); padding-top: 16px; color: var(--color-muted); font-size: 12px; }
.preview-tools summary { cursor: pointer; width: fit-content; }
.preview-tools p { margin: 14px 0; }
.long-search-option { display: flex; align-items: center; gap: 7px; margin-bottom: 16px; cursor: pointer; }
.long-search-option input { accent-color: var(--search-accent); }
.preview-tools > div { display: flex; flex-wrap: wrap; gap: 8px; }
.preview-tools button { border: 1px solid var(--color-border); background: var(--color-bg); border-radius: 6px; padding: 6px 10px; cursor: pointer; }
.preview-tools button[aria-pressed='true'] { background: var(--search-soft); color: var(--search-accent); }
.search-page :is(button, select, summary):focus-visible { outline: 2px solid var(--search-accent); outline-offset: 3px; }
:global(html.dark .search-page) { --search-accent: #bcafff; --search-soft: #302a4d; --glass: rgb(24 30 53 / 48%); --glass-border: rgb(194 202 255 / 17%); background: radial-gradient(ellipse at 12% 26%, #253459 0%, transparent 55%), radial-gradient(ellipse at 85% 58%, #3d2c56 0%, transparent 50%), radial-gradient(ellipse at 48% 94%, #183e4b 0%, transparent 50%), #111827; }
:global(html.dark .search-page::before) { opacity: .12; }
:global(html.dark .search-page .query-form) { box-shadow: inset 0 1px 0 rgb(255 255 255 / 12%), 0 12px 40px rgb(0 0 0 / 18%); }
:global(html.dark .search-page .query-form::before) { background: radial-gradient(240px circle at var(--light-x) var(--light-y), rgb(195 177 255 / 12%), transparent 75%); }
:global(html.dark .search-page .query-form:focus-within) { background: rgb(35 38 64 / 65%); border-color: #a394d6; box-shadow: 0 0 0 4px rgb(181 166 255 / 9%), 0 18px 50px rgb(0 0 0 / 22%); }
:global(html.dark .search-page .examples > button) { box-shadow: inset 0 1px 0 rgb(255 255 255 / 9%); }
:global(html.dark .search-page .examples > button:hover) { background: rgb(74 68 105 / 50%); }
:global(html.dark .search-page .submit:disabled) { background: rgb(255 255 255 / 8%); box-shadow: none; }
@media (prefers-reduced-motion: reduce) { .query-form, .query-form::before, .query-icon, .submit, .examples > button, textarea, .search-feedback-enter-active, .search-feedback-leave-active, .loading-copy-enter-active, .loading-copy-leave-active { transition: none; }
  .search-spinner, .loading-wave i, .loading-skeleton span, .response:not(.loading-response) tbody tr { animation: none; } }
:global(html.dark .search-page .submit:not(:disabled)) { color: #171123; }
@media (min-width: 601px) and (max-height: 800px) {
  .search-intro { margin: 28px 0 22px; }
  .search-symbol { padding: 10px; margin-bottom: 12px; }
  h1 { font-size: 34px; }
  .examples { margin-top: 24px; }
}
@media (max-width: 600px) {
  .search-page { padding: 22px 18px 32px; }
  .search-intro { margin-top: 42px; }
  h1 { letter-spacing: -1px; }
  .search-intro p { font-size: 13px; line-height: 1.8; }
  .query-form { padding: 9px 10px 9px 15px; gap: 10px; border-radius: 23px; }
  .response { padding: 18px 12px; }
  textarea { font-size: 15px; }
  .examples { grid-template-columns: 1fr; gap: 10px; margin-top: 28px; }
  .examples > button { display: grid; grid-template-columns: 20px 1fr; column-gap: 12px; padding: 16px; }
  .examples > button > svg { grid-row: span 2; margin: 3px 0 0; }
  .example-label { margin-bottom: 3px; }
  .example-question { font-size: 13px; }
  th, td { padding: 13px 10px; }
  .has-search h1 { font-size: 23px; }
  .search-hint { font-size: 11px; line-height: 1.7; }
}
</style>
