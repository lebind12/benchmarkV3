<script setup lang="ts">
import { computed, ref } from 'vue'
import { Play, Square, ArrowRight, Activity, RefreshCw } from 'lucide-vue-next'
import { useManagementApi, type CollectionRun, type CollectionTarget } from '@/lib/api/management'
import ManagementDialog from './ManagementDialog.vue'
import RunDetails from './RunDetails.vue'
import { retryIds } from './display'
const api = useManagementApi()
const props = defineProps<{ targets: CollectionTarget[]; selected: number[]; active: CollectionRun | null; result: CollectionRun | null; parent: string | null; preferredMode?: 'initial' | 'refresh' }>()
const emit = defineEmits<{ selection: [ids: number[]]; started: [run: CollectionRun]; refresh: []; notify: [message: string]; history: []; retry: [run: CollectionRun] }>()
const mode = ref<'initial' | 'refresh'>(props.preferredMode ?? 'refresh')
const confirm = ref(false)
const cancelConfirm = ref(false)
const busy = ref(false)
const error = ref('')
const selectedTargets = computed(() => props.targets.filter((row) => props.selected.includes(row.id) && row.is_active))
function toggle(id: number) { emit('selection', props.selected.includes(id) ? props.selected.filter((value) => value !== id) : [...props.selected, id]) }
async function start() {
  busy.value = true; error.value = ''
  try { const run = await api.start(selectedTargets.value.map((row) => row.id), mode.value, props.parent); confirm.value = false; emit('started', run); emit('notify', '수집을 시작했습니다. 다른 사용자의 작업도 동일한 실행 상태를 공유합니다.') }
  catch (err) { error.value = err instanceof Error ? err.message : '실행하지 못했습니다.'; emit('refresh') }
  finally { busy.value = false }
}
async function cancel() {
  if (!props.active) return
  busy.value = true
  try { await api.cancel(props.active.id); cancelConfirm.value = false; emit('refresh'); emit('notify', '취소를 요청했습니다. 이미 저장한 데이터는 유지됩니다.') }
  catch (err) { emit('notify', err instanceof Error ? err.message : '취소 요청에 실패했습니다.') }
  finally { busy.value = false }
}
</script>
<template>
  <div class="mm-execution-grid">
    <section class="mm-panel">
      <header class="mm-panel-head"><div><h2>수집 실행</h2><p>대상과 실행 방식을 확인한 후 시작하세요.</p></div><Play :size="19" class="mm-muted" /></header>
      <div class="mm-panel-body">
        <p v-if="parent" class="mm-note">이력 {{ parent }}의 실패·미처리 대상을 다시 실행합니다.</p>
        <fieldset class="mm-run-choices"><legend>수집 대상 <span>{{ selectedTargets.length }}개 선택</span></legend><label v-for="target in targets" :key="target.id" :class="{ 'mm-disabled': !target.is_active }"><input type="checkbox" :checked="selected.includes(target.id)" :disabled="!target.is_active || !!active" :aria-label="`${target.name} ${target.season} 실행 선택`" @change="toggle(target.id)" /><span><strong>{{ target.name }}</strong><small>{{ target.season }} 시즌{{ !target.is_active ? ' · 비활성' : '' }}</small></span><span class="mm-caption">{{ target.fixture_limit ? `${target.fixture_limit}경기` : '제한 없음' }}</span></label></fieldset>
        <fieldset class="mm-modes"><legend>실행 방식</legend><label :class="{ selected: mode === 'refresh' }"><input v-model="mode" type="radio" value="refresh" :disabled="!!active" /><span><strong>갱신 수집</strong><small>최근 3일과 예정 경기의 변경 사항을 갱신합니다.</small></span></label><label :class="{ selected: mode === 'initial' }"><input v-model="mode" type="radio" value="initial" :disabled="!!active" /><span><strong>최초 수집</strong><small>선택 시즌 전체를 수집합니다. 설정한 경기 수 제한은 유지됩니다.</small></span></label></fieldset>
        <p class="mm-caption">상세·선수·순위 포함 여부는 각 대상에 저장한 설정을 사용합니다.</p>
        <button type="button" class="mm-button mm-button--primary mm-full" :disabled="!!active || !selectedTargets.length || selectedTargets.length > 20" @click="error = ''; confirm = true"><Play :size="15" />{{ active ? '진행 중인 수집을 먼저 확인하세요' : `${selectedTargets.length}개 대상 수집 시작` }}</button>
      </div>
    </section>
    <section class="mm-panel" aria-label="수집 진행 상태">
      <header class="mm-panel-head"><div><h2>{{ active ? '진행 중인 작업' : result ? '최근 작업 결과' : '작업 모니터' }}</h2><p>{{ active ? '진행 상태를 자동으로 확인하고 있습니다.' : '저장·실패·미처리를 나누어 확인합니다.' }}</p></div><Activity :size="20" class="mm-muted" /></header>
      <div class="mm-panel-body"><template v-if="active || result"><RunDetails :run="(active || result)!" /><div class="mm-action-row"><button v-if="active" type="button" class="mm-button mm-button--danger" :disabled="active.status === 'cancel_requested' || busy" @click="cancelConfirm = true"><Square :size="14" />{{ active.status === 'cancel_requested' ? '취소 처리 중…' : '수집 취소' }}</button><button v-else-if="result && retryIds(result).length" type="button" class="mm-button" @click="emit('retry', result)"><RefreshCw :size="15" />실패·미처리 대상 재실행</button><button type="button" class="mm-button mm-button--quiet" @click="emit('history')">실행 이력 보기<ArrowRight :size="14" /></button></div></template><div v-else class="mm-empty mm-empty--tall"><Activity :size="34" /><h3>수집할 준비가 되었습니다</h3><p>왼쪽에서 대상을 고르고 실행하면<br />처리 상태와 로그가 여기에 표시됩니다.</p><small>새로고침 후에도 진행 중 작업을 이어서 확인할 수 있습니다.</small></div></div>
    </section>
    <ManagementDialog :open="confirm" title="수집을 시작할까요?" @close="confirm = false"><p>{{ mode === 'initial' ? '시즌 전체 최초 수집' : '최근 경기 갱신' }}을 <strong>{{ selectedTargets.length }}개 대상</strong>에 실행합니다.</p><ul class="mm-confirm-list"><li v-for="target in selectedTargets" :key="target.id"><strong>{{ target.name }} {{ target.season }}<small class="mm-caption">{{ [target.include_details ? '경기 상세' : '', target.include_players ? '선수' : '', target.include_standings ? '순위' : ''].filter(Boolean).join(' · ') || '경기 목록' }}</small></strong><span>{{ target.fixture_limit ? `${target.fixture_limit}경기 제한` : '경기 수 제한 없음' }}</span></li></ul><p class="mm-note">수집 설정과 결과는 전체 서비스에 공통 적용됩니다. 외부 호출량을 사용하며 실행 중인 작업은 전체 서비스에서 하나로 제한됩니다.</p><p v-if="selectedTargets.length > 20" class="mm-error-text">한 번에 최대 20개 대상을 실행할 수 있습니다. 대상을 나누어 선택하세요.</p><p v-if="error" class="mm-error-text" role="alert">{{ error }}</p><template #footer><button class="mm-button" type="button" @click="confirm = false">돌아가기</button><button class="mm-button mm-button--primary" type="button" :disabled="busy" @click="start">{{ busy ? '시작 중…' : '수집 실행' }}</button></template></ManagementDialog>
    <ManagementDialog :open="cancelConfirm" title="수집을 취소할까요?" @close="cancelConfirm = false"><p>현재 저장 단위가 끝나면 이후 작업을 중단합니다.</p><p class="mm-note">이미 저장한 데이터는 유지하고, 남은 미처리는 따로 표시합니다. 이후 안전하게 다시 실행할 수 있습니다.</p><template #footer><button class="mm-button" type="button" @click="cancelConfirm = false">계속 수집</button><button class="mm-button mm-button--danger" type="button" :disabled="busy" @click="cancel">취소 요청</button></template></ManagementDialog>
  </div>
</template>
