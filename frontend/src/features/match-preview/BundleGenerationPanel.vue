<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { RouterLink } from 'vue-router'
import { previewRunsApi } from './api'
import MatchPreview from './MatchPreview.vue'
import type { FixtureCandidate } from './fixtures'
import type { BundlePreviewRunResponse } from './types'

const props = defineProps<{ fixture: FixtureCandidate | null }>()
const emit = defineEmits<{ select: [fixture: FixtureCandidate] }>()
const fixtureNumber = ref('')
const checkedFixture = ref<FixtureCandidate | null>(null)
const checking = ref(false)
const running = ref(false)
const message = ref<string | null>(null)
const result = ref<BundlePreviewRunResponse | null>(null)
const resultFixture = ref<FixtureCandidate | null>(null)
const readVersion = ref(0)
let lookupSequence = 0

const fixtureId = computed(() => {
  const input = fixtureNumber.value.trim()
  const value = Number(input)
  return /^\d+$/.test(input) && Number.isSafeInteger(value) && value > 0 ? value : null
})
const confirmed = computed(() => checkedFixture.value?.fixture_id === fixtureId.value
  ? checkedFixture.value : null)

watch(() => props.fixture, (fixture) => {
  if (!fixture || running.value) return
  lookupSequence++
  checking.value = false
  fixtureNumber.value = String(fixture.fixture_id)
  checkedFixture.value = fixture
  message.value = null
}, { immediate: true })

async function checkFixture() {
  if (checking.value || running.value) return
  if (fixtureId.value === null) {
    message.value = 'API-Football 경기 번호를 양의 정수로 입력하세요.'
    return
  }
  const sequence = ++lookupSequence
  const requestedId = fixtureId.value
  checking.value = true
  checkedFixture.value = null
  message.value = null
  const response = await previewRunsApi.fixture(requestedId)
  if (sequence !== lookupSequence) return
  checking.value = false
  if (!response.ok) {
    message.value = response.status === 404
      ? '이 번호의 저장된 경기가 없습니다. 경기 목록과 외부 경기 번호를 확인하세요.'
      : response.status === 503
      ? '저장된 경기 DB를 읽을 수 없습니다. 관리자에게 DB 연결·조회 권한 확인이 필요합니다.'
      : response.message
    return
  }
  if (fixtureId.value !== requestedId) return
  checkedFixture.value = response.data
  emit('select', response.data)
}

async function generate() {
  const fixture = confirmed.value
  if (!fixture?.selectable || running.value || checking.value) return
  running.value = true
  message.value = null
  result.value = null
  resultFixture.value = fixture
  const response = await previewRunsApi.runBundle(fixture.fixture_id)
  running.value = false
  if (!response.ok) {
    message.value = response.kind === 'network'
      ? '응답을 받지 못했습니다. 서버에 실행이 남아 있을 수 있으니 실행 목록을 먼저 확인하세요. 자동으로 다시 생성하지 않습니다.'
      : response.message
    return
  }
  result.value = response.data
  readVersion.value++
}
</script>

