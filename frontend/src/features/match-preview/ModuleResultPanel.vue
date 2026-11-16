<script setup lang="ts">
/**
 * 모듈 결과 패널 (공통) — MP-02.
 *
 * 등록된 모듈이면 `panel` 값에 따라 전용 표현을 붙일 수 있지만, 기본은 이 공통
 * 네 탭이다. 새 모듈을 추가해도 이 컴포넌트를 고치지 않아도 되게 만드는 것이
 * 목적이다. 전용 표현이 필요할 때만 별도 컴포넌트를 패널 값으로 연결한다.
 *
 * 원문 응답은 데이터로만 표시한다. HTML로 실행하지 않는다(`<pre>` 텍스트).
 */
import { computed, ref } from 'vue'
import { parseNestedModelJson, prettyJsonText } from './panels/players'
import type { ArtifactRef, ModuleInspection, PlayerSectionAttemptTraceView } from './types'

const props = defineProps<{
  module: ModuleInspection
}>()

const activeTab = ref<'request' | 'response' | 'transform' | 'next_input'>('request')

const tabs = computed(() => props.module.tabs_meta ?? [])
const processing = computed(() => props.module.player_section_processing ?? null)

function processingTraceFor(attemptOrdinal: number): PlayerSectionAttemptTraceView | null {
  const traces = processing.value?.attempts ?? []
  return traces.find((item) => item.attempt_ordinal === attemptOrdinal) ?? null
}

const panelLabel = computed(() =>
  props.module.panel.registered
    ? props.module.panel.display_name
    : `${props.module.panel.display_name} (등록부에 없음)`,
)

function pretty(value: unknown): string {
  if (value === null || value === undefined) return '—'
  if (typeof value === 'string') return value
  try {
    return JSON.stringify(value, null, 2)
  } catch {
    return String(value)
  }
}

function artifactText(artifact: ArtifactRef | null | undefined): string {
  if (!artifact) return '—'
  if (artifact.status === 'expired') {
    return artifact.detail ?? '보관 기간이 지나 원문을 열 수 없습니다.'
  }
  // artifact.body는 직렬화된 JSON **문자열**이다. 그대로 넣으면 압축된 한 줄이 나오므로
  // 표시 경계에서 파싱해 들여쓰기한다. JSON이 아니면 원문을 그대로 쓴다.
  return prettyJsonText(artifact.body)
}

/**
 * 전체 응답 안에서 **모델이 생성한 JSON 텍스트**를 찾는다.
 *
 * Google 응답의 `candidates[].content.parts[].text`는 문자열이며, 그 안에 선수 선정
 * JSON이 들어 있는 경우가 있다. 전체 원문 보기는 이 값을 **문자열 그대로** 두고,
 * 사용자가 따로 읽고 싶을 때만 이 목록을 펼쳐 보여 준다(원문 변조 없음).
 */
function modelJsonParts(artifact: ArtifactRef | null | undefined): string[] {
  if (!artifact || artifact.status === 'expired' || typeof artifact.body !== 'string') {
    return []
  }
  let parsed: unknown
  try {
    parsed = JSON.parse(artifact.body)
  } catch {
    return []
  }
  if (typeof parsed !== 'object' || parsed === null) return []
  const candidates = (parsed as { candidates?: unknown }).candidates
  if (!Array.isArray(candidates)) return []
  const found: string[] = []
  for (const candidate of candidates) {
    if (typeof candidate !== 'object' || candidate === null) continue
    const content = (candidate as { content?: unknown }).content
    if (typeof content !== 'object' || content === null) continue
    const parts = (content as { parts?: unknown }).parts
    if (!Array.isArray(parts)) continue
    for (const part of parts) {
      if (typeof part !== 'object' || part === null) continue
      const text = (part as { text?: unknown }).text
      if (typeof text !== 'string') continue
      const formatted = parseNestedModelJson(text)
      if (formatted !== null) found.push(formatted)
    }
  }
  return found
}

function usageText(usage: Record<string, number | null> | null): string {
  if (!usage) return '제공되지 않음'
  const parts = Object.entries(usage)
    .filter(([, value]) => value !== null && value !== undefined)
    .map(([key, value]) => `${key}=${value}`)
  return parts.length > 0 ? parts.join(' · ') : '제공되지 않음'
}
</script>

