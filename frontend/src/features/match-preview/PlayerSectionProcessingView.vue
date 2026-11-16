<script setup lang="ts">
/**
 * NS-02 선수·부상 섹션 처리 진단 패널.
 *
 * 생성된 본문 아래 또는 노드 진단에서 고정 4슬롯(home1/home2/away1/away2,
 * home_etc=NULL/away_etc=NULL), DB 내부 ID/검증된 외부 ID, 한글명 출처,
 * 미연결/제외 사유, 시도별 원문·생성 JSON·재생성 이유를 그대로 보여준다.
 */
import { computed } from 'vue'
import type {
  PlayerSectionProcessingViewData,
  PlayerSectionSlotDraftView,
  PlayerSectionSlotKey,
} from './types'

const props = defineProps<{
  processing: PlayerSectionProcessingViewData
}>()

const SLOT_ORDER: readonly PlayerSectionSlotKey[] = ['home1', 'home2', 'away1', 'away2']

const SLOT_LABELS: Record<PlayerSectionSlotKey, string> = {
  home1: '홈 1 (home1)',
  home2: '홈 2 (home2)',
  away1: '원정 1 (away1)',
  away2: '원정 2 (away2)',
}

const NAME_SOURCE_LABELS: Record<string, string> = {
  db_ko: 'DB 한글명 (db_ko)',
  ai_candidate: 'AI 한글명 후보 (ai_candidate)',
}

const REGEN_REASON_LABELS: Record<string, string> = {
  missing_body: '설명 누락 (missing_body)',
  duplicate_player: '동일 선수 중복 (duplicate_player)',
  missing_and_duplicate: '설명 누락 및 중복 (missing_and_duplicate)',
}

const UNPLACED_REASON_LABELS: Record<string, string> = {
  missing_body: '설명 누락 (missing_body)',
  duplicate_player: '중복 선수 제외 (duplicate_player)',
  team_unresolved: '팀 미확인 (team_unresolved)',
  slot_capacity_exceeded: '팀당 2명 상한 초과 (slot_capacity_exceeded)',
  missing_name: '선수 이름 누락 (missing_name)',
  missing_name_ko: '한글명 없음·번역 결함 (missing_name_ko)',
}

type SlotRowEntry = {
  key: PlayerSectionSlotKey
  label: string
  slot: PlayerSectionSlotDraftView | null
}

const slotEntries = computed<SlotRowEntry[]>(() =>
  SLOT_ORDER.map((key) => ({
    key,
    label: SLOT_LABELS[key],
    slot: props.processing[key],
  })),
)

const isMock = computed(() => props.processing.mode === 'mock')

const adoptedLabel = computed(() => {
  const ord = props.processing.adopted_attempt_ordinal
  if (ord === null || ord === undefined) {
    if (props.processing.failed_reason) {
      return `채택 시도 없음 (${props.processing.failed_reason})`
    }
    if (props.processing.ok || props.processing.persisted) {
      return '채택 시도 추적 미기록 (저장·성공)'
    }
    return '채택 시도 없음 (실패)'
  }
  return `시도 ${ord + 1} (attempt_ordinal=${ord})`
})

const moduleAttemptsLabel = computed(() => {
  const count = props.processing.module_attempt_count
  if (count === 0 && (props.processing.ok || props.processing.persisted)) {
    return '추적 미기록 (저장·성공)'
  }
  return `${count}회 (최대 3회)`
})

const regenerationLabel = computed(() => {
  if (!props.processing.regeneration_count && !props.processing.regeneration_reason) {
    return '없음 (0회)'
  }
  const reason = props.processing.regeneration_reason
  const reasonText = reason ? (REGEN_REASON_LABELS[reason] ?? reason) : '사유 없음'
  return `${props.processing.regeneration_count}회 · ${reasonText}`
})

function formatPrettyJson(value: Record<string, unknown> | null): string {
  if (!value) return '없음'
  try {
    return JSON.stringify(value, null, 2)
  } catch {
    return String(value)
  }
}
</script>

