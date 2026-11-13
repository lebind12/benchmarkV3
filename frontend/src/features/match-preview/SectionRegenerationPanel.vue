<script setup lang="ts">
/**
 * 선택 섹션 재생성·비교·승인 패널 (PS-04).
 *
 * 이 패널이 다루는 것은 **저장된 정보 원문을 재사용하는가, 새로 수집하는가**와
 * **무호출 재처리인가, 실제 재생성(모델 호출)인가**의 구분이다. 사용자가 명시적으로
 * 눌러야만 요청이 나가고, 승인 행은 자동으로 만들지 않는다.
 *
 * 세 동작을 섞지 않는다:
 *
 * | 동작 | 자료 | 모델 전송 | 결과 |
 * |---|---|---|---|
 * | 저장 응답 재처리 | 저장된 응답 원문 | 0회 | 새 결과 버전 |
 * | 정보 원문 재사용 재생성 | 저장된 묶음(bundle) | 비용 발생 | 새 결과 버전 |
 * | 새 수집 재생성 | 새 HTTP 수집 + 모델 | 비용 발생 | 새 결과 버전 |
 *
 * 화면은 위 구분을 **누르기 전에** 보여준다. 서버가 응답에 준 실제 전송 수
 * (`external_calls`)를 결과에 그대로 표시하며, 화면이 추정값을 만들지 않는다.
 */
import { computed, ref } from 'vue'
import { previewRunsApi } from './api'
import type {
  SectionRegenerationRequest,
  SectionResultView,
  SectionRunResponse,
  SourceMode,
} from './types'

const props = withDefaults(
  defineProps<{
    workflowId: string
    fixtureId: number | null
    /** 이 섹션의 저장된 결과들(버전 오름차순). 비교 기준을 여기서 고른다. */
    results: SectionResultView[]
    /** 재사용할 저장 묶음 ID. 없으면 재사용 모드를 열지 않는다. */
    bundleId?: string | null
    /**
     * 새 run의 구성본에 **그대로 남길** 다른 섹션 결과 ID(현재 화면이 보여주는 버전).
     *
     * 이 값을 서버에 `selected_result_ids`로 보내면 서버가 각 결과를 자기 실행에서 검증해
     * 새 run 구성본으로 복사하고, 이 패널이 다시 만든 섹션만 교체한다. 비우면 서버는
     * 저장된 구성본(없으면 최신 결과)을 쓰므로 다른 섹션 본문이 달라질 수 있다.
     */
    selectedResultIds?: string[]
    /**
     * 부모가 승인 가능 여부를 이미 판단했으면 그 값을 넘긴다. 넘기지 않으면 이 패널은
     * 결과의 `approvable`만으로 판단한다(Boolean prop의 암묵 기본값 false에 기대지 않음).
     */
    canApprove?: boolean
    /**
     * 승인 블록을 이 패널에 그릴지. 같은 화면에 승인 UI가 이미 있으면 끈다
     * (승인 경로를 두 개 만들지 않는다).
     */
    showApproval?: boolean
  }>(),
  { bundleId: null, selectedResultIds: () => [], canApprove: true, showApproval: false },
)

const emit = defineEmits<{
  (event: 'regenerated', payload: SectionRunResponse): void
  (event: 'approved', payload: { sectionResultId: string; note: string | null }): void
  (event: 'reprocess', payload: { resultId: string; note: string | null }): void
}>()

const sourceMode = ref<SourceMode>('reuse')
const action = ref<'reuse' | 'refresh' | 'reprocess'>('reuse')
const note = ref('')
const pending = ref(false)
const errorMessage = ref<string | null>(null)
const doneMessage = ref<string | null>(null)

const selectedResultId = ref<string | null>(null)

const orderedResults = computed(() =>
  [...props.results].sort((left, right) => left.version - right.version),
)

const latestResult = computed<SectionResultView | null>(
  () => orderedResults.value[orderedResults.value.length - 1] ?? null,
)

const previousResult = computed<SectionResultView | null>(
  () => orderedResults.value[orderedResults.value.length - 2] ?? null,
)

const selectedResult = computed<SectionResultView | null>(() => {
  const id = selectedResultId.value
  if (id === null) return latestResult.value
  return orderedResults.value.find((row) => row.section_result_id === id) ?? latestResult.value
})

const reuseAvailable = computed(() => Boolean(props.bundleId))
const fixtureMissing = computed(() => props.fixtureId === null)