<template>
  <section class="module-card" data-testid="module-result-panel">
    <header class="module-card__head">
      <div class="module-card__title-row">
        <h2 class="module-card__title" data-testid="module-panel-title">{{ panelLabel }}</h2>
        <span class="chip" data-testid="module-mode">{{ module.run_mode.label }}</span>
        <span
          class="chip"
          :class="{ 'chip--quiet': !module.panel.available }"
          data-testid="module-availability"
        >
          {{ module.panel.available ? '실행 가능' : '사용할 수 없음' }}
        </span>
      </div>
      <p class="module-card__meta measured" data-testid="module-identity">
        {{ module.module_id }} · 실행 {{ module.module_execution_id.slice(0, 8) }} · 시도
        {{ module.attempt_count }}회 · 재시도 {{ module.retry_count }}회
      </p>
      <p v-if="!module.panel.available && module.panel.unrunnable_reason" class="module-card__note">
        {{ module.panel.unrunnable_reason }}
      </p>
      <p class="module-card__note">{{ module.run_mode.note }}</p>
    </header>

    <div class="tabs" role="tablist" :aria-label="`${panelLabel} 호출 검사 탭`">
      <button
        v-for="tab in tabs"
        :key="tab.id"
        class="tabs__button"
        type="button"
        role="tab"
        :aria-selected="activeTab === tab.id"
        :data-testid="`tab-${tab.id}`"
        @click="activeTab = tab.id"
      >
        {{ tab.label }}
      </button>
    </div>

    <!-- 요청 -->
    <div v-if="activeTab === 'request'" class="tab-panel" data-testid="panel-request">
      <p v-if="module.tabs.request.note" class="module-card__note">
        {{ module.tabs.request.note }}
      </p>
      <div
        v-for="attempt in module.tabs.request.attempts"
        :key="attempt.attempt_id"
        class="attempt"
      >
        <h3 class="attempt__title">
          시도 {{ attempt.attempt_ordinal + 1 }} · {{ attempt.provider }}
          <span v-if="attempt.model" class="measured">/ {{ attempt.model }}</span>
        </h3>
        <dl class="facts">
          <dt>논리 호출</dt>
          <dd class="measured">{{ attempt.logical_call_id }}</dd>
          <dt>프롬프트 버전</dt>
          <dd class="measured">{{ attempt.request_spec.prompt_version ?? '—' }}</dd>
          <dt>계약 버전</dt>
          <dd class="measured">{{ attempt.request_spec.contract_version }}</dd>
          <dt>비밀값 참조</dt>
          <dd class="measured">
            {{ attempt.request_spec.secret_refs.length > 0
              ? attempt.request_spec.secret_refs.join(', ')
              : '없음' }}
          </dd>
        </dl>
        <h4 class="attempt__subhead">요청 파라미터</h4>
        <pre class="code" data-testid="request-parameters">{{
          pretty(attempt.request_spec.parameters)
        }}</pre>
        <h4 class="attempt__subhead">실제 전송 본문 (비밀값 제거)</h4>
        <pre class="code" data-testid="request-body">{{ artifactText(attempt.request_body) }}</pre>
      </div>
    </div>

    <!-- 응답 -->
    <div v-else-if="activeTab === 'response'" class="tab-panel" data-testid="panel-response">
      <p v-if="module.tabs.response.note" class="module-card__note">
        {{ module.tabs.response.note }}
      </p>
      <div
        v-for="attempt in module.tabs.response.attempts"
        :key="attempt.attempt_id"
        class="attempt"
      >
        <h3 class="attempt__title">
          시도 {{ attempt.attempt_ordinal + 1 }}
          <span
            v-if="processing && processing.adopted_attempt_ordinal === attempt.attempt_ordinal"
            class="attempt__badge attempt__badge--adopted"
            data-testid="attempt-adopted-badge"
          >
            채택 시도
          </span>
          <span
            v-if="processingTraceFor(attempt.attempt_ordinal)?.regeneration_triggered"
            class="attempt__badge attempt__badge--regen"
            data-testid="attempt-regeneration-badge"
          >
            재생성 유발 ({{ processingTraceFor(attempt.attempt_ordinal)?.regeneration_reason }})
          </span>
        </h3>
        <dl class="facts">
          <dt>결과</dt>
          <dd class="measured" data-testid="response-outcome">{{ attempt.outcome }}</dd>
          <dt>HTTP 상태</dt>
          <dd class="measured">{{ attempt.http_status ?? '—' }}</dd>
          <dt>오류 분류</dt>
          <dd>{{ attempt.error_class ?? '없음' }}</dd>
          <dt>사용량</dt>
          <dd class="measured" data-testid="response-usage">{{ usageText(attempt.usage) }}</dd>
        </dl>
        <h4 class="attempt__subhead">
          Google API 전체 응답 (정렬 보기 · 비밀값 제거 · 메타데이터 포함)
        </h4>
        <p class="module-card__note">
          제공자가 보낸 응답 객체를 들여쓰기해 그대로 보여 줍니다(candidates,
          grounding_metadata, sdk_http_response, usage_metadata 등). 필드를 줄이거나
          요약하지 않습니다. 검색 메타데이터는
          <code>candidates[].grounding_metadata</code>에 있습니다.
        </p>
        <p
          v-if="attempt.content?.status === 'expired'"
          class="notice notice--info"
          data-testid="response-expired"
        >
          {{ attempt.content.detail }}
        </p>
        <pre class="code code--readable" data-testid="response-body">{{ artifactText(attempt.content) }}</pre>

        <!--
          전체 응답 안의 `candidates[].content.parts[].text`는 **문자열**이다(모델이 만든
          JSON이 문자열로 들어 있다). 위 원문 보기에서는 그 값을 문자열 그대로 두고,
          읽고 싶은 사용자를 위해 여기서만 따로 파싱해 펼쳐 보여 준다. 두 뷰의 이름을
          섞지 않는다.
        -->
        <details
          v-if="modelJsonParts(attempt.content).length"
          class="model-json"
          data-testid="response-model-json"
        >
          <summary>모델이 생성한 JSON (전체 응답 안의 텍스트를 따로 정렬)</summary>
          <p class="module-card__note">
            위 전체 응답의 <code>candidates[].content.parts[].text</code> 값입니다.
            전체 응답을 대신하는 것이 아니라, 그 안의 문자열을 읽기 좋게 편 것입니다.
          </p>
          <pre
            v-for="(part, index) in modelJsonParts(attempt.content)"
            :key="index"
            class="code code--readable"
            data-testid="response-model-json-body"
          >{{ part }}</pre>
        </details>
      </div>
    </div>

    <!-- 변환 -->
    <div v-else-if="activeTab === 'transform'" class="tab-panel" data-testid="panel-transform">
      <p v-if="module.tabs.transform.note" class="module-card__note">
        {{ module.tabs.transform.note }}
      </p>
      <template v-else>
        <dl class="facts">
          <dt>결과 버전</dt>
          <dd class="measured" data-testid="transform-version">
            v{{ module.tabs.transform.version }}
          </dd>
          <dt>실행 상태</dt>
          <dd class="measured">{{ module.tabs.transform.status }}</dd>
          <dt>품질 상태</dt>
          <dd class="measured">{{ module.tabs.transform.quality }}</dd>
          <dt>입력 해시</dt>
          <dd class="measured">{{ module.tabs.transform.input_hash?.slice(0, 16) }}…</dd>
          <dt>구현 버전</dt>
          <dd class="measured">{{ module.tabs.transform.implementation_version ?? '—' }}</dd>
        </dl>

        <h4 class="attempt__subhead">추출한 근거 (채택·제외 사유 포함)</h4>
        <ul v-if="module.tabs.transform.claims.length" class="claims" data-testid="transform-claims">
          <li v-for="claim in module.tabs.transform.claims" :key="claim.claim_id" class="claim">
            <p class="claim__text">{{ claim.text }}</p>
            <p class="claim__meta measured">
              {{ claim.claim_id }} · {{ claim.kind }} · <strong>{{ claim.decision }}</strong>
            </p>
            <p v-if="claim.decision_reason" class="claim__reason">{{ claim.decision_reason }}</p>
          </li>
        </ul>
        <p v-else class="module-card__note">채택된 근거가 없습니다.</p>

        <h4 class="attempt__subhead">자료 확보 상태</h4>
        <ul class="coverage" data-testid="transform-coverage">
          <li v-for="entry in module.tabs.transform.coverage" :key="entry.topic">
            <span class="measured">{{ entry.topic }}</span> — {{ entry.state }}
            <span v-if="entry.detail" class="module-card__note"> {{ entry.detail }}</span>
          </li>
        </ul>

        <h4 class="attempt__subhead">내부 진단 (독자용 프리뷰에 넣지 않음)</h4>
        <ul class="diagnostics" data-testid="transform-diagnostics">
          <li v-for="(line, index) in module.tabs.transform.diagnostics" :key="index">
            {{ line }}
          </li>
        </ul>
      </template>
    </div>

    <!-- 다음 입력 -->
    <div v-else class="tab-panel" data-testid="panel-next-input">
      <p v-if="module.tabs.next_input.note" class="module-card__note">
        {{ module.tabs.next_input.note }}
      </p>
      <template v-else>
        <dl class="facts">
          <dt>다음 모듈</dt>
          <dd class="measured">{{ module.tabs.next_input.target_module_id ?? '없음' }}</dd>
          <dt>전달한 결과 버전</dt>
          <dd class="measured" data-testid="next-input-version">
            v{{ module.tabs.next_input.latest_result_version }}
            {{ module.tabs.next_input.uses_latest_version ? '(최신 버전)' : '(이전 버전)' }}
          </dd>
        </dl>
        <h4 class="attempt__subhead">실제 전달 값</h4>
        <dl class="facts">
          <template v-for="entry in module.tabs.next_input.values" :key="entry.key">
            <dt class="measured">{{ entry.key }}</dt>
            <dd class="measured">{{ pretty(entry.value) }}</dd>
          </template>
        </dl>
      </template>
    </div>
  </section>