<template>
  <section class="generation" aria-labelledby="bundle-generation-title" data-testid="bundle-generation">
    <header>
      <h2 id="bundle-generation-title">경기 번호로 전체 프리뷰 생성</h2>
      <p>경기를 확인하고 생성하면 DB에 저장된 본문을 다시 읽어 보여줍니다.</p>
    </header>
    <form class="generation__form" @submit.prevent="checkFixture">
      <label for="bundle-fixture-number">API-Football 경기 번호</label>
      <div class="generation__controls">
        <input id="bundle-fixture-number" v-model="fixtureNumber" inputmode="numeric" autocomplete="off" :disabled="running" placeholder="경기 번호 입력" />
        <button type="submit" :disabled="checking || running">{{ checking ? '경기 확인 중…' : '경기 확인' }}</button>
      </div>
    </form>
    <div v-if="confirmed" class="generation__fixture" data-testid="bundle-confirmed-fixture">
      <strong>{{ confirmed.label }}</strong>
      <p>{{ confirmed.league_name }} · {{ confirmed.kickoff_at }} · 경기 번호 {{ confirmed.fixture_id }}</p>
      <p v-if="!confirmed.selectable">이 경기는 현재 실행할 수 없습니다. 저장된 경기 정보를 확인하세요.</p>
    </div>
    <button class="generation__start" type="button" :disabled="!confirmed?.selectable || running || checking" @click="generate" data-testid="bundle-generate">
      {{ running ? '프리뷰 생성 중…' : '이 경기 전체 프리뷰 생성' }}
    </button>
    <p v-if="running" role="status">{{ resultFixture?.label }} 프리뷰를 생성하고 저장하는 중입니다.</p>
    <p v-if="message" role="alert" class="generation__error">{{ message }}</p>
    <RouterLink to="/admin/runs">저장된 실행 목록</RouterLink>

    <section v-if="result" class="generation__result" aria-label="저장된 생성 결과" data-testid="bundle-saved-result">
      <h3>{{ resultFixture?.label }} · 저장된 결과</h3>
      <nav class="generation__links" aria-label="생성 결과 조회">
        <button type="button" @click="readVersion++">저장 결과 다시 읽기</button>
        <RouterLink :to="`/admin/preview/${result.run_id}`">프리뷰 별도 열기</RouterLink>
        <RouterLink :to="`/admin/runs?run=${encodeURIComponent(result.run_id)}`">요청·원문·섹션 재실행</RouterLink>
      </nav>
      <MatchPreview :key="`${result.run_id}:${readVersion}`" :run-id="result.run_id" />
      <details class="generation__diagnostics">
        <summary>실행 정보</summary>
        <p>실행 ID {{ result.run_id }} · 실제 호출 {{ result.external_calls }}회</p>
        <p>처리 상태 {{ result.status }} · 저장 품질 표기 {{ result.quality }}</p>
        <p v-if="result.unavailable_reason">{{ result.unavailable_reason }}</p>
        <ul v-if="Object.keys(result.section_unavailable).length">
          <li v-for="(reason, sectionId) in result.section_unavailable" :key="sectionId">{{ sectionId }}: {{ reason }}</li>
        </ul>
      </details>
    </section>
  </section>
</template>

<style scoped>
.generation { display: grid; gap: var(--space-4); padding: var(--space-5); border: 1px solid var(--color-rule); border-radius: var(--radius-panel); background: var(--color-paper); }
.generation header p, .generation__fixture p { color: var(--color-muted); margin-top: var(--space-2); }
.generation__form { display: grid; gap: var(--space-2); }
.generation__controls, .generation__links { display: flex; flex-wrap: wrap; gap: var(--space-3); align-items: center; }
.generation input { width: min(100%, 20rem); min-width: 0; padding: var(--space-3); border: 1px solid var(--color-rule); border-radius: var(--radius-control); color: var(--color-ink); background: var(--color-paper); font: inherit; }
.generation button { padding: var(--space-3) var(--space-4); border: 1px solid var(--color-rule); border-radius: var(--radius-control); color: var(--color-ink); background: var(--color-paper); font: inherit; cursor: pointer; }
.generation__start { justify-self: start; font-weight: 700; }
.generation button:disabled { opacity: 0.5; cursor: not-allowed; }
.generation a { color: var(--color-ink); text-underline-offset: 0.2em; }
.generation :is(button, input, a, summary):focus-visible { outline: 2px solid var(--color-ink); outline-offset: 3px; }
.generation__result { min-width: 0; border-top: 1px solid var(--color-rule); padding-top: var(--space-5); }
.generation__links { margin-block: var(--space-3); }
.generation__diagnostics { margin-top: var(--space-4); color: var(--color-muted); overflow-wrap: anywhere; }
.generation__error { color: var(--color-bad); }
</style>
