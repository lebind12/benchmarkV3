<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, provide, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ArrowRight, Info, ShieldCheck, RefreshCw, CheckCircle2 } from 'lucide-vue-next'
import { managementApiKey, type ManagementApi, type CatalogLeague, type CollectionRun, type CollectionTarget, type TranslationEntry } from '@/lib/api/management'
const props = defineProps<{ api: ManagementApi }>()
const api = props.api
provide(managementApiKey, api)
import TargetsPanel from '@/components/management/TargetsPanel.vue'
import ExecutionPanel from '@/components/management/ExecutionPanel.vue'
import HistoryPanel from '@/components/management/HistoryPanel.vue'
import TranslationsPanel from '@/components/management/TranslationsPanel.vue'
import { retryIds } from '@/components/management/display'
const tabs = [
  { id: 'targets', label: '수집 대상', description: '수집할 리그와 시즌을 관리합니다.' },
  { id: 'execution', label: '수집 실행', description: '선택한 대상의 수집을 실행하고 추적합니다.' },
  { id: 'history', label: '실행 이력', description: '지난 작업의 결과와 로그를 확인합니다.' },
  { id: 'translations', label: '번역 검수', description: '서비스에 사용할 한국어 표기를 검수합니다.' },
] as const
type Tab = typeof tabs[number]['id']
const route = useRoute()
const router = useRouter()
const tab = computed<Tab>(() => tabs.find((item) => item.id === route.query.tab)?.id ?? 'targets')
const catalog = ref<CatalogLeague[]>([])
const targets = ref<CollectionTarget[]>([])
const active = ref<CollectionRun | null>(null)
const runs = ref<CollectionRun[]>([])
const translations = ref<TranslationEntry[]>([])
const selected = ref<number[]>([])
const loading = ref(true)
const error = ref('')
const notice = ref('')
const schedulerEnabled = ref<boolean | undefined>(undefined)
const missingCount = ref(0)
const ready = ref(false)
let poll: ReturnType<typeof setInterval> | null = null
let pollBusy = false
let toastTimer: ReturnType<typeof setTimeout> | null = null
let disposed = false
const focusedRun = computed(() => runs.value.find((run) => run.id === route.query.run) ?? null)
const parent = computed(() => typeof route.query.retry === 'string' ? route.query.retry : null)
const preferredMode = computed(() => runs.value.find((run) => run.id === parent.value)?.mode ?? 'refresh')
function notify(message: string) { notice.value = message; if (toastTimer) clearTimeout(toastTimer); toastTimer = setTimeout(() => { notice.value = '' }, 6500) }
async function setTab(value: Tab) { await router.push({ query: { ...route.query, tab: value } }) }
async function loadRuns() {
  const payload = await api.runs()
  if (disposed) return
  active.value = payload.active; runs.value = payload.items
  // Retain the recovered run when it finishes; keep an explicitly opened past run intact.
  if (active.value && tab.value === 'execution' && typeof route.query.run !== 'string') {
    await router.replace({ query: { ...route.query, run: active.value.id } })
  }
  if (typeof route.query.run === 'string' && !active.value && runs.value.some(run => run.id === route.query.run)) { const detail = await api.run(route.query.run); if (!disposed) runs.value = runs.value.map(run => run.id === detail.id ? detail : run) }
}
function syncPolling() {
  if (poll) { clearInterval(poll); poll = null }
  if (!ready.value || tab.value !== 'execution' || !active.value || error.value) return
  poll = setInterval(async () => {
    if (pollBusy) return
    pollBusy = true
    try { await loadRuns() } catch (err) { error.value = err instanceof Error ? err.message : '작업을 확인하지 못했습니다.'; syncPolling() }
    finally { pollBusy = false }
  }, 2000)
}
async function refresh() {
  error.value = ''
  try {
    const [targetData, catalogData, translationData] = await Promise.all([api.targets(), api.catalog(), api.translations()])
    if (disposed) return
    targets.value = targetData.items; schedulerEnabled.value = targetData.scheduler_enabled; catalog.value = catalogData.items; translations.value = translationData.items; missingCount.value = translationData.missing_count ?? translationData.items.filter(row => !row.name_ko?.trim()).length
    selected.value = selected.value.filter((id) => targets.value.some((row) => row.id === id && row.is_active))
    await loadRuns()
    if (active.value && !selected.value.length) selected.value = active.value.items.map((item) => item.target_id)
    if (parent.value && !selected.value.length) {
      const source = runs.value.find((run) => run.id === parent.value)
      if (source) selected.value = retryIds(source).filter((id) => targets.value.some((row) => row.id === id && row.is_active))
    }
  } catch (err) { error.value = err instanceof Error ? err.message : '관리 데이터를 불러오지 못했습니다.' }
  finally { loading.value = false; syncPolling() }
}
async function executeSelection() { await router.push({ query: { tab: 'execution' } }) }
async function started(run: CollectionRun) { active.value = run; await router.replace({ query: { ...route.query, tab: 'execution', run: run.id } }); syncPolling() }
async function retry(run: CollectionRun) {
  const ids = retryIds(run).filter((id) => targets.value.some((target) => target.id === id && target.is_active))
  if (!ids.length) { notify('다시 실행할 활성 대상이 없습니다. 수집 대상의 활성 상태를 확인하세요.'); return }
  selected.value = ids
  await router.push({ query: { tab: 'execution', retry: run.id } })
  notify('실패·미처리 대상을 선택했습니다. 실행 범위를 확인한 후 시작하세요.')
}
async function retryLoad() { loading.value=true; await refresh() }
watch([tab, () => active.value?.id], syncPolling)
watch(() => route.query.tab, async () => { if (ready.value && !loading.value) { try { await refresh() } catch { /* refresh exposes a recoverable error */ } } })
onMounted(async () => {
  try {
    if (!tabs.some((item) => item.id === route.query.tab)) await router.replace({ query: { ...route.query, tab: 'targets' } })
    ready.value = true; await refresh()
  } catch { loading.value = false; error.value = '관리 화면을 불러오지 못했습니다. 페이지를 새로고침하세요.' }
})
onBeforeUnmount(() => { disposed = true; if (poll) clearInterval(poll); if (toastTimer) clearTimeout(toastTimer) })
</script>
<template>
  <main class="management-page app-container" data-testid="management-page">
    <div class="mm-page-inner">
      <header class="mm-page-header"><div><h1>서비스 관리</h1><p>수집 대상을 관리하고, 작업 결과와 한국어 표기를 확인하세요.</p></div><div class="mm-next-sync"><span class="mm-schedule-dot" /><span>정기 수집 <strong>매일 00 · 06 · 12 · 18시</strong><small>{{ schedulerEnabled === false ? '현재 서버 자동 수집 비활성' : '한국 시간 기준' }}</small></span></div></header>
      <div class="mm-shared-banner"><ShieldCheck :size="18" /><span>수집 설정과 번역 수정은 <strong>전체 서비스에 공통 적용</strong>됩니다.</span><button v-if="active" type="button" class="mm-button mm-button--quiet" @click="setTab('execution')"><span class="mm-live-dot" />수집 진행 중<ArrowRight :size="14" /></button></div>
      <div class="mm-summary-line"><span>활성 대상 <strong>{{ targets.filter((row) => row.is_active).length }}</strong><small>/ {{ targets.length }}</small></span><span>최근 실행 <strong>{{ runs.length }}</strong><small>최근 7일</small></span><span>미번역 <strong>{{ missingCount }}</strong><small>개 이름</small></span></div>
      <nav class="mm-main-tabs" aria-label="관리 하위 탭"><button v-for="item in tabs" :key="item.id" type="button" :class="{ active: tab === item.id }" :aria-current="tab === item.id ? 'page' : undefined" :data-testid="`management-tab-${item.id}`" @click="setTab(item.id)">{{ item.label }}<span v-if="item.id === 'execution' && active" class="mm-live-dot" /></button></nav>
      <div v-if="loading" class="mm-panel mm-loading" role="status"><RefreshCw :size="24" class="mm-spin" />관리 데이터를 불러오고 있습니다.</div>
      <section v-else-if="error" class="mm-panel mm-empty" role="alert"><Info :size="30" /><h2>관리 데이터를 확인하지 못했습니다</h2><p>{{ error }}</p><button class="mm-button mm-button--primary" type="button" @click="retryLoad">다시 불러오기</button></section>
      <template v-else>
        <TargetsPanel v-if="tab === 'targets'" :targets="targets" :catalog="catalog" :selected="selected" @selection="selected = $event" @refresh="refresh" @notify="notify" @execute="executeSelection" />
        <ExecutionPanel v-else-if="tab === 'execution'" :key="parent ?? 'normal'" :targets="targets" :selected="selected" :active="active" :result="focusedRun" :parent="parent" :preferred-mode="preferredMode" @selection="selected = $event" @started="started" @refresh="refresh" @notify="notify" @history="setTab('history')" @retry="retry" />
        <HistoryPanel v-else-if="tab === 'history'" :runs="runs" :active="active" @retry="retry" @execution="setTab('execution')" />
        <TranslationsPanel v-else :translations="translations" @refresh="refresh" @notify="notify" />
      </template>
      <div v-if="notice" class="mm-toast" role="status"><CheckCircle2 :size="18" /><span>{{ notice }}</span><button type="button" aria-label="알림 닫기" @click="notice = ''">×</button></div>
    </div>
  </main>
</template>
<style src="@/styles/management.css"></style>