/** 새 수집은 실제 HTTP·모델 호출이 발생한다. 누르기 전에 그 사실을 알린다. */
const refreshWarning = computed(() =>
  // 새 수집은 배당도 **자료 검색 모델**과 외부 API 조회를 발생시킨다(배당 본문 작성만 모델을
  // 쓰지 않는다). "모델 0회"로 단정하면 실제 호출·과금과 어긋나므로 그 단정을 빼고, 저장된
  // 정보 원문 재사용(reuse)만 수집을 다시 하지 않는다는 사실을 적는다.
  oddsSection.value
    ? '새 수집은 자료 검색 모델 호출과 외부 API 조회(배당 포함)를 새로 발생시킵니다. ' +
      '배당 본문 작성 자체는 모델을 쓰지 않지만, 조사 단계의 모델 호출은 발생합니다. ' +
      '저장된 정보 원문을 재사용하면 수집은 다시 하지 않습니다.'
    : '새 수집은 외부 HTTP 요청과 모델 호출을 새로 발생시킵니다. 저장된 정보 원문을 ' +
      '재사용하면 수집은 다시 하지 않습니다.',
)

/**
 * 배당 섹션인지. **모델을 안 부르는 섹션**이라는 뜻이 아니다.
 *
 * - `reuse`: 저장된 정보 원문을 재사용하며 모델 전송은 0회다(필요 시 배당 API 1회 보완).
 * - `refresh`: 배당 본문 작성은 모델을 쓰지 않지만, 자료 조사를 위해 `discovery_outlook`
 *   조사 모델을 **1회** 호출한다(`regeneration_logical_call_ids('section_odds','refresh')`
 *   → `('discovery_outlook',)`). 즉 refresh는 모델 0회가 아니다.
 *
 * 그래서 문구는 실행 방식별로 나눠 쓰고, 결과 문구는 `section_id`로 모델 0을 단정하지 않고
 * 응답의 `no_model_call`·실제 모델 전송 수를 따른다.
 */
const oddsSection = computed(() => props.workflowId === 'section_odds')

const reprocessHint = computed(
  () =>
    '저장된 응답 재처리는 모델을 다시 부르지 않습니다(0회). 같은 응답으로 본문만 다시 ' +
    '만들며, 새 결과 버전으로 저장됩니다. 새 응답을 사는 재생성과 다릅니다.',
)

const comparison = computed(() => {
  const target = selectedResult.value
  if (!target) return null
  const base = previousResult.value
  if (!base || base.section_result_id === target.section_result_id) return null
  return {
    base,
    target,
    bodyChanged: base.body !== target.body,
    sourcesChanged:
      JSON.stringify(base.sources.map((row) => row.url ?? row.label)) !==
      JSON.stringify(target.sources.map((row) => row.url ?? row.label)),
  }
})

function chooseAction(next: 'reuse' | 'refresh' | 'reprocess') {
  action.value = next
  errorMessage.value = null
  doneMessage.value = null
}

function selectResult(id: string) {
  selectedResultId.value = id
}

/**
 * 재생성 요청. 사용자가 버튼을 눌렀을 때만 호출된다.
 *
 * 필드 이름은 manifest §5를 그대로 쓴다(`mode`, `source_mode`, `bundle_id`,
 * `base_run_id`, `base_result_id`). `reuse`에는 `bundle_id`가 필수이며, 없으면 요청을
 * 보내지 않는다. 경기 식별자가 없으면 서버가 거부하므로 여기서도 보내지 않는다.
 *
 * `mode`는 생략하지 않는다. 이 버튼은 **실제 생성 의도**이므로 `live`를 명시한다.
 * 생략하면 서버 기본값(`mock`)으로 떨어져 모의 본문이 새 실행·새 버전으로 저장되고,
 * 사용자가 누른 "새 수집으로 재생성"이 실행되지 않는다. 모의 시연은 이 화면의 동작이
 * 아니며, 서버 기본값을 바꾸지도 않는다(다른 호출자의 모의 계약을 깬다).
 */
