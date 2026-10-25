<script setup lang="ts">
import { computed } from 'vue'
import { RouterLink } from 'vue-router'
import PreviewPlayerPhoto from '@/components/home-preview/PreviewPlayerPhoto.vue'
import HomePlayerWatchpoints from '@/components/home-preview/HomePlayerWatchpoints.vue'
import { homePreviewSchema, type HomePreview } from '@/lib/api/homePreviewSchema'
import review from '@/mocks/home-preview/single-call-review.json'
import '@/styles/home-preview.css'

const result = review.result
const base = homePreviewSchema.parse(review.baseline)
const displayNames = new Map(Object.entries(review.display_names))
for (const player of base.facts.injuries.data ?? []) player.player_name = displayNames.get(String(player.player_id)) ?? player.player_name
const teams = [base.fixture.home, base.fixture.away]
const teamName = (id: number) => teams.find(team => team.external_id === id)?.name ?? ''
const injury = (id: number) => base.facts.injuries.data?.find(player => player.player_id === id)
const source = (id: string) => result.source_catalog.find(row => row.id === id)
const safeUrl = (url: string | null | undefined) => url?.startsWith('https://') ? url : undefined
const matchedForecastCount = result.external_forecasts.items.filter(item => item.source_ids.every(id => result.source_catalog.find(s => s.id === id)?.verification === 'original_quote_matched')).length
const summarySourceIds = new Set(result.grounding_links.filter(link => link.path[0] === 'summary').flatMap(link => link.source_ids))
const summarySources = result.source_catalog.filter(source => summarySourceIds.has(source.id))
const elapsedSeconds = Math.round((Date.parse(review.execution.finished_at) - Date.parse(review.execution.started_at)) / 1000)
const checks = new Map(review.source_checks.map(check => [check.id, check]))
const slots = [0, 1].flatMap(rank => teams.map(team => ({ team, rank, pick: result.key_absences.filter(pick => pick.team_id === team.external_id)[rank] })))
const eventLabels: Record<string, string> = { initial: '최초 발생', recurrence: '재발', aggravation: '악화', suspension: '징계', unknown: '사건 구분 미확인' }
const watchPreview = computed<HomePreview>(() => ({ ...base, analysis: { ...base.analysis,
  player_watchpoints: { status: 'available', reason: null, as_of: review.execution.finished_at,
    source_ids: [...new Set(result.player_watchpoints.flatMap(row => row.evidence_ids))],
    data: result.player_watchpoints.map(row => ({ ...row, focus: row.focus as 'season_contribution' | 'scoring_streak' | 'assist_streak' | 'involvement_streak' })),
  },
} }))
function checkLabel(id: string) {
  const check = checks.get(id)
  if (!check) return '원문 미확인'
  if (check.state === 'original_quote_matched') return '원문 인용 확인'
  if (['grounding_linked', 'grounding_attribution'].includes(check.state)) return 'Google 검색 출처 연결'
  if (check.reason === 'missing_grounding_connection') return '검색 메타데이터에서 출처 연결 미확인'
  if (check.state === 'original_fetched') return check.quote_matches?.every(Boolean) ? '인용 확인 · 경기 정합성 추가 확인 필요' : '원문 인용 불일치'
  if (check.http_status) return `원문 접근 실패 · HTTP ${check.http_status}`
  return check.reason === 'unapproved_source_host' ? '현재 수집 허용 목록 밖 · 원문 미확인' : '원문 미확인'
}
</script>

