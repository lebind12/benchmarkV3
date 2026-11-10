<script setup lang="ts">
/**
 * 결과 버전 비교 — MP-02.
 *
 * 수정 전후 결과를 나란히 보여준다. 이전 버전은 삭제되지 않으므로 언제든 다시
 * 비교할 수 있다. 입력 해시가 바뀌면 "같은 입력이 아님"을 명시해 다른 입력의
 * 결과를 수정 전후 비교로 오해하지 않게 한다.
 */
import { computed, ref, watch } from 'vue'
import { previewRunsApi } from './api'
import type { VersionComparison } from './types'

const props = defineProps<{
  runId: string
  moduleExecutionId: string
}>()

const comparison = ref<VersionComparison | null>(null)
const loading = ref(false)
const errorMessage = ref<string | null>(null)
const selectedTarget = ref<number | null>(null)

async function load(targetVersion?: number) {
  loading.value = true
  errorMessage.value = null
  const result = await previewRunsApi.compareVersions(
    props.runId,
    props.moduleExecutionId,
    targetVersion === undefined ? {} : { targetVersion },
  )
  loading.value = false
  if (!result.ok) {
    errorMessage.value = result.message
    return
  }
  comparison.value = result.data
  selectedTarget.value = result.data.target.version
}

watch(
  () => [props.runId, props.moduleExecutionId],
  () => {
    void load()
  },
  { immediate: true },
)

const versions = computed(() => comparison.value?.versions_available ?? [])

function claimList(version: number | null): string[] {
  const current = comparison.value
  if (!current || version === null) return []
  const source = version === current.target.version ? current.target : current.base
  const claims = (source?.payload?.claims ?? []) as { claim_id: string; text: string }[]
  return claims.map((claim) => claim.text)
}
</script>

<template>
  <section class="compare" data-testid="run-version-compare">
    <header class="compare__head">
      <h3 class="compare__title">결과 버전 비교</h3>
      <label v-if="versions.length > 1" class="compare__select">
        <span class="visually-hidden">비교할 버전</span>
        <select
          class="input"
          :value="selectedTarget ?? undefined"
          data-testid="compare-version-select"
          @change="load(Number(($event.target as HTMLSelectElement).value))"
        >
          <option v-for="version in versions" :key="version" :value="version">
            v{{ version }}
          </option>
        </select>
      </label>
    </header>

    <p v-if="errorMessage" class="notice notice--error" role="alert" data-testid="compare-error">
      {{ errorMessage }}
    </p>

    <div v-else-if="loading" class="skeleton" aria-busy="true">
      <span class="visually-hidden">버전을 비교하는 중입니다.</span>
      <div class="skeleton__row" />
      <div class="skeleton__row" />
    </div>

    <template v-else-if="comparison">
      <p v-if="!comparison.base" class="module-note" data-testid="compare-single-version">
        이 모듈 실행에는 아직 저장된 결과가 한 버전뿐입니다. 수정 뒤 새 버전을 저장하면 여기에서
        나란히 비교할 수 있습니다.
      </p>

      <div v-else class="compare__grid">
        <article class="version" data-testid="compare-base">
          <h4 class="version__title measured">이전 결과 v{{ comparison.base.version }}</h4>
          <dl class="facts">
            <dt>상태</dt>
            <dd class="measured">{{ comparison.base.status }} / {{ comparison.base.quality }}</dd>
            <dt>구현 버전</dt>
            <dd class="measured">{{ comparison.base.implementation_version }}</dd>
            <dt>입력 해시</dt>
            <dd class="measured">{{ comparison.base.input_hash.slice(0, 16) }}…</dd>
          </dl>
          <ul class="version__claims">
            <li v-for="(text, index) in claimList(comparison.base.version)" :key="index">
              {{ text }}
            </li>
          </ul>
        </article>

        <article class="version" data-testid="compare-target">
          <h4 class="version__title measured">현재 결과 v{{ comparison.target.version }}</h4>
          <dl class="facts">
            <dt>상태</dt>
            <dd class="measured">{{ comparison.target.status }} / {{ comparison.target.quality }}</dd>
            <dt>구현 버전</dt>
            <dd class="measured">{{ comparison.target.implementation_version }}</dd>
            <dt>입력 해시</dt>
            <dd class="measured">{{ comparison.target.input_hash.slice(0, 16) }}…</dd>
          </dl>
          <ul class="version__claims">
            <li v-for="(text, index) in claimList(comparison.target.version)" :key="index">
              {{ text }}
            </li>
          </ul>
        </article>
      </div>

      <div v-if="comparison.base" class="compare__diff" data-testid="compare-diff">
        <p
          v-if="comparison.diff.input_hash.changed"
          class="notice notice--info"
          data-testid="compare-input-changed"
        >
          두 버전의 입력이 다릅니다. 이 비교는 같은 입력의 수정 전후 비교가 아닙니다.
        </p>
        <dl class="facts">
          <dt>추가된 근거</dt>
          <dd class="measured" data-testid="claims-added">
            {{ comparison.diff.claims_added.join(', ') || '없음' }}
          </dd>
          <dt>제거된 근거</dt>
          <dd class="measured">{{ comparison.diff.claims_removed.join(', ') || '없음' }}</dd>
          <dt>바뀐 근거</dt>
          <dd class="measured">{{ comparison.diff.claims_changed.join(', ') || '없음' }}</dd>
        </dl>
      </div>
    </template>
  </section>
</template>

<style scoped>
.compare {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}

.compare__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-3);
  flex-wrap: wrap;
}

.compare__title {
  font-size: var(--text-base);
}

.compare__select .input {
  min-height: 32px;
  width: auto;
}

.compare__grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(16rem, 1fr));
  gap: var(--space-3);
}

.version {
  border: var(--rule-hair) solid var(--color-rule);
  border-radius: var(--radius-control);
  padding: var(--space-3);
  background: var(--color-paper-3);
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}

.version__title {
  font-size: var(--text-sm);
  color: var(--color-accent);
}

.version__claims {
  margin: 0;
  padding-left: var(--space-4);
  font-size: var(--text-sm);
  color: var(--color-ink-2);
}

.facts {
  display: grid;
  grid-template-columns: minmax(6rem, 9rem) 1fr;
  gap: var(--space-1) var(--space-3);
  font-size: var(--text-sm);
  margin: 0;
}

.facts dt {
  color: var(--color-muted);
}

.facts dd {
  margin: 0;
  overflow-wrap: anywhere;
}

.compare__diff {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}

.module-note {
  font-size: var(--text-sm);
  color: var(--color-muted);
}
</style>
