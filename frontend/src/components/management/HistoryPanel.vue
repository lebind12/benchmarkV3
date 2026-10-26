<script setup lang="ts">
import { computed, ref } from 'vue'
import { Search, Clock3, ArrowUpRight, RefreshCw } from 'lucide-vue-next'
import type { CollectionRun, RunStatus } from '@/lib/api/managementTypes'
import { dateTime, dayKey, retryIds, runTotals, statusLabels } from './display'
import ManagementDialog from './ManagementDialog.vue'
import RunDetails from './RunDetails.vue'
import { useManagementApi } from '@/lib/api/management'
const api = useManagementApi()
import { logStatistics } from './logPresentation'
const props = defineProps<{ runs: CollectionRun[]; active: CollectionRun | null }>()
const emit = defineEmits<{ retry: [run: CollectionRun]; execution: [] }>()
const search = ref('')
const status = ref('all')
const from = ref('')
const to = ref('')
const detailId = ref<string | null>(null)
const detail = ref<CollectionRun | null>(null)
const detailLoading = ref(false)
const detailError = ref('')
async function openDetail(run: CollectionRun) {
  detailId.value = run.id; detail.value = null; detailError.value = ''; detailLoading.value = true
  try { const result = await api.run(run.id); if (detailId.value === run.id) detail.value = result }
  catch (err) { if (detailId.value === run.id) detailError.value = err instanceof Error ? err.message : '실행 로그를 불러오지 못했습니다.' }
  finally { if (detailId.value === run.id) detailLoading.value = false }
}
const filtered = computed(() => props.runs.filter((run) => (status.value === 'all' || run.status === status.value) && (!from.value || dayKey(run.started_at) >= from.value) && (!to.value || dayKey(run.started_at) <= to.value) && `${run.id} ${run.actor} ${run.items.map((item) => item.name).join(' ')}`.toLowerCase().includes(search.value.toLowerCase())))
const statistics = computed(() => logStatistics(filtered.value))
const clear = () => { search.value = ''; status.value = 'all'; from.value = ''; to.value = '' }
function retry(run: CollectionRun) { detailId.value = null; emit('retry', run) }
</script>
<template>
  <section class="mm-panel" aria-label="실행 이력 목록">
    <header class="mm-panel-head"><div><h2>실행 이력</h2><p>최근 7일 중 최대 100개 작업의 결과와 처리 로그를 확인하세요.</p></div><span class="mm-badge">{{ runs.length }}개 작업</span></header>
    <div v-if="active" class="mm-inline-banner"><span>현재 수집 중인 작업이 있습니다.</span><button class="mm-button mm-button--quiet" type="button" @click="emit('execution')">진행 상태 보기<ArrowUpRight :size="14" /></button></div>
    <div class="mm-toolbar mm-toolbar--wrap"><label class="mm-search"><Search :size="16" /><input v-model="search" placeholder="리그, 실행자 또는 작업 ID 검색" aria-label="실행 이력 검색" /></label><select v-model="status" aria-label="실행 이력 상태"><option value="all">전체 결과</option><option v-for="key in ['succeeded', 'partial_failed', 'failed', 'cancelled', 'interrupted']" :key="key" :value="key">{{ statusLabels[key as RunStatus] }}</option></select><label class="mm-date-label">시작일<input v-model="from" type="date" aria-label="이력 시작일" /></label><label class="mm-date-label">종료일<input v-model="to" type="date" aria-label="이력 종료일" /></label></div>
    <section class="mm-history-statistics" aria-label="실행 이력 로그 통계"><h3>조회한 작업의 오류·경고 원인</h3><p class="mm-caption">현재 검색·기간·결과 필터 기준 {{ filtered.length }}개 작업 · 로그 발생 건수이며 실패 데이터 건수와 다릅니다.</p><div v-if="statistics.groups.length" class="mm-cause-list"><div v-for="group in statistics.groups" :key="group.code" class="mm-cause-button"><strong>{{ group.title }}</strong><span>오류 {{ group.errors }} · 재시도·경고 {{ group.warnings }}</span><small>{{ group.runs.size }}개 작업 · {{ group.targets.size }}개 작업별 대상</small></div></div><p v-else class="mm-caption">분류 가능한 오류·경고가 없습니다.</p><p v-if="filtered.some(run => run.counts_kind === 'legacy_unknown')" class="mm-caption">기존 실행 통계는 보관된 원문을 분류한 결과입니다. 삭제·생략된 로그와 판별할 수 없는 원인은 포함하지 않습니다.</p><p v-else class="mm-caption">수준·원인 정보 없는 원문 {{ statistics.unknown }}건 제외 · 상세에서 실패 로그와 원문을 확인하세요.</p></section>
    <div class="mm-table-wrap"><table class="mm-table"><thead><tr><th>실행 시각</th><th>수집 대상</th><th>방식 · 실행자</th><th>결과</th><th>처리 내역</th><th></th></tr></thead><tbody><tr v-for="run in filtered" :key="run.id" :data-testid="`history-${run.id}`"><td><strong>{{ dateTime(run.started_at) }}</strong><small>{{ run.id }}</small></td><td><strong>{{ run.items[0]?.name ?? '대상별 정보 미기록' }}</strong><small>{{ run.items.length > 1 ? `외 ${run.items.length - 1}개 대상` : `${run.items[0]?.season ?? ''} 시즌` }}</small></td><td>{{ run.mode === 'initial' ? '최초 수집' : '갱신' }}<small>{{ run.actor }}</small></td><td><span :class="['mm-badge', `mm-badge--${run.status}`]">{{ statusLabels[run.status] }}</span></td><td><span v-if="run.counts_kind === 'legacy_unknown'">대상별 처리 수 미기록</span><span v-else>{{ run.counts_kind ? '처리' : '저장' }} {{ runTotals(run).saved }}</span><small v-if="run.counts_kind !== 'legacy_unknown'">실패 {{ runTotals(run).failed }} · 미처리 {{ runTotals(run).pending }}</small></td><td><button class="mm-button mm-button--quiet" type="button" :aria-label="`${run.id} 상세 보기`" @click="openDetail(run)">{{ ['failed', 'partial_failed'].includes(run.status) ? '실패 로그 보기' : '상세 보기' }}<ArrowUpRight :size="14" /></button></td></tr></tbody></table></div>
    <div v-if="!filtered.length" class="mm-empty"><Clock3 :size="30" /><h3>{{ runs.length ? '조건에 맞는 이력이 없습니다' : '저장된 실행 이력이 없습니다' }}</h3><p>수집을 완료하거나 취소하면 처리 결과가 여기에 남습니다.</p><button v-if="runs.length" class="mm-button" type="button" @click="clear">필터 초기화</button></div>
    <footer class="mm-panel-foot">종료 로그는 7일 동안 보관됩니다. 진행 중 작업과 번역 수정 이력은 이 보관 기간과 구분합니다.</footer>
    <ManagementDialog :open="!!detailId" title="수집 실행 상세" @close="detailId = null"><p v-if="detailLoading" role="status">실행 로그를 불러오고 있습니다.</p><p v-if="detailError" role="alert">{{ detailError }}</p><RunDetails v-if="detail" :run="detail" /><template #footer><button type="button" class="mm-button" @click="detailId = null">닫기</button><button v-if="detail && retryIds(detail).length" type="button" class="mm-button mm-button--primary" :disabled="!!active" @click="retry(detail)"><RefreshCw :size="14" />실패·미처리 대상 재실행</button></template></ManagementDialog>
  </section>
</template>