<template>
  <main class="hp-page hp-single-review" data-testid="single-call-review">
    <div class="hp-container">
      <header class="review-heading"><div><p class="hp-date">로컬 실험 · 실제 LLM 응답</p><h1>맨유–본머스 · 1회 호출 결과</h1></div><RouterLink to="/">메인으로</RouterLink></header>
      <p class="review-meta">{{ review.execution.model }} · 모델 요청 {{ review.execution.model_requests }}회(429 실패 1회 + 성공 1회) · 검색 {{ review.execution.search_queries.length }}개 · 성공 응답 {{ elapsedSeconds }}초</p>
      <aside class="review-note" data-testid="review-status"><b>생성 결과 · 출처 대조 완료</b><p>외부 전망 3곳은 Google 검색이 반환한 실제 원문의 인용과 일치했습니다. 부상 근거 2건은 검색 메타데이터에 출처 연결이 없어 발생일을 미검증으로 표시합니다. 본문은 실제 LLM 응답 그대로입니다.</p></aside>
      <section class="review-section"><p class="hp-date">프리미어리그 · 2026시즌 · 10월 25일 23:00 KST</p><h2>{{ base.fixture.home.name }} <span>vs</span> {{ base.fixture.away.name }}</h2><RouterLink :to="`/fixtures/${result.fixture_id}`">경기 상세 보기 →</RouterLink></section>
      <section class="review-section"><h3>경기 전 프리뷰</h3><p class="review-lead" data-testid="single-summary">{{ result.summary.text }}</p><div class="review-claim-sources" data-testid="summary-grounding"><a v-for="source in summarySources" :key="source.id" :href="safeUrl(source.url)" target="_blank" rel="noopener noreferrer">{{ source.title }}</a></div><details class="review-details"><summary>기존 저장본과 비교</summary><p>{{ base.analysis.summary.data?.text }}</p></details></section>
      <section class="review-section"><h3>관전 포인트</h3><ul class="review-points"><li v-for="(point, i) in result.key_points" :key="i">{{ point.text }}</li></ul></section>
      <section class="review-section"><h3>주요 부상·출전 변수</h3><p class="review-meta">발생일·원인은 모델 반환값입니다. 이번 두 선수의 출처는 검색 메타데이터에 연결되지 않아 미검증 상태입니다.</p>
        <div class="review-grid"><b v-for="team in teams" :key="team.external_id">{{ team.name }}</b></div>
        <div class="review-grid">
          <article v-for="slot in slots" :key="`${slot.team.external_id}:${slot.rank}`" class="review-card" :class="{ 'review-empty': !slot.pick }" data-testid="single-absence">
            <template v-if="slot.pick"><div class="review-player"><div><small>{{ injury(slot.pick.player_id)?.availability === 'out' ? 'DB 기준 결장' : 'DB 기준 출전 불확실' }}</small><h4>{{ injury(slot.pick.player_id)?.player_name }}</h4><p>{{ slot.pick.cause ?? '원인 미확인' }}</p></div><PreviewPlayerPhoto :name="injury(slot.pick.player_id)?.player_name ?? ''" :photo-url="injury(slot.pick.player_id)?.photo_url" /></div>
              <p class="review-date" data-testid="single-occurrence">{{ slot.pick.occurred_on ?? slot.pick.occurred_month ?? '정확한 날짜 미확인' }} · {{ eventLabels[slot.pick.event_type] }}</p><p>{{ slot.pick.timing_text }}</p>
              <details class="review-details"><summary>선정 이유·발생 시점 근거</summary><p>{{ slot.pick.selection_reason }}</p><p>{{ slot.pick.date_basis }}</p><div v-for="(evidence, i) in [...slot.pick.cause_evidence, ...slot.pick.timing_evidence]" :key="i" class="review-evidence"><p>{{ evidence.claim }}</p><blockquote>{{ evidence.quote }}</blockquote><a :href="safeUrl(source(evidence.source_id)?.url)" target="_blank" rel="noopener noreferrer">{{ source(evidence.source_id)?.publisher }}</a><small>{{ checkLabel(evidence.source_id) }}</small></div></details>
            </template><span v-else>추가 선정 선수 없음</span>
          </article>
        </div>
      </section>
      <HomePlayerWatchpoints :preview="watchPreview" />
      <section class="review-section"><h3>AI 경기 예측</h3><strong class="review-score">{{ result.ai_prediction.predicted_score }}</strong><p>{{ result.ai_prediction.text }}</p></section>
      <section class="review-section"><h3>외부 사이트 전망</h3><p class="review-meta">모델 제시 {{ result.external_forecasts.items.length }}곳 · 원문 인용 확인 {{ matchedForecastCount }}곳</p><div class="review-forecasts"><article v-for="forecast in result.external_forecasts.items" :key="forecast.publisher" class="review-card" data-testid="single-forecast"><h4>{{ forecast.publisher }} <span>{{ forecast.predicted_score }}</span></h4><p>{{ forecast.summary }}</p><div v-for="evidence in forecast.evidence" :key="evidence.source_id" class="review-evidence"><blockquote>{{ evidence.quote }}</blockquote><a :href="safeUrl(source(evidence.source_id)?.url)" target="_blank" rel="noopener noreferrer">모델이 제시한 출처</a><small>{{ checkLabel(evidence.source_id) }}</small></div></article></div></section>
      <section class="review-section"><h3>경기 전 배당</h3><p class="review-meta">기존 DB 수집본 · 소수 배당</p><div v-for="row in base.external.odds.data ?? []" :key="row.bookmaker" class="review-odds"><b>{{ row.bookmaker }}</b><span>{{ teamName(33) }} 승 <strong>{{ row.home }}</strong></span><span>무승부 <strong>{{ row.draw }}</strong></span><span>{{ teamName(35) }} 승 <strong>{{ row.away }}</strong></span></div></section>
      <section class="review-section"><h3>출처 확인 결과</h3><article v-for="row in result.source_catalog" :key="row.id" class="review-source"><a :href="safeUrl(row.url)" target="_blank" rel="noopener noreferrer">{{ row.title }}</a><p>{{ checkLabel(row.id) }}</p><p v-if="checks.get(row.id)?.resolved_url && checks.get(row.id)?.resolved_url !== row.url">실제 연결: {{ checks.get(row.id)?.title }}</p></article>
        <iframe v-if="review.search_suggestions" title="Google 검색 제안" :srcdoc="review.search_suggestions" sandbox="allow-popups allow-popups-to-escape-sandbox" class="review-suggestions" />
      </section>
      <details class="review-details"><summary>두 번째 응답 JSON 원문 보기</summary><pre data-testid="single-raw-json">{{ JSON.stringify(review.raw_result, null, 2) }}</pre></details>
      <details class="review-details"><summary>첫 번째 응답 JSON 원문과 비교</summary><pre>{{ JSON.stringify(review.previous_result, null, 2) }}</pre></details>
      <details class="review-details"><summary>실제 검색 쿼리 {{ review.execution.search_queries.length }}개</summary><ul><li v-for="query in review.execution.search_queries" :key="query">{{ query }}</li></ul></details>
    </div>
  </main>