<template>
  <section class="ns02-panel" data-testid="player-section-processing">
    <header class="ns02-panel__header">
      <div>
        <h3 class="ns02-panel__title">선수·부상 슬롯 및 생성 진단 (NS-02)</h3>
        <p class="ns02-panel__subtitle">
          워크플로우: <code>{{ processing.workflow_id }}</code> · 계약 버전:
          <code>{{ processing.output_contract_version }}</code> · 경기 ID:
          <code>{{ processing.fixture_id }}</code>
        </p>
      </div>
      <div class="ns02-panel__badges">
        <span
          class="ns02-badge"
          :class="
            processing.storage_mismatch
              ? 'ns02-badge--error'
              : processing.persisted
                ? 'ns02-badge--ok'
                : 'ns02-badge--pending'
          "
          data-testid="ns02-storage-status"
        >
          {{
            processing.storage_mismatch
              ? '저장 불일치'
              : processing.persisted
                ? '저장됨'
                : processing.storage_status || '저장 예정 값'
          }}
        </span>
        <span
          class="ns02-badge"
          :class="isMock ? 'ns02-badge--mock' : 'ns02-badge--live'"
          data-testid="ns02-mode-badge"
        >
          {{ isMock ? '모의 시연 (실제 AI 호출 아님)' : `실제 실행 (${processing.mode})` }}
        </span>
      </div>
    </header>

    <p
      v-if="processing.storage_mismatch"
      class="ns02-alert ns02-alert--error"
      data-testid="ns02-storage-mismatch"
    >
      저장 불일치: {{ processing.storage_error || '신규 선수/부상 섹션 전용 테이블 행이 없습니다. 기존 payload로 대체 표시하지 않습니다.' }}
    </p>

    <p v-else-if="!processing.persisted" class="ns02-note" data-testid="ns02-pending-note">
      아직 전용 테이블 통합 전이므로 아래 4슬롯과 후보는 <strong>저장 예정 값</strong>입니다.
      새로고침 조회만으로는 모델을 재호출하지 않습니다.
    </p>

    <p v-if="processing.failed_reason" class="ns02-alert ns02-alert--error" data-testid="ns02-failed-reason">
      처리 실패: {{ processing.failed_reason }}
    </p>

    <ul
      v-if="processing.translation_defects.length"
      class="ns02-alert ns02-alert--warn"
      data-testid="ns02-translation-defects"
    >
      <li v-for="(defect, idx) in processing.translation_defects" :key="idx">
        {{ defect }}
      </li>
    </ul>

    <dl class="ns02-summary">
      <div>
        <dt>채택 시도</dt>
        <dd data-testid="ns02-adopted-attempt">{{ adoptedLabel }}</dd>
      </div>
      <div>
        <dt>모듈 실제 전송</dt>
        <dd data-testid="ns02-module-attempts">{{ moduleAttemptsLabel }}</dd>
      </div>
      <div>
        <dt>내용 재생성</dt>
        <dd data-testid="ns02-regeneration">{{ regenerationLabel }}</dd>
      </div>
      <div>
        <dt>기타 확장 슬롯</dt>
        <dd data-testid="ns02-etc-null">home_etc = NULL · away_etc = NULL</dd>
      </div>
    </dl>

    <div class="ns02-slots">
      <h4 class="ns02-subhead">고정 4슬롯 결과</h4>
      <div class="ns02-slots__grid">
        <article
          v-for="entry in slotEntries"
          :key="entry.key"
          class="ns02-slot"
          :class="
            entry.slot === null
              ? 'ns02-slot--empty'
              : entry.slot.player_id !== null
                ? 'ns02-slot--resolved'
                : 'ns02-slot--unresolved'
          "
          :data-testid="`ns02-slot-${entry.key}`"
        >
          <div class="ns02-slot__head">
            <strong>{{ entry.label }}</strong>
            <span class="ns02-slot__state">
              <template v-if="entry.slot === null">비어 있음 (NULL)</template>
              <template v-else-if="entry.slot.player_id !== null">DB 연결됨</template>
              <template v-else>DB 미연결 (ID=NULL)</template>
            </span>
          </div>

          <template v-if="entry.slot">
            <dl class="ns02-slot__facts">
              <dt>표시 한글명</dt>
              <dd>{{ entry.slot.name_ko }}</dd>
              <dt>원문 이름</dt>
              <dd>{{ entry.slot.original_name }}</dd>
              <dt>한글명 출처</dt>
              <dd>{{ NAME_SOURCE_LABELS[entry.slot.name_source] ?? entry.slot.name_source }}</dd>
              <dt>내부 DB player_id</dt>
              <dd><code>{{ entry.slot.player_id ?? 'NULL' }}</code></dd>
              <dt>외부 사진용 ID</dt>
              <dd><code>{{ entry.slot.external_player_id ?? 'NULL' }}</code></dd>
              <template v-if="entry.slot.photo_url">
                <dt>사진 URL</dt>
                <dd><code class="ns02-url">{{ entry.slot.photo_url }}</code></dd>
              </template>
              <template v-if="entry.slot.candidate_review_status">
                <dt>번역 후보 상태</dt>
                <dd><code>{{ entry.slot.candidate_review_status }}</code></dd>
              </template>
              <template v-if="entry.slot.team_name || entry.slot.team_id !== null">
                <dt>소속 팀</dt>
                <dd>{{ entry.slot.team_name ?? '—' }} (ID: {{ entry.slot.team_id ?? 'NULL' }})</dd>
              </template>
              <template v-if="entry.slot.status">
                <dt>출전 상태</dt>
                <dd><code>{{ entry.slot.status }}</code></dd>
              </template>
              <template v-if="entry.slot.unresolved_reason">
                <dt>미연결 사유</dt>
                <dd class="ns02-unresolved-reason">{{ entry.slot.unresolved_reason }}</dd>
              </template>
            </dl>
            <p class="ns02-slot__body">{{ entry.slot.body }}</p>
            <p v-if="entry.slot.evidence.length" class="ns02-slot__evidence">
              근거: {{ entry.slot.evidence.join(', ') }}
            </p>
          </template>
        </article>
      </div>
    </div>

    <div v-if="processing.unplaced_items.length" class="ns02-unplaced" data-testid="ns02-unplaced-list">
      <h4 class="ns02-subhead">슬롯 제외·미배치 항목 ({{ processing.unplaced_items.length }}건)</h4>
      <ul class="ns02-list">
        <li
          v-for="(item, idx) in processing.unplaced_items"
          :key="`${item.original_name}-${idx}`"
          class="ns02-list__item"
        >
          <strong>{{ item.original_name }}</strong>
          <span v-if="item.team_hint"> ({{ item.team_hint }})</span>
          — <code>{{ UNPLACED_REASON_LABELS[item.reason] ?? item.reason }}</code>
          <span v-if="item.player_id !== null"> · player_id={{ item.player_id }}</span>
          <p v-if="item.detail" class="ns02-list__detail">{{ item.detail }}</p>
        </li>
      </ul>
    </div>

    <details class="ns02-attempts" data-testid="ns02-attempts-details">
      <summary class="ns02-attempts__summary">
        시도별 생성 JSON 및 재생성 판정 추적 ({{ processing.attempts.length }}건)
      </summary>
      <div
        v-for="attempt in processing.attempts"
        :key="`${attempt.logical_call_id}-${attempt.attempt_ordinal}`"
        class="ns02-attempt"
        :data-testid="`ns02-attempt-${attempt.attempt_ordinal}`"
      >
        <div class="ns02-attempt__head">
          <strong>시도 {{ attempt.attempt_ordinal + 1 }} (ordinal {{ attempt.attempt_ordinal }})</strong>
          <code>{{ attempt.logical_call_id }}</code>
          <span v-if="attempt.attempt_ordinal === processing.adopted_attempt_ordinal" class="ns02-badge ns02-badge--ok">
            채택됨
          </span>
          <span v-if="attempt.regeneration_triggered" class="ns02-badge ns02-badge--warn">
            재생성 유발: {{ REGEN_REASON_LABELS[attempt.regeneration_reason ?? ''] ?? attempt.regeneration_reason }}
          </span>
          <span v-if="!attempt.parsed_valid" class="ns02-badge ns02-badge--error">
            유효 JSON 아님 ({{ attempt.error_reason ?? '실패' }})
          </span>
        </div>
        <pre v-if="attempt.parsed_json" class="ns02-code">{{ formatPrettyJson(attempt.parsed_json) }}</pre>
        <pre v-else-if="attempt.raw_text" class="ns02-code">{{ attempt.raw_text }}</pre>
      </div>
    </details>
  </section>