</template>

<style scoped>
.module-card {
  background: var(--color-paper-3);
  border: var(--rule-hair) solid var(--color-rule);
  border-radius: var(--radius-panel);
  padding: var(--space-4);
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}

.module-card__head {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}

.module-card__title-row {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  flex-wrap: wrap;
}

.module-card__title {
  font-size: var(--text-lg);
}

.module-card__meta,
.module-card__note {
  font-size: var(--text-sm);
  color: var(--color-muted);
}

.chip {
  font-size: var(--text-sm);
  padding: 0 var(--space-2);
  border-radius: var(--radius-control);
  border: var(--rule-hair) solid var(--color-rule-2);
  color: var(--color-ink-2);
}

.chip--quiet {
  color: var(--color-muted);
  border-style: dashed;
}

.tabs {
  display: flex;
  gap: var(--space-1);
  flex-wrap: wrap;
  border-bottom: var(--rule-hair) solid var(--color-rule);
  padding-bottom: var(--space-1);
}

.tabs__button {
  background: transparent;
  border: var(--rule-hair) solid transparent;
  border-radius: var(--radius-control);
  color: var(--color-muted);
  font-family: var(--font-body);
  font-size: var(--text-sm);
  padding: var(--space-1) var(--space-3);
  cursor: pointer;
}

