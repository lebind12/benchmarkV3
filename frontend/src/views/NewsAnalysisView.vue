<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { useAuthStore } from '@/stores/auth'
import { ARTICLE_LIMIT, SOURCE_URL_LIMIT, analyzeNews, validateNewsInput, type NewsAnalyzer, type NewsAnalysisResult } from '@/lib/api/news-analysis'

const props = defineProps<{ analyze?: NewsAnalyzer }>()
const auth = useAuthStore()
const allowed = computed(() => auth.verified && auth.user?.is_active === true && (auth.isAdmin || auth.isStreamer))
const article = ref('')
const source = ref('')
const pending = ref(false)
const error = ref('')
const result = ref<NewsAnalysisResult | null>(null)
let generation = 0
let controller: AbortController | null = null
const labels = { linked: '연결됨', ambiguous: '보류 · 동명이인', unresolved: '보류 · 후보 없음' }
const linkedCount = computed(() => result.value?.mentions.filter(item => item.status === 'linked').length ?? 0)
const heldCount = computed(() => (result.value?.mentions.length ?? 0) - linkedCount.value)
function invalidate() { generation++; controller?.abort(); pending.value = false; result.value = null; error.value = '' }
watch([article, source], invalidate, { flush: 'sync' })
onBeforeUnmount(invalidate)
async function submit() {
  if (pending.value || !allowed.value) return
  error.value = validateNewsInput({ article_text: article.value, source_url: source.value })
  if (error.value) return
  result.value = null
  pending.value = true
  const current = ++generation
  controller = new AbortController()
  try {
    const response = await (props.analyze ?? analyzeNews)({ article_text: article.value, source_url: source.value.trim() }, controller.signal)
    if (current === generation) result.value = response
  } catch (err) {
    if (current === generation) error.value = err instanceof Error ? err.message : '분석하지 못했습니다. 잠시 후 다시 시도하세요.'
  } finally { if (current === generation) pending.value = false }
}
</script>

<template>
  <main class="na-page app-container">
    <div v-if="!allowed" class="na-access" role="alert">활성 STREAMER 또는 ADMIN 계정으로 로그인해야 사용할 수 있습니다.</div>
    <div v-else class="na-inner">
      <RouterLink to="/admin" class="na-back">서비스 관리로 돌아가기</RouterLink>
      <header><h1>기사 속 팀과 선수</h1><p>기사에 등장한 이름을 서비스의 팀·선수 정보와 연결해 확인하세요.</p></header>
      <aside class="na-preview"><strong>관리자 전용 분석</strong><span>원문에 등장한 이름과 DB 정보를 대조합니다. 결과를 공개 뉴스로 저장하지 않습니다.</span></aside>
      <div class="na-workspace">
        <section class="na-input" aria-labelledby="input-title">
          <div class="na-section-head"><h2 id="input-title">기사 입력</h2></div>
          <form novalidate @submit.prevent="submit">
            <label for="na-source">출처 URL</label>
            <input id="na-source" v-model="source" type="url" :maxlength="SOURCE_URL_LIMIT" placeholder="https://…" aria-describedby="na-source-help" />
            <small id="na-source-help">HTTP(S) 주소 · 출처 표시용이며 링크의 내용을 가져오지 않습니다.</small>
            <div class="na-between"><label for="na-article">기사 텍스트</label><small>{{ article.length.toLocaleString() }} / 20,000자</small></div>
            <textarea id="na-article" v-model="article" :maxlength="ARTICLE_LIMIT" rows="15" placeholder="분석할 기사 텍스트를 붙여 넣으세요." />
            <p v-if="error" class="na-error" role="alert">{{ error }}</p>
            <button class="na-button na-primary" type="submit" :disabled="pending">{{ pending ? '분석 중…' : error ? '다시 분석하기' : '팀·선수 분석하기' }}</button>
            <p class="na-note">분석은 현재 화면에서만 확인합니다. 새로고침하면 입력과 결과가 사라집니다.</p>
          </form>
        </section>
        <section class="na-output" aria-labelledby="output-title" :aria-busy="pending">
          <div class="na-section-head"><h2 id="output-title">연결 근거</h2><span v-if="result" class="na-count">연결 {{ linkedCount }} · 보류 {{ heldCount }}</span></div>
          <div aria-live="polite" role="status">
            <p v-if="pending" class="na-empty">기사에서 팀과 선수 이름을 확인하고 있습니다.</p>
            <template v-else-if="result">
              <p class="na-result-notice">분석 완료 · 연결 근거를 확인하세요.</p>
              <p v-if="!result.mentions.length" class="na-empty">연결할 대상을 확인하지 못했습니다. 기사에 이름이 포함되어 있는지 확인하세요.</p>
              <article v-for="(item, index) in result.mentions" :key="index" class="na-mention">
                <div class="na-between"><strong>{{ item.mention }}</strong><span :class="['na-state', item.status]">{{ labels[item.status] }}</span></div>
                <blockquote>{{ item.evidence }}</blockquote>
                <p>{{ item.reason }}</p>
                <RouterLink v-if="item.entity" :to="item.entity.detail_path" class="na-detail">{{ item.entity.name }} 상세 보기</RouterLink>
              </article>
              <footer><a :href="result.source_url" target="_blank" rel="noopener noreferrer">입력한 출처 열기</a><p>출처의 내용이나 신뢰성을 검증한 결과가 아닙니다.</p></footer>
            </template>
            <p v-else class="na-empty">기사를 입력하면 원문 구절과 연결 대상을 이곳에서 함께 확인할 수 있습니다.</p>
          </div>
        </section>
      </div>
    </div>
  </main>