</template>

<style scoped>
.hp-single-review { height: auto; min-height: calc(100dvh - var(--header-height)); overflow: visible; --reveal: 1; }
.review-heading,.review-player { display:flex; justify-content:space-between; align-items:start; gap:16px; }
h1 { font-size:26px; margin-top:8px; } h2 { font-size:26px; margin:12px 0; } h2 span { color:var(--color-muted); font-size:18px; } h4 { font-size:18px; margin:8px 0; } h4 span { float:right; }
a { color:var(--color-fg); text-underline-offset:4px; font-size:12px; } p,li { font-size:14px; line-height:1.9; overflow-wrap:anywhere; }
.review-claim-sources { display:flex; flex-wrap:wrap; gap:10px; margin-top:14px; }
.review-meta { color:var(--color-muted); font-size:12px; margin:12px 0!important; }
.review-note { border:1px solid var(--color-border); padding:18px; border-radius:12px; margin-top:20px; } .review-note p { font-size:12px; margin-top:6px; }
.review-section { border-bottom:1px solid var(--color-border); padding:28px 0; } .review-section h3 { margin-bottom:18px; }
.review-lead { font-size:21px; line-height:1.9; } .review-points { padding-left:20px; } .review-points li { margin-bottom:12px; }
.review-grid { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:14px; margin:16px 0; }
.review-card { padding:22px; border:1px solid var(--color-border); border-radius:12px; min-width:0; }
.review-empty { display:flex; align-items:center; justify-content:center; color:var(--color-muted); border-style:dashed; min-height:100px; }
.review-date { margin:16px 0 8px!important; font-weight:600; } .review-player small { color:var(--color-muted); font-size:11px; }
.review-details { border-top:1px solid var(--color-border); padding:16px 0; margin-top:16px; } summary { cursor:pointer; font-size:12px; color:var(--color-muted); } .review-details p { margin:14px 0; }
.review-evidence { margin-top:16px; } blockquote { font-size:12px; line-height:1.8; margin:10px 0; border-left:2px solid var(--color-border); padding-left:12px; } .review-evidence small { display:block; font-size:11px; color:var(--color-muted); margin:6px 0; }
.review-forecasts { display:grid; gap:14px; } .review-score { font-size:32px; display:block; margin:12px 0; }
.review-odds { display:grid; grid-template-columns:1fr 2fr 1fr 2fr; gap:12px; font-size:12px; padding:14px 0; border-bottom:1px solid var(--color-border); } .review-odds strong { display:block; font-size:17px; margin-top:6px; }
.review-source { padding:14px 0; border-bottom:1px solid var(--color-border); } .review-source p { font-size:12px; color:var(--color-muted); }
.review-suggestions { width:100%; height:150px; border:0; margin-top:16px; } pre { white-space:pre-wrap; overflow-wrap:anywhere; font-size:11px; line-height:1.6; margin-top:20px; }
@media(max-width:600px) { h1,h2 { font-size:20px; } .review-heading { display:block; } .review-heading>a { display:inline-block; margin-top:14px; } .review-lead { font-size:17px; } .review-grid { gap:10px; } .review-card { padding:14px 12px; } .review-player { flex-direction:row; gap:4px; } .review-player>div { min-width:0; } .review-player :deep(.hp-player-photo) { width:46px; height:52px; } .review-player h4 { font-size:15px; } .review-card p { font-size:12px; } .review-odds { grid-template-columns:repeat(3,minmax(0,1fr)); } .review-odds>b { grid-column:1/-1; } }
</style>