.tabs__button[aria-selected='true'] {
  color: var(--color-accent);
  border-color: var(--color-rule-2);
  background: var(--color-paper-2);
}

.tab-panel {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}

.attempt {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}

.attempt__title {
  font-size: var(--text-base);
  color: var(--color-ink);
}

.attempt__subhead {
  font-size: var(--text-sm);
  color: var(--color-muted);
  font-weight: 500;
}

.facts {
  display: grid;
  grid-template-columns: minmax(8rem, 12rem) 1fr;
  gap: var(--space-1) var(--space-3);
  font-size: var(--text-sm);
  margin: 0;
}

.facts dt {
  color: var(--color-muted);
}

.facts dd {
  margin: 0;
  color: var(--color-ink-2);
  overflow-wrap: anywhere;
}

.code {
  margin: 0;
  padding: var(--space-3);
  background: var(--color-paper);
  border: var(--rule-hair) solid var(--color-rule);
  border-radius: var(--radius-control);
  font-family: var(--font-measured);
  font-size: var(--text-sm);
  line-height: 1.5;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
  max-height: 22rem;
  overflow-y: auto;
}

/*
 * 전체 응답은 필드가 깊고 길다. 들여쓰기를 유지한 채 더 넓게 보여 주고, 아주 긴
 * 문자열 한 줄이 레이아웃을 밀지 않도록 감싼다(스크롤은 그대로).
 */
.code--readable {
  max-height: 32rem;
  tab-size: 2;
}

.model-json {
  display: grid;
  gap: var(--space-2);
  margin-top: var(--space-2);
}

.model-json > summary {
  cursor: pointer;
  font-size: var(--text-sm);
}

.claims,
.coverage,
.diagnostics {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  font-size: var(--text-sm);
}

.claim {
  border-left: 2px solid var(--color-rule-2);
  padding-left: var(--space-3);
}

.claim__text {
  color: var(--color-ink);
}

.claim__meta {
  color: var(--color-muted);
}

.claim__reason {
  color: var(--color-ink-2);
}

@media (max-width: 40rem) {
  .facts {
    grid-template-columns: 1fr;
  }
}
</style>