</template>

<style scoped>
.na-page{height:calc(100vh - var(--header-height));overflow-y:auto;color:var(--color-fg);padding-block:24px 48px}.na-inner{max-width:1280px;margin:auto}.na-back,.na-detail,footer a{color:#2563eb;font-size:13px;text-decoration:underline;text-underline-offset:3px}header{margin:22px 0}h1{font-size:29px;font-weight:750;letter-spacing:-1px;margin:0 0 7px}header p{color:var(--color-muted);font-size:14px;margin:0}.na-preview{display:flex;flex-wrap:wrap;gap:8px 16px;padding:12px 15px;border:1px solid #dbeafe;border-radius:7px;background:#eff6ff;color:#1e40af;font-size:13px;margin-bottom:22px}.na-workspace{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);border:1px solid var(--color-border);border-radius:9px;overflow:hidden}.na-input,.na-output{min-width:0;padding:22px}.na-output{border-left:1px solid var(--color-border);background:var(--color-card)}.na-section-head,.na-between{display:flex;justify-content:space-between;align-items:center;gap:10px}.na-section-head{min-height:35px;margin-bottom:20px}h2{font-size:16px;font-weight:700;margin:0}form{display:grid;gap:10px}label{font-size:13px;font-weight:600}input,textarea,select{width:100%;box-sizing:border-box;border:1px solid var(--color-border);border-radius:6px;background:var(--color-bg);color:var(--color-fg);font:inherit;font-size:14px;padding:10px;min-width:0}textarea{resize:vertical;line-height:1.8;min-height:220px}.na-between{margin-top:10px}small,.na-note,.na-count{font-size:11px;color:var(--color-muted);line-height:1.7}.na-button{border:1px solid var(--color-border);border-radius:6px;padding:8px 12px;background:var(--color-bg);color:var(--color-fg);font-size:12px;cursor:pointer}.na-primary{background:#2563eb;color:white;border-color:#2563eb;font-weight:600;margin-top:8px;min-height:42px}.na-button:disabled{opacity:.55;cursor:wait}.na-note{margin:0}.na-error{color:#b91c1c;font-size:13px}.na-empty{font-size:13px;line-height:1.9;color:var(--color-muted);padding:42px 12px;margin:0}.na-result-notice{font-size:12px;color:var(--color-muted);margin:0 0 12px}.na-mention{padding:17px 0;border-bottom:1px solid var(--color-border)}.na-mention .na-between{margin:0}.na-mention strong{font-size:15px}.na-state{font-size:11px;color:#92400e;background:#fef3c7;border-radius:4px;padding:3px 7px}.na-state.linked{background:#dbeafe;color:#1e40af}blockquote{margin:15px 0 10px;padding:10px 12px;border-left:3px solid #93c5fd;background:var(--color-bg);font-size:14px;overflow-wrap:anywhere}.na-mention p,footer p{font-size:12px;line-height:1.7;color:var(--color-muted);margin:8px 0}footer{margin-top:22px;overflow-wrap:anywhere}.na-access{padding:32px}button:focus-visible,input:focus-visible,textarea:focus-visible,select:focus-visible,a:focus-visible{outline:2px solid #2563eb;outline-offset:3px}@media(max-width:760px){.na-workspace{grid-template-columns:minmax(0,1fr)}.na-output{border-left:0;border-top:1px solid var(--color-border)}.na-input,.na-output{padding:18px}h1{font-size:25px}.na-count{white-space:nowrap}}
</style>