async function regenerate() {
  if (action.value === 'reprocess') {
    await reprocess()
    return
  }
  const fixtureId = props.fixtureId
  if (fixtureId === null) {
    errorMessage.value = '경기 식별자가 없어 재생성할 수 없습니다. 경기를 먼저 선택하세요.'
    return
  }
  sourceMode.value = action.value === 'refresh' ? 'refresh' : 'reuse'
  if (sourceMode.value === 'reuse' && !props.bundleId) {
    errorMessage.value = '재사용할 저장 묶음이 없습니다. 새 수집으로 재생성하세요.'
    return
  }
  const payload: SectionRegenerationRequest = {
    workflow_id: props.workflowId,
    // 실제 생성 요청임을 서버에 명시한다(생략 시 mock 기본값으로 떨어진다).
    mode: 'live',
    fixture_id: fixtureId,
    source_mode: sourceMode.value,
  }
  const base = latestResult.value
  if (base) {
    payload.base_run_id = base.run_id
    payload.base_result_id = base.section_result_id
  }
  if (sourceMode.value === 'reuse' && props.bundleId) {
    payload.bundle_id = props.bundleId
  }
  // 다른 섹션은 **현재 화면의 저장 버전**을 그대로 이어받게 한다. 이 섹션의 결과는
  // 새로 만들 것이므로 목록에서 뺀다(같은 섹션 중복 선택 거부를 피한다).
  const keep = props.selectedResultIds.filter(
    (id) => id && id !== base?.section_result_id,
  )
  if (keep.length > 0) payload.selected_result_ids = keep

  pending.value = true
  errorMessage.value = null
  doneMessage.value = null
  const result = await previewRunsApi.regenerateSection(payload)
  pending.value = false
  if (!result.ok) {
    errorMessage.value = result.message
    return
  }
  doneMessage.value = describeOutcome(result.data, sourceMode.value)
  emit('regenerated', result.data)
}

/**
 * 응답이 실제로 무엇을 했는지 문장으로 만든다.
 *
 * 서버가 준 `no_model_call`·`bundle_reused`·`external_calls`를 그대로 읽고, 없으면
 * 요청한 모드를 사실로 단정하지 않는다(`—`). 화면이 전송 수를 추정하지 않는다.
 */
function describeOutcome(payload: SectionRunResponse, requested: SourceMode): string {
  // `external_calls`는 서버 예산의 `budget.model_used`, 즉 **모델 전송 수**다. 그래서
  // "외부 호출 n회"가 아니라 "모델 전송 n회"로 적는다(배당 API 전송 수가 아니다).
  const calls =
    typeof payload.external_calls === 'number'
      ? `모델 전송 ${payload.external_calls}회`
      : '모델 전송 수 미표시'
  // 모델 0회 여부는 **응답이** 정한다(`no_model_call`). 섹션 ID로 단정하지 않는다 —
  // 배당도 새 수집(refresh)에서는 자료 검색 모델이 실제로 호출된다.
  if (payload.no_model_call === true) {
    if (oddsSection.value) {
      // 배당 reuse의 모델 0회는 저장 자료 재사용의 결과다. 배당 API 조회는 이 응답과
      // 별도로 발생할 수 있으므로, 그 전송 수를 이 숫자로 대신하지 않는다.
      return (
        `모델 호출 없이 처리됐습니다(${calls}). 배당 조회는 이 응답과 별도로 발생할 수 ` +
        '있으며, 실제 배당 API 전송 수는 이 화면에서 확인하지 않습니다.'
      )
    }
    return `모델 호출 없이 처리됐습니다(${calls}).`
  }
  if (payload.bundle_reused === true) {
    return `저장된 정보 원문을 재사용했습니다. ${calls}.`
  }
  if (payload.bundle_reused === false || requested === 'refresh') {
    return `새 수집을 포함해 실행했습니다. ${calls}.`
  }
  return `실행 결과를 저장했습니다. ${calls}.`
}

/**
 * 저장된 응답만 다시 변환한다. 모델 호출 0회임을 화면이 먼저 알린다.
 *
 * 재처리 경로는 **모듈 결과 ID**를 쓴다(기존 `POST /results/{result_id}/replays`,
 * manifest §5). 섹션 결과 ID와 모듈 결과 ID는 다른 값이므로 섞지 않는다. 이 섹션
 * 결과에 모듈 결과 ID가 없으면 요청을 만들지 않고 그 사실을 알린다.
 */
async function reprocess() {
  const target = latestResult.value
  if (!target) {
    errorMessage.value = '재처리할 저장 결과가 없습니다.'
    return
  }
  const moduleResultId = target.result_ids.at(-1) ?? null
  if (moduleResultId === null) {
    errorMessage.value =
      '이 섹션 결과에는 저장된 모듈 응답 ID가 없어 재처리할 수 없습니다. 실행 검사 화면에서 모듈 결과를 확인하세요.'
    return
  }
  pending.value = true
  errorMessage.value = null
  doneMessage.value = null
  emit('reprocess', { resultId: moduleResultId, note: note.value || null })
  pending.value = false
}

