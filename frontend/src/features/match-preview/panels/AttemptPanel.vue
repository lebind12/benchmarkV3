<script setup lang="ts">
/**
 * 시도 진단 패널 (MP-04).
 *
 * 이 패널은 **진단**이다. 승인 단위는 섹션 워크플로우 결과이며, 여기 보이는 시도
 * 하나하나가 승인 대상이 아니다.
 *
 * 보여주는 값:
 * - 논리 호출 ID와 시도 순번(0이 최초, 1 이상이 재시도)
 * - 결과(ok/error/unknown), HTTP 상태, 오류 분류·메시지
 * - 재시도 대기 시간(wait_ms)
 * - 제공자가 준 사용량. 주지 않았으면 `0`이 아니라 "제공되지 않음"으로 표시한다.
 *
 * 재시도는 실행기 하나가 소유한다. 그래서 429 뒤 성공한 경우에도 두 시도가 모두
 * 여기 남는다(성공만 골라 보여주지 않는다).
 */
import { computed } from 'vue'
import type { AttemptView } from '../types'

const props = defineProps<{
  attempts: AttemptView[]
}>()

const rows = computed(() =>
  [...props.attempts].sort(
    (left, right) =>
      left.logical_call_id.localeCompare(right.logical_call_id) ||
      left.attempt_ordinal - right.attempt_ordinal,
  ),
)

const retryCount = computed(() => rows.value.filter((row) => row.attempt_ordinal > 0).length)
const unknownCount = computed(() => rows.value.filter((row) => row.outcome === 'unknown').length)

function outcomeLabel(outcome: string): string {
  if (outcome === 'ok') return '성공'
  if (outcome === 'error') return '오류'
  if (outcome === 'unknown') return '결과 불명확'
  return outcome
}

function usageText(usage: Record<string, number | null> | null): string {
  if (!usage) return '제공되지 않음'
  const parts: string[] = []
  for (const [key, value] of Object.entries(usage)) {
    // 제공자가 주지 않은 값은 0이 아니라 unknown으로 표시한다.
    parts.push(`${key}: ${value === null || value === undefined ? '제공되지 않음' : value}`)
  }
  return parts.length > 0 ? parts.join(' · ') : '제공되지 않음'
}

function waitText(waitMs: number | null): string | null {
  if (waitMs === null || waitMs === undefined || waitMs === 0) return null
  return `${(waitMs / 1000).toFixed(1)}초 대기 후 재시도`
}
</script>

<template>
  <section class="attempts" data-testid="attempt-panel">
    <header class="attempts__head">
      <h4 class="attempts__title">시도 기록 (진단)</h4>
      <p class="attempts__hint">
        재시도는 실행기 하나가 소유하므로 실패한 시도도 지우지 않고 모두 남깁니다.
        승인은 이 시도 단위가 아니라 섹션 결과 단위로 이뤄집니다.
      </p>
      <p class="attempts__summary measured" data-testid="attempt-summary">
        시도 {{ rows.length }}건 · 재시도 {{ retryCount }}건<span
          v-if="unknownCount > 0"
        >
          · 결과 불명확 {{ unknownCount }}건</span
        >
      </p>
    </header>

    <p v-if="rows.length === 0" class="attempts__empty" data-testid="attempt-empty">
      이 실행에는 아직 저장된 시도가 없습니다.
    </p>

    <ol v-else class="attempts__list">
      <li
        v-for="row in rows"
        :key="row.attempt_id"
        class="attempts__row"
        :data-testid="`attempt-${row.logical_call_id}-${row.attempt_ordinal}`"
      >
        <div class="attempts__row-head">
          <span class="attempts__ordinal measured">
            {{ row.logical_call_id }} #{{ row.attempt_ordinal }}
          </span>
          <span
            class="attempts__outcome"
            :class="{
              'attempts__outcome--ok': row.outcome === 'ok',
              'attempts__outcome--error': row.outcome === 'error',
              'attempts__outcome--unknown': row.outcome === 'unknown',
            }"
            data-testid="attempt-outcome"
          >
            {{ outcomeLabel(row.outcome) }}
          </span>
          <span v-if="row.http_status !== null" class="attempts__status measured">
            HTTP {{ row.http_status }}
          </span>
        </div>
        <p class="attempts__meta measured">
          {{ row.provider }} / {{ row.model ?? '모델 미지정' }} · {{ row.mode }}
        </p>
        <p v-if="waitText(row.wait_ms)" class="attempts__wait" data-testid="attempt-wait">
          {{ waitText(row.wait_ms) }}
        </p>
        <p v-if="row.error_class" class="attempts__error" data-testid="attempt-error">
          {{ row.error_class }}: {{ row.error_message ?? '메시지 없음' }}
        </p>
        <p class="attempts__usage measured" data-testid="attempt-usage">
          사용량 {{ usageText(row.usage) }}
        </p>
      </li>
    </ol>
  </section>
</template>

<style scoped>
.attempts {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  border-top: var(--rule-hair) solid var(--color-rule);
  padding-top: var(--space-3);
}

.attempts__head {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
}

.attempts__title {
  font-size: var(--text-base);
}

.attempts__hint,
.attempts__empty {
  font-size: var(--text-sm);
  color: var(--color-muted);
}

.attempts__summary {
  font-size: var(--text-sm);
  color: var(--color-ink-2);
}

.attempts__list {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  margin: 0;
  padding: 0;
  list-style: none;
}

.attempts__row {
  border: var(--rule-hair) solid var(--color-rule-2);
  border-radius: var(--radius-control);
  padding: var(--space-2) var(--space-3);
  background: var(--color-paper-3);
  font-size: var(--text-sm);
}

.attempts__row-head {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: var(--space-2);
}

.attempts__ordinal {
  color: var(--color-ink);
}

.attempts__outcome {
  color: var(--color-ink-2);
}

.attempts__outcome--ok {
  color: var(--color-ink);
}

.attempts__outcome--error,
.attempts__outcome--unknown {
  color: var(--color-accent);
}

.attempts__status,
.attempts__meta,
.attempts__usage {
  color: var(--color-muted);
}

.attempts__wait {
  color: var(--color-ink-2);
}

.attempts__error {
  color: var(--color-accent);
  overflow-wrap: anywhere;
}
</style>
