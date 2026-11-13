<script setup lang="ts">
/**
 * 섹션 결과 버전 **구성본** 패널 (SF-02 차단 2 연결).
 *
 * 사용자가 하는 일은 정확히 셋이다.
 *
 *   1) 실행에 저장된 섹션 결과 중 **섹션당 버전 하나**를 고른다
 *   2) 그 선택을 **구성본으로 저장**한다(`POST /runs/{run_id}/composition`)
 *   3) 그 구성본으로 **마지막 AI 전망만** 다시 실행한다
 *      (`POST /section-runs` + `composition_id`)
 *
 * 지키는 것:
 *
 * - 고르지 않은 "최신"을 서버도 화면도 임의로 넣지 않는다. 섹션당 정확히 1개만 보낸다.
 * - 다른 경기의 결과나 없는 결과는 서버가 `refused[]`로 돌려주고, 화면은 그 사유를
 *   그대로 보여준다(조용히 빼지 않는다).
 * - 저장은 모델·HTTP를 쓰지 않는다. 실행은 사용자가 버튼을 눌렀을 때만 나간다.
 * - 부모 실행의 저장 결과는 바뀌지 않는다(새 실행 + 새 결과 버전).
 */
import { computed, ref, watch } from 'vue'
import { previewRunsApi } from './api'
import type { CompositionView, SectionResultView, SectionRunResponse } from './types'

const props = defineProps<{
  /** 구성본을 저장할 실행(기준 실행). */
  runId: string
  /** 그 실행이 저장한 섹션 결과들(여러 버전일 수 있다). */
  results: SectionResultView[]
  /** 경기 식별자. 없으면 서버가 거부하므로 실행 버튼을 열지 않는다. */
  fixtureId: number | null
}>()

const emit = defineEmits<{
  (event: 'ran', payload: SectionRunResponse): void
}>()

/** 섹션 표시 순서(서버와 같은 순서를 쓴다). 저장에 없는 섹션은 그리지 않는다. */
const SECTION_ORDER = [
  'section_players',
  'section_availability',
  'section_outlook',
  'section_odds',
  'section_ai_forecast',
] as const

const SECTION_TITLES: Record<string, string> = {
  section_players: '주목 선수',
  section_availability: '부상·결장',
  section_outlook: '외부 매체 전망',
  section_odds: '배당',
  section_ai_forecast: 'AI 경기 전망',
}

const FINAL_SECTION = 'section_ai_forecast'

/** 섹션별 선택 결과 ID. 기본값은 그 섹션의 **가장 최근** 결과 1건이다. */
const picked = ref<Record<string, string>>({})
const savedComposition = ref<CompositionView | null>(null)
const busy = ref<'save' | 'run' | null>(null)
const errorMessage = ref<string | null>(null)
const doneMessage = ref<string | null>(null)

/** 이 실행에 저장된 섹션 목록(표시 순서). */
const sections = computed(() =>
  SECTION_ORDER.filter((id) => props.results.some((row) => row.workflow_id === id)),
)

function rowsOf(sectionId: string): SectionResultView[] {
  return props.results
    .filter((row) => row.workflow_id === sectionId)
    .slice()
    .sort((a, b) => (b.version ?? 0) - (a.version ?? 0))
}

/** 최신 결과 1건을 기본 선택으로 채운다(사용자가 바꾸면 그 값을 유지한다). */
function seedSelection() {
  const next: Record<string, string> = {}
  for (const sectionId of sections.value) {
    const keep = picked.value[sectionId]
    const rows = rowsOf(sectionId)
    const stillExists = rows.some((row) => row.section_result_id === keep)
    next[sectionId] = stillExists ? keep : (rows[0]?.section_result_id ?? '')
  }
  picked.value = next
}

watch(() => [props.runId, props.results], seedSelection, { immediate: true, deep: true })

/** 보낼 선택 ID(섹션당 1개, 표시 순서). */
const selectedIds = computed<string[]>(() =>
  sections.value
    .map((sectionId) => picked.value[sectionId])
    .filter((value): value is string => Boolean(value)),
)

const canSave = computed(
  () => Boolean(props.runId) && selectedIds.value.length > 0 && busy.value === null,
)