/** 승인은 사용자가 직접 눌러야 한다. 이 컴포넌트는 승인을 자동 생성하지 않는다. */
function approve() {
  const target = selectedResult.value
  if (!target) return
  if (!target.approvable) {
    errorMessage.value =
      '이 결과는 승인 근거로 쓸 수 없습니다(모의 시연이거나 본문이 없음).'
    return
  }
  emit('approved', {
    sectionResultId: target.section_result_id,
    note: note.value.trim() === '' ? null : note.value.trim(),
  })
}
</script>

<template>
  <section class="regen" data-testid="section-regeneration">
    <header class="regen__head">
      <h3 class="regen__title">조정 · 재생성</h3>
      <p class="regen__note">
        다른 성공 섹션은 자동으로 다시 만들지 않습니다. 아래에서 고른 동작만 실행됩니다.
      </p>
    </header>

    <fieldset class="regen__choices" data-testid="regen-choices">
      <legend class="regen__legend">동작</legend>

      <label class="regen__choice">
        <input
          type="radio"
          name="regen-action"
          value="reuse"
          :checked="action === 'reuse'"
          :disabled="pending"
          data-testid="regen-action-reuse"
          @change="chooseAction('reuse')"
        />
        <span>
          <strong>저장된 정보 원문 재사용</strong>
          <span class="regen__hint">
            수집은 다시 하지 않고, 저장된 묶음으로 섹션 본문을 다시 만듭니다.
            <template v-if="oddsSection">
              배당은 저장된 정보 원문을 재사용하고, 남는 자리가 있으면 배당 API를 1회
              보완합니다. 이 재사용 경로는 모델 호출이 0회입니다.
            </template>
            <template v-else>모델 호출은 발생합니다.</template>
          </span>
          <span v-if="!reuseAvailable" class="regen__blocked" data-testid="regen-reuse-blocked">
            재사용할 정보 원문 묶음을 확인하지 못했습니다.
          </span>
        </span>
      </label>

      <label class="regen__choice">
        <input
          type="radio"
          name="regen-action"
          value="refresh"
          :checked="action === 'refresh'"
          :disabled="pending"
          data-testid="regen-action-refresh"
          @change="chooseAction('refresh')"
        />
        <span>
          <strong>새 수집으로 재생성</strong>
          <span class="regen__hint">{{ refreshWarning }}</span>
        </span>
      </label>

      <label class="regen__choice">
        <input
          type="radio"
          name="regen-action"
          value="reprocess"
          :checked="action === 'reprocess'"
          :disabled="pending"
          data-testid="regen-action-reprocess"
          @change="chooseAction('reprocess')"
        />
        <span>
          <strong>저장된 응답 재처리 (모델 전송 0회)</strong>
          <span class="regen__hint">{{ reprocessHint }}</span>
        </span>
      </label>
    </fieldset>

    <p v-if="fixtureMissing" class="regen__state" data-testid="regen-no-fixture">
      경기 식별자가 없어 재생성 요청을 보낼 수 없습니다.
    </p>

    <label class="regen__label" for="regen-note">메모 (선택)</label>
    <input
      id="regen-note"
      v-model="note"
      class="input"
      type="text"
      maxlength="1000"
      data-testid="regen-note"
    />

    <div class="regen__actions">
      <button
        type="button"
        class="button"
        :disabled="pending || (action === 'reuse' && !reuseAvailable) || (action !== 'reprocess' && fixtureMissing)"
        data-testid="regen-run"
        @click="regenerate"
      >
        {{ pending ? '요청 중…' : action === 'reprocess' ? '저장 응답으로 재처리' : '재생성 요청' }}
      </button>
    </div>

    <p v-if="errorMessage" class="regen__state regen__state--error" role="alert" data-testid="regen-error">
      {{ errorMessage }}
    </p>
    <p v-if="doneMessage" class="regen__state regen__state--ok" data-testid="regen-done">
      {{ doneMessage }}
    </p>

    <section v-if="orderedResults.length > 1" class="regen__compare" data-testid="regen-compare">
      <h4 class="regen__subtitle">버전 비교</h4>
      <p class="regen__versions">
        <button
          v-for="row in orderedResults"
          :key="row.section_result_id"
          type="button"
          class="regen__version"
          :aria-current="row.section_result_id === selectedResult?.section_result_id"
          :data-testid="`regen-version-${row.version}`"
          @click="selectResult(row.section_result_id)"
        >
          v{{ row.version }} · {{ row.mode_label }}
        </button>
      </p>

      <div v-if="comparison" class="regen__grid">
        <article class="regen__column" data-testid="regen-compare-base">
          <h5 class="regen__column-title measured">이전 v{{ comparison.base.version }}</h5>
          <p class="regen__column-meta measured">
            {{ comparison.base.mode_label }} · {{ comparison.base.quality }}
          </p>
          <p class="regen__column-body">{{ comparison.base.body }}</p>
        </article>
        <article class="regen__column" data-testid="regen-compare-target">
          <h5 class="regen__column-title measured">선택 v{{ comparison.target.version }}</h5>
          <p class="regen__column-meta measured">
            {{ comparison.target.mode_label }} · {{ comparison.target.quality }}
          </p>
          <p class="regen__column-body">{{ comparison.target.body }}</p>
        </article>
      </div>
      <p v-if="comparison?.bodyChanged" class="regen__hint" data-testid="regen-compare-body-changed">
        본문이 바뀌었습니다.
      </p>
      <p v-if="comparison?.sourcesChanged" class="regen__hint" data-testid="regen-compare-sources-changed">
        근거 출처가 바뀌었습니다.
      </p>
    </section>

    <section v-if="showApproval" class="regen__approval" data-testid="regen-approval">
      <h4 class="regen__subtitle">섹션 워크플로우 버전 승인</h4>
      <p class="regen__note">
        승인은 위 본문과 근거를 확인한 뒤 <strong>사용자가</strong> 누르는 동작입니다.
        이 화면은 승인 행을 자동으로 만들지 않습니다.
      </p>
      <p v-if="selectedResult && !selectedResult.approvable" class="regen__state" data-testid="regen-approval-blocked">
        이 결과는 승인 근거로 쓸 수 없습니다(모의 시연이거나 본문이 없음).
      </p>
      <button
        v-else
        type="button"
        class="button"
        :disabled="!selectedResult || canApprove === false"
        data-testid="regen-approve"
        @click="approve"
      >
        이 섹션 버전 승인
      </button>
    </section>
  </section>