</template>

<style scoped>
.ns02-panel {
  margin-top: 16px;
  padding: 16px;
  border: 1px solid #cbd5e1;
  border-radius: 10px;
  background: #f8fafc;
}
.ns02-panel__header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 12px;
  flex-wrap: wrap;
}
.ns02-panel__title {
  margin: 0;
  font-size: 16px;
}
.ns02-panel__subtitle {
  margin: 4px 0 0;
  font-size: 13px;
  color: #475569;
}
.ns02-panel__badges {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
}
.ns02-badge {
  display: inline-block;
  padding: 2px 8px;
  border-radius: 999px;
  font-size: 12px;
  font-weight: 600;
}
.ns02-badge--pending {
  background: #fef3c7;
  color: #92400e;
}
.ns02-badge--ok {
  background: #dcfce7;
  color: #166534;
}
.ns02-badge--mock {
  background: #e2e8f0;
  color: #334155;
}
.ns02-badge--live {
  background: #dbeafe;
  color: #1e40af;
}
.ns02-badge--warn {
  background: #ffedd5;
  color: #9a3412;
}
.ns02-badge--error {
  background: #fee2e2;
  color: #991b1b;
}
.ns02-note {
  margin: 10px 0 0;
  padding: 8px 10px;
  border-radius: 6px;
  background: #fffbeb;
  color: #78350f;
  font-size: 13px;
}
.ns02-alert {
  margin: 10px 0 0;
  padding: 8px 12px;
  border-radius: 6px;
  font-size: 13px;
}
.ns02-alert--error {
  background: #fef2f2;
  color: #991b1b;
}
.ns02-alert--warn {
  background: #fff7ed;
  color: #9a3412;
  list-style: disc;
  padding-left: 24px;
}
.ns02-summary {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: 8px 16px;
  margin: 12px 0;
  padding: 10px 12px;
  background: #ffffff;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
}
.ns02-summary dt {
  font-size: 12px;
  color: #64748b;
}
.ns02-summary dd {
  margin: 2px 0 0;
  font-size: 13px;
  font-weight: 600;
}
.ns02-subhead {
  margin: 12px 0 8px;
  font-size: 14px;
}
.ns02-slots__grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
  gap: 10px;
}
.ns02-slot {
  padding: 10px 12px;
  border-radius: 8px;
  background: #ffffff;
  border: 1px solid #cbd5e1;
}
.ns02-slot--empty {
  background: #f1f5f9;
  color: #64748b;
}
.ns02-slot--unresolved {
  border-color: #f59e0b;
}
.ns02-slot__head {
  display: flex;
  justify-content: space-between;
  gap: 8px;
  font-size: 13px;
}
.ns02-slot__state {
  font-size: 12px;
  color: #475569;
}
.ns02-slot__facts {
  display: grid;
  grid-template-columns: auto 1fr;
  gap: 2px 10px;
  margin: 8px 0;
  font-size: 12px;
}
.ns02-slot__facts dt {
  color: #64748b;
}
.ns02-slot__facts dd {
  margin: 0;
}
.ns02-unresolved-reason {
  color: #b45309;
  font-weight: 600;
}
.ns02-slot__body {
  margin: 6px 0 0;
  font-size: 13px;
  white-space: pre-wrap;
}
.ns02-slot__evidence {
  margin: 6px 0 0;
  font-size: 12px;
  color: #475569;
}
.ns02-list {
  margin: 0;
  padding-left: 18px;
  font-size: 13px;
}
.ns02-list__item + .ns02-list__item {
  margin-top: 6px;
}
.ns02-list__detail {
  margin: 2px 0 0;
  font-size: 12px;
  color: #475569;
}
.ns02-attempts {
  margin-top: 12px;
}
.ns02-attempts__summary {
  cursor: pointer;
  font-size: 13px;
  font-weight: 600;
}
.ns02-attempt {
  margin-top: 8px;
  padding: 8px 10px;
  border: 1px solid #e2e8f0;
  border-radius: 6px;
  background: #ffffff;
}
.ns02-attempt__head {
  display: flex;
  gap: 8px;
  align-items: center;
  flex-wrap: wrap;
  font-size: 13px;
}
.ns02-code {
  margin: 8px 0 0;
  padding: 8px;
  border-radius: 6px;
  background: #0f172a;
  color: #e2e8f0;
  font-size: 12px;
  overflow-x: auto;
}
</style>