/**
 * 구성본이 저장된 실행. 마지막 AI 실행도 **같은 실행**을 기준으로 보내야 서버가 그 실행의
 * 저장 구성본을 찾는다. 다른 실행을 기준으로 보내면 구성본을 못 찾아 거부된다.
 */
const compositionRunId = computed(() => props.runId)

const canRun = computed(
  () =>
    Boolean(savedComposition.value?.composition_id) &&
    props.fixtureId !== null &&
    busy.value === null,
)

function choose(sectionId: string, resultId: string) {
  picked.value = { ...picked.value, [sectionId]: resultId }
  // 선택이 바뀌면 저장된 구성본은 더 이상 이 선택과 같지 않다. 저장을 다시 요구한다.
  savedComposition.value = null
  doneMessage.value = null
}

async function save() {
  if (!canSave.value) return
  busy.value = 'save'
  errorMessage.value = null
  doneMessage.value = null
  const result = await previewRunsApi.saveComposition(props.runId, {
    fixture_id: props.fixtureId ?? undefined,
    selected_result_ids: selectedIds.value,
  })
  busy.value = null
  if (!result.ok) {
    errorMessage.value = result.message
    return
  }
  savedComposition.value = {
    composition_id: result.data.composition_id,
    fixture_id: result.data.fixture_id,
    items: result.data.items,
    refused: result.data.refused,
    diagnostics: result.data.diagnostics,
    section_result_ids: result.data.section_result_ids,
  }
  const refused = result.data.refused ?? []
  doneMessage.value = refused.length
    ? `구성본 ${result.data.composition_id}을 저장했습니다. 쓰지 않은 선택 ${refused.length}건이 있습니다(사유 참고).`
    : `구성본 ${result.data.composition_id}을 저장했습니다. 모델·외부 호출은 없습니다.`
}

/**
 * 저장된 구성본으로 **마지막 AI 전망만** 다시 만든다.
 *
 * `composition_id`를 명시해 서버가 그 구성본의 선택 결과를 입력으로 쓰게 한다.
 * `source_mode: 'reuse'`라 새 수집·새 검색 호출이 없다.
 *
 * `mode`는 생략하지 않는다. 이 버튼은 실제 모델 호출을 일으키는 생성 의도이므로 `live`를
 * 명시한다. 생략하면 서버 기본값(`mock`)으로 떨어져 `source_mode: 'reuse'` 옛 경로 거부에
 * 걸려 항상 422가 된다(기능이 동작하지 않는다).
 */
async function runFinal() {
  if (!canRun.value || props.fixtureId === null) return
  const compositionId = savedComposition.value?.composition_id
  if (!compositionId) return
  busy.value = 'run'
  errorMessage.value = null
  doneMessage.value = null
  const result = await previewRunsApi.regenerateSection({
    workflow_id: FINAL_SECTION,
    // 실제 생성 요청임을 서버에 명시한다(생략 시 mock 기본값으로 떨어진다).
    mode: 'live',
    fixture_id: props.fixtureId,
    source_mode: 'reuse',
    base_run_id: compositionRunId.value,
    composition_id: compositionId,
  })
  busy.value = null
  if (!result.ok) {
    errorMessage.value = result.message
    return
  }
  doneMessage.value =
    `마지막 AI 전망을 실행했습니다. 실제 모델 전송 ${result.data.external_calls}회 · ` +
    `품질 ${result.data.quality}` +
    (result.data.unavailable_reason ? ` · 사유: ${result.data.unavailable_reason}` : '')
  emit('ran', result.data)
}
</script>