</template>

<style scoped>
.regen {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
  border: var(--rule-hair) solid var(--color-rule);
  border-radius: var(--radius-panel);
  padding: var(--space-4);
}

.regen__head {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
}

.regen__title {
  margin: 0;
  font-size: var(--text-lg);
}

.regen__note,
.regen__hint,
.regen__label {
  margin: 0;
  font-size: var(--text-sm);
  color: var(--color-muted);
}

.regen__choices {
  border: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}

.regen__legend {
  padding: 0;
  font-size: var(--text-sm);
  color: var(--color-muted);
}

.regen__choice {
  display: flex;
  gap: var(--space-2);
  align-items: flex-start;
  padding: var(--space-2);
  border: var(--rule-hair) solid var(--color-rule);
  border-radius: var(--radius-control);
}

.regen__choice strong {
  display: block;
  font-weight: 500;
  color: var(--color-ink);
}

.regen__hint {
  display: block;
}

.regen__blocked {
  display: block;
  color: var(--color-bad);
  font-size: var(--text-sm);
}

.regen__actions {
  display: flex;
  gap: var(--space-2);
}

.regen__state {
  margin: 0;
  padding: var(--space-2) var(--space-3);
  border-radius: var(--radius-control);
  background: var(--color-paper-2);
  font-size: var(--text-sm);
}

.regen__state--error {
  background: var(--color-bad-soft);
  color: var(--color-bad);
}

.regen__state--ok {
  color: var(--color-ok);
}

.regen__compare,
.regen__approval {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  border-top: var(--rule-hair) solid var(--color-rule);
  padding-top: var(--space-3);
}

.regen__subtitle {
  margin: 0;
  font-size: var(--text-sm);
  color: var(--color-muted);
}

.regen__versions {
  margin: 0;
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-1);
}

.regen__version {
  padding: var(--space-1) var(--space-2);
  border: var(--rule-hair) solid var(--color-rule-2);
  border-radius: var(--radius-control);
  background: transparent;
  color: var(--color-ink-2);
  font-size: var(--text-sm);
  cursor: pointer;
}

.regen__version[aria-current='true'] {
  border-color: var(--color-accent);
  color: var(--color-accent);
}

.regen__grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(16rem, 1fr));
  gap: var(--space-3);
}

.regen__column {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
}

.regen__column-title,
.regen__column-meta {
  margin: 0;
  font-size: var(--text-sm);
  color: var(--color-muted);
}

.regen__column-body {
  margin: 0;
  white-space: pre-line;
  line-height: 1.6;
  color: var(--color-ink-2);
}
</style>
