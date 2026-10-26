<script setup lang="ts">
import { computed } from 'vue'
import type { CollectionRun, RunStatus } from '@/lib/api/managementTypes'
import { dateTime, runTotals, statusLabels } from './display'
import RunLogs from './RunLogs.vue'
const props = defineProps<{ run: CollectionRun }>()
const totals = computed(() => runTotals(props.run))
</script>
<template>
  <div class="mm-run-detail">
    <div class="mm-run-title"><div><span class="mm-caption">{{ run.mode === 'initial' ? '최초 수집' : '갱신 수집' }} · {{ run.actor }}</span><h3>{{ run.stage }}</h3></div><span :class="['mm-badge', `mm-badge--${run.status}`]">{{ statusLabels[run.status] }}</span></div>
    <div class="mm-progress" role="progressbar" aria-label="수집 진행률" :aria-valuenow="run.progress" :aria-valuemin="0" :aria-valuemax="100"><i :style="{ width: `${run.progress}%` }" /></div>
    <div class="mm-between mm-caption"><span>작업 진행 {{ run.progress }}%</span><span>{{ dateTime(run.started_at) }} 시작</span></div>
    <div v-if="run.counts_kind !== 'legacy_unknown'" class="mm-result-totals"><div><span>{{ run.counts_kind ? '처리 완료' : '저장' }}</span><strong>{{ totals.saved }}</strong></div><div><span>실패</span><strong>{{ totals.failed }}</strong></div><div><span>미처리</span><strong>{{ totals.pending }}</strong></div></div>
    <p v-if="run.counts_kind === 'processing_units'" class="mm-note">처리·실패·미처리는 API/적재 단계 단위입니다. DB에 저장한 행은 {{ run.items.reduce((sum,item) => sum + (item.stored_rows ?? 0), 0) }}건(재실행 시 upsert 포함)입니다. 가져온 뒤 아직 저장하지 않은 자료는 재실행 시 다시 확인합니다.</p>
    <p v-if="!run.counts_kind && (run.status === 'cancelled' || run.status === 'cancel_requested' || run.status === 'interrupted')" class="mm-note">이미 저장한 {{ totals.saved }}건은 유지됩니다. 미처리 {{ totals.pending }}건은 이후 다시 수집할 수 있습니다.</p>
    <p v-if="run.counts_kind === 'legacy_unknown'" class="mm-note">기존 실행에는 대상별 처리 수와 저장 행 수가 기록되어 있지 않습니다. 아래에서 보관 로그의 단계·원인 분류를 확인할 수 있습니다.</p><p v-if="run.items.some(item => item.total_known === false)" class="mm-note">수집 범위를 확인하지 못한 대상이 있습니다. 해당 대상의 미처리 수는 아직 집계되지 않았습니다.</p><div v-if="run.counts_kind !== 'legacy_unknown'" class="mm-table-wrap"><table class="mm-table"><thead><tr><th>대상</th><th>상태</th><th class="mm-numeric">{{ run.counts_kind ? '처리' : '저장' }}</th><th class="mm-numeric">실패</th><th class="mm-numeric">미처리</th></tr></thead><tbody><tr v-for="item in run.items" :key="item.target_id"><td><strong>{{ item.name }}</strong><small>{{ item.season }} 시즌</small></td><td>{{ statusLabels[item.status as RunStatus] ?? item.status }}</td><td class="mm-numeric">{{ item.saved }}</td><td class="mm-numeric">{{ item.failed }}</td><td class="mm-numeric">{{ item.total_known === false ? '확인 전' : item.pending }}</td></tr></tbody></table></div>
    <RunLogs :key="run.id" :run="run" />
    <div class="mm-caption mm-run-meta">작업 {{ run.id }}<span v-if="run.finished_at"> · {{ dateTime(run.finished_at) }} 종료</span><span v-if="run.parent_run_id"> · 원래 작업 {{ run.parent_run_id }}</span></div>
  </div>
</template>