<template>
  <section class="composition" data-testid="composition-panel">
    <header class="composition__head">
      <h3 class="composition__title">섹션 버전 구성본 → 마지막 AI</h3>
      <p class="composition__note">
        섹션마다 <strong>버전 하나</strong>를 골라 구성본으로 저장하고, 그 구성본으로 마지막
        AI 전망만 다시 실행합니다. 고르지 않은 최신 버전을 섞지 않으며, 저장은 모델·외부
        호출을 하지 않습니다.
      </p>
    </header>

    <fieldset v-for="sectionId in sections" :key="sectionId" class="composition__group">
      <legend class="composition__legend">
        {{ SECTION_TITLES[sectionId] ?? sectionId }}
        <span v-if="sectionId === FINAL_SECTION" class="composition__chip">마지막 AI</span>
      </legend>
      <label
        v-for="row in rowsOf(sectionId)"
        :key="row.section_result_id"
        class="composition__choice"
      >
        <input
          type="radio"
          :name="`composition-${sectionId}`"
          :value="row.section_result_id"
          :checked="picked[sectionId] === row.section_result_id"
          :disabled="busy !== null"
          data-testid="composition-choice"
          @change="choose(sectionId, row.section_result_id)"
        />
        <span>
          <strong>v{{ row.version }}</strong>
          <span class="composition__hint">
            {{ row.quality }}
            <template v-if="row.unavailable"> · 부분 결과</template>
            · {{ row.body ? `${row.body.length}자` : '본문 없음' }}
            <template v-if="row.mode !== 'live'"> · {{ row.mode }}</template>
          </span>
        </span>
      </label>
    </fieldset>

    <p v-if="!sections.length" class="composition__state" data-testid="composition-empty">
      이 실행에는 저장된 섹션 결과가 없습니다. 섹션을 먼저 실행하세요.
    </p>

    <div class="composition__actions">
      <button
        type="button"
        class="button"
        :disabled="!canSave"
        data-testid="composition-save"
        @click="save"
      >
        {{ busy === 'save' ? '저장 중…' : '선택으로 구성본 저장' }}
      </button>
      <button
        type="button"
        class="button"
        :disabled="!canRun"
        data-testid="composition-run-final"
        @click="runFinal"
      >
        {{ busy === 'run' ? '실행 중…' : '이 구성본으로 마지막 AI 실행' }}
      </button>
    </div>

    <p v-if="fixtureId === null" class="composition__state" data-testid="composition-no-fixture">
      경기 식별자가 없어 실행할 수 없습니다. 경기를 먼저 선택하세요.
    </p>

    <p v-if="errorMessage" class="composition__state composition__state--error" role="alert" data-testid="composition-error">
      {{ errorMessage }}
    </p>
    <p v-if="doneMessage" class="composition__state" data-testid="composition-done">
      {{ doneMessage }}
    </p>

    <div v-if="savedComposition" class="composition__saved" data-testid="composition-saved">
      <p class="composition__hint">
        저장된 구성본 <strong>{{ savedComposition.composition_id }}</strong> ·
        항목 {{ savedComposition.items.length }}건
      </p>
      <ul class="composition__list">
        <li v-for="item in savedComposition.items" :key="item.result_id" class="composition__item">
          {{ SECTION_TITLES[item.section_id] ?? item.section_id }} v{{ item.version }} ·
          {{ item.quality }} · 실행 {{ item.run_id.slice(0, 8) }}
        </li>
      </ul>
      <p v-if="savedComposition.refused.length" class="composition__state" data-testid="composition-refused">
        쓰지 않은 선택: {{ savedComposition.refused.map((row) => row.reason).join(' / ') }}
      </p>
    </div>
  </section>
</template>

<style scoped>
.composition {
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  padding: 12px 16px;
  margin: 16px 0;
}
.composition__head {
  margin-bottom: 8px;
}
.composition__title {
  font-size: 15px;
  margin: 0 0 4px;
}
.composition__note {
  color: #4b5563;
  font-size: 13px;
  margin: 0;
}
.composition__group {
  border: 0;
  border-top: 1px solid #f3f4f6;
  margin: 8px 0 0;
  padding: 8px 0 0;
}
.composition__legend {
  font-weight: 600;
  font-size: 13px;
  padding: 0;
}
.composition__chip {
  background: #eef2ff;
  border-radius: 4px;
  font-size: 11px;
  margin-left: 6px;
  padding: 1px 6px;
}
.composition__choice {
  align-items: flex-start;
  display: flex;
  gap: 8px;
  margin: 6px 0;
}
.composition__hint {
  color: #6b7280;
  font-size: 12px;
}
.composition__actions {
  display: flex;
  gap: 8px;
  margin-top: 12px;
}
.composition__state {
  color: #4b5563;
  font-size: 13px;
  margin: 8px 0 0;
}
.composition__state--error {
  color: #b91c1c;
}
.composition__saved {
  margin-top: 12px;
}
.composition__list {
  font-size: 12px;
  margin: 4px 0 0;
  padding-left: 18px;
}
.composition__item {
  color: #374151;
}
</style>
