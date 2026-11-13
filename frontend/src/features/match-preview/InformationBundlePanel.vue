<script setup lang="ts">
/**
 * 정보 원문 묶음 패널 (PS-04).
 *
 * 관리자 검사 화면에서 "이 본문이 어떤 자료로 만들어졌는가"를 확인하는 영역이다.
 * 계약: `docs/implementation/match-preview/section-interface-manifest.md` §1·§4.
 * 승인 단위는 이 패널이 아니라 섹션 워크플로우 결과이며, 이 패널은 승인을 만들지 않는다.
 *
 * 순서(사용자 확정):
 *
 * 1. 저장된 **본문과 근거**는 부모(`SectionRunView`/`RunInspector`)가 먼저 보여준다.
 * 2. 이 패널은 그 아래에서 **출처 목록**을 먼저 보여준다(접히지 않은 채).
 * 3. 전달 구간·DB 스냅샷·배당·조사 묶음은 **펼치는 진단**이다.
 *
 * 지키는 것:
 *
 * - 조회 전용. 이 컴포넌트는 어떤 실행·재생성도 스스로 시작하지 않는다.
 * - `available=false`면 서버가 준 사유를 그대로 보여준다(빈 묶음을 만들지 않음).
 * - 실패한 출처를 "가져온 자료"로 그리지 않는다. 사유를 그대로 쓴다.
 * - **후보와 실제 전달을 구분한다.** `sources[].passages`/`available_passages`는 수집된
 *   **후보**이며, "모델에 실제로 전달됨"은 `section_deliveries`의 기록으로만 표시한다.
 *   배당(`model_delivered=false`)은 전달됐다고 쓰지 않는다.
 * - 전문은 `body_artifact_id` 아티팩트에 있고 묶음에 없다. 없는 전문을 받아오는
 *   가상 endpoint를 호출하지 않는다.
 * - 비밀값·계정·쿠키는 표시하지 않는다(타입에도 없다).
 */
import { computed, ref, watch } from 'vue'
import { previewRunsApi } from './api'
import {
  deliveredPassageIds,
  failedSources,
  isBundleEmpty,
  parseInformationBundle,
  redirectNote,
  sourceHref,
  usableSources,
  type BundleSectionDeliveryView,
  type BundleSourceView,
  type InformationBundleView,
} from './informationBundle'

const props = defineProps<{
  runId: string
  /** 부모가 이미 받은 묶음이 있으면 다시 조회하지 않는다. */
  provided?: InformationBundleView | null
}>()

/**
 * 조회 결과를 부모에게 알린다. 부모(재생성 패널)는 이 값의 묶음 ID로 "저장된 정보
 * 원문 재사용"을 열 수 있다. 이 이벤트는 **조회 결과 통지**이며 실행 시작이 아니다.
 */
const emit = defineEmits<{
  (event: 'loaded', payload: InformationBundleView | null): void
}>()

const loading = ref(false)
const errorMessage = ref<string | null>(null)
const bundle = ref<InformationBundleView | null>(null)

const view = computed<InformationBundleView | null>(() => props.provided ?? bundle.value)

const okSources = computed<BundleSourceView[]>(() => (view.value ? usableSources(view.value) : []))
const blockedSources = computed<BundleSourceView[]>(() =>
  view.value ? failedSources(view.value) : [],
)
const dbSnapshot = computed(() => view.value?.dbSnapshot ?? null)
const odds = computed(() => view.value?.odds ?? null)
const diagnostics = computed(() => view.value?.diagnostics ?? [])
const network = computed(() => view.value?.networkUsage ?? null)
const groups = computed(() => view.value?.discoveryGroups ?? [])
const deliveries = computed<BundleSectionDeliveryView[]>(
  () => view.value?.sectionDeliveries ?? [],
)
/** 모델 호출로 실제 전달된 섹션만. 배당(model_delivered=false)은 여기 없다. */
const modelDeliveries = computed(() => deliveries.value.filter((row) => row.modelDelivered))
const candidateCount = computed(() => view.value?.availablePassages.length ?? 0)
const deliveredIds = computed(() =>
  view.value ? deliveredPassageIds(view.value) : new Set<string>(),
)
const nothing = computed(() => (view.value ? isBundleEmpty(view.value) : true))
/**
 * 검색 단계가 실제로 확보한 자료. **자료 유형 라벨을 그대로** 보여준다.
 * 검색 스니펫이 없는데 모델 산문을 스니펫이라고 부르지 않기 위해 여기서도 합치지 않는다.
 */
const searchFindings = computed(() => view.value?.searchFindings ?? [])
const snippetCount = computed(
  () => searchFindings.value.filter((item) => item.isSearchSnippet).length,
)
/** 검색을 사용한 AI 조사 요약 건수. 스니펫 건수와 절대 합치지 않는다. */
const summaryCount = computed(
  () => searchFindings.value.filter((item) => item.isAiSummary).length,
)

/** 후보 구간이 실제로 전달됐는지. 전달 기록이 없으면 표시하지 않는다(추정 금지). */
function passageStatus(passageId: string | null): 'delivered' | 'candidate' | null {
  if (passageId === null) return null
  if (deliveredIds.value.has(passageId)) return 'delivered'
  return deliveries.value.length > 0 ? 'candidate' : null
}

const honestyWarnings = computed<string[]>(() => {
  const flags = view.value?.honestyFlags
  if (!flags) return []
  const warnings: string[] = []
  if (flags.browserUsed) warnings.push('브라우저 렌더를 사용했다고 보고되었습니다(계약상 false여야 함).')
  if (flags.crossCheckedWithDb) {
    warnings.push('기사와 DB를 교차 대조했다고 보고되었습니다(계약상 false여야 함).')
  }
  if (flags.requiresGroundingChunks) {
    warnings.push('Google 인용 메타데이터를 필수로 요구했다고 보고되었습니다(계약상 false여야 함).')
  }
  return warnings
})

async function load() {
  if (props.provided !== undefined && props.provided !== null) {
    emit('loaded', props.provided)
    return
  }
  if (!props.runId) {
    bundle.value = null
    emit('loaded', null)
    return
  }
  loading.value = true
  errorMessage.value = null
  const result = await previewRunsApi.informationBundle(props.runId)
  loading.value = false
  if (!result.ok) {
    // 조회 경로 자체가 아직 없는 경우(404)와 실행이 없는 경우를 구분해 말한다.
    // UI 완료와 API 실연결은 다르다 — 이 화면은 계획된 경로를 읽으려 한 결과를 숨기지 않는다.
    errorMessage.value =
      result.status === 404
        ? '정보 원문 조회 경로가 아직 서버에 없거나(계획 §4) 이 실행이 없습니다. 실행 상세의 아티팩트로 확인할 수 있습니다.'
        : result.message
    bundle.value = null
    emit('loaded', null)
    return
  }
  bundle.value = parseInformationBundle(result.data)
  emit('loaded', bundle.value)
}

watch(
  () => [props.runId, props.provided] as const,
  () => {
    void load()
  },
  { immediate: true },
)

/** 출처를 사람이 읽는 이름으로. 제목이 없으면 호스트, 그것도 없으면 ID를 쓴다. */
function sourceLabel(source: BundleSourceView): string {
  if (source.title) return source.title
  const href = sourceHref(source)
  if (href) {
    try {
      return new URL(href).host
    } catch {
      return href
    }
  }
  return source.sourceId
}

function networkLine(): string | null {
  const usage = network.value
  if (!usage) return null
  const parts: string[] = []
  if (usage.httpUsed !== null) {
    const limit = usage.httpLimit !== null ? ` / 상한 ${usage.httpLimit}` : ''
    parts.push(`HTTP ${usage.httpUsed}회${limit}`)
  }
  if (usage.apiUsed !== null) parts.push(`API ${usage.apiUsed}회`)
  if (usage.httpFailed !== null && usage.httpFailed > 0) parts.push(`실패 ${usage.httpFailed}회`)
  if (usage.redirects !== null && usage.redirects > 0) parts.push(`리다이렉트 ${usage.redirects}회`)
  if (usage.note) parts.push(usage.note)
  return parts.length > 0 ? parts.join(' · ') : null
}
</script>

<template>
  <section class="bundle" data-testid="information-bundle">
    <header class="bundle__head">
      <h3 class="bundle__title">정보 원문</h3>
      <p class="bundle__note">
        이 섹션 본문을 만들 때 쓰인 <strong>저장된 자료</strong>입니다. 본문·근거는 위에 먼저
        표시되고, 여기서는 출처와 전달 구간을 확인합니다. 이 화면은 조회만 하며 새 수집·모델
        호출을 일으키지 않습니다.
      </p>
      <dl v-if="view && !nothing" class="bundle__facts measured">
        <template v-if="view.bundleId">
          <dt>묶음</dt>
          <dd data-testid="bundle-id">{{ view.bundleId }}</dd>
        </template>
        <template v-if="view.bundleVersion">
          <dt>묶음 버전</dt>
          <dd>{{ view.bundleVersion }}</dd>
        </template>
        <template v-if="view.mode">
          <dt>묶음 방식</dt>
          <dd data-testid="bundle-mode">{{ view.mode }}</dd>
        </template>
        <template v-if="view.collectedAt">
          <dt>수집 시각</dt>
          <dd>{{ view.collectedAt }}</dd>
        </template>
        <template v-if="candidateCount > 0">
          <dt>전달 후보</dt>
          <dd data-testid="bundle-candidate-count">
            구간 {{ candidateCount }}개<template v-if="view.availableChars !== null"> · {{ view.availableChars }}자</template>
            <span class="bundle__source-meta"> (수집된 후보이며 실제 전달 기록은 아래)</span>
          </dd>
        </template>
        <template v-if="modelDeliveries.length">
          <dt>실제 모델 전달</dt>
          <dd data-testid="bundle-delivery-count">{{ modelDeliveries.length }}개 섹션</dd>
        </template>
        <template v-if="networkLine()">
          <dt>네트워크</dt>
          <dd data-testid="bundle-network">{{ networkLine() }}</dd>
        </template>
      </dl>
    </header>

    <p v-if="loading" class="bundle__state" data-testid="bundle-loading">
      정보 원문을 읽는 중입니다.
    </p>
    <p v-else-if="errorMessage" class="bundle__state bundle__state--error" role="alert" data-testid="bundle-error">
      {{ errorMessage }}
    </p>
    <template v-else-if="nothing">
      <p class="bundle__state" data-testid="bundle-empty">
        <template v-if="view?.unavailableReason">{{ view.unavailableReason }}</template>
        <template v-else>저장된 정보 원문이 없습니다. 이 실행에 묶음이 남아 있지 않습니다.</template>
      </p>
    </template>

    <template v-else>
      <p v-for="(warning, index) in honestyWarnings" :key="`warn-${index}`" class="bundle__state bundle__state--error" data-testid="bundle-honesty-warning">
        {{ warning }}
      </p>

      <div v-if="okSources.length" class="bundle__sources" data-testid="bundle-sources">
        <h4 class="bundle__subtitle">가져온 출처 ({{ okSources.length }}건)</h4>
        <ul class="bundle__source-list">
          <li
            v-for="source in okSources"
            :key="source.sourceId"
            class="bundle__source"
            data-testid="bundle-source"
          >
            <p class="bundle__source-head">
              <a
                v-if="sourceHref(source)"
                class="bundle__source-link"
                :href="sourceHref(source) ?? undefined"
                rel="noreferrer noopener"
                target="_blank"
              >{{ sourceLabel(source) }}</a>
              <span v-else>{{ sourceLabel(source) }}</span>
              <span v-if="source.nature" class="bundle__chip" data-testid="bundle-source-nature">
                {{ source.nature }}
              </span>
            </p>
            <p class="bundle__source-meta measured">
              <span v-if="source.method">{{ source.method }}</span>
              <span v-if="source.httpStatus !== null"> · HTTP {{ source.httpStatus }}</span>
              <span v-if="source.bodyChars !== null"> · {{ source.bodyChars }}자</span>
              <span v-if="source.passages.length"> · 전달 {{ source.passages.length }}구간</span>
              <span v-if="source.capturedAt"> · 수집 {{ source.capturedAt }}</span>
            </p>
            <p v-if="redirectNote(source)" class="bundle__source-note">{{ redirectNote(source) }}</p>
          </li>
        </ul>
      </div>

      <div v-if="blockedSources.length" class="bundle__sources" data-testid="bundle-failed-sources">
        <h4 class="bundle__subtitle">가져오지 못한 출처 ({{ blockedSources.length }}건)</h4>
        <ul class="bundle__source-list">
          <li
            v-for="source in blockedSources"
            :key="source.sourceId"
            class="bundle__source bundle__source--failed"
            data-testid="bundle-failed-source"
          >
            <p class="bundle__source-head">
              <span>{{ sourceLabel(source) }}</span>
              <span v-if="source.httpStatus !== null" class="bundle__chip">HTTP {{ source.httpStatus }}</span>
              <span v-if="source.nature" class="bundle__chip">{{ source.nature }}</span>
            </p>
            <p class="bundle__source-note">
              {{ source.failure ?? '본문 구간을 확보하지 못했습니다.' }}
            </p>
          </li>
        </ul>
      </div>

      <!--
        검색 단계가 **실제로 돌려준** 자료. 각 줄에 자료 유형 라벨을 그대로 붙인다.
        요약문 필드가 응답에 없으면 "검색 요약문"이라는 이름을 쓰지 않는다.
      -->
      <div v-if="searchFindings.length" class="bundle__sources" data-testid="bundle-search-findings">
        <h4 class="bundle__subtitle">
          검색 단계 자료 ({{ searchFindings.length }}건 · AI 조사 요약 {{ summaryCount }}건 ·
          도구 반환 요약문 {{ snippetCount }}건)
        </h4>
        <p class="bundle__source-note" data-testid="bundle-search-semantics">
          자료 유형별로 구분해 표시합니다. 검색을 사용한 AI 조사 요약
          {{ summaryCount }}건, 검색 도구가 직접 반환한 요약문 {{ snippetCount }}건,
          출처 메타·모델이 쓴 문장은 각자 라벨로 표시됩니다. AI 조사 요약은 기사 원문이
          아니며, 검색 도구가 반환한 요약문과 같은 이름으로 부르지 않습니다.
        </p>
        <ul class="bundle__source-list">
          <li
            v-for="finding in searchFindings"
            :key="finding.findingId"
            class="bundle__source"
            data-testid="bundle-search-finding"
          >
            <p class="bundle__source-head">
              <span class="bundle__chip" data-testid="bundle-search-label">{{ finding.label }}</span>
              <span v-if="finding.domain" class="bundle__source-meta"> · {{ finding.domain }}</span>
              <span v-if="finding.title && finding.title !== finding.domain" class="bundle__source-meta">
                · {{ finding.title }}
              </span>
            </p>
            <p v-if="finding.content" class="bundle__source-note">{{ finding.content }}</p>
            <p v-else class="bundle__source-note">
              주소만 반환되었습니다. 기사 내용은 이 자료에 없습니다.
            </p>
            <p
              v-if="finding.isAiSummary"
              class="bundle__source-meta measured"
              data-testid="bundle-search-ai-summary-note"
            >
              검색을 사용해 정리한 AI 요약입니다. 기사 원문 발췌도 검색 도구가 직접 반환한
              스니펫도 아닙니다.
              <template v-if="finding.unverified"> · 모델이 확인 불충분으로 표시했습니다.</template>
            </p>
            <p v-if="finding.url" class="bundle__source-meta measured bundle__hash">
              {{ finding.url }}
              <template v-if="finding.urlProvenance === 'model_provided'">
                · 모델이 제시한 주소(검색 도구가 반환한 주소로 확인되지 않음)
              </template>
            </p>
            <p
              v-if="finding.sources.length > 1"
              class="bundle__source-meta measured"
              data-testid="bundle-search-sources"
            >
              근거 주소: {{ finding.sources.join(', ') }}
            </p>
            <p v-if="finding.capturedAt" class="bundle__source-meta measured">
              확보 {{ finding.capturedAt }}
            </p>
          </li>
        </ul>
      </div>

      <p v-for="(note, index) in diagnostics" :key="`diag-${index}`" class="bundle__state" data-testid="bundle-diagnostics">
        {{ note }}
      </p>

      <!--
        섹션별 **실제 전달** 기록. 후보 목록과 별개이며, model_delivered=false(배당)는
        여기서 "모델 호출 없음"으로 표시한다. 전달됐다고 추정해 쓰지 않는다.
      -->
      <details class="bundle__details" data-testid="bundle-deliveries">
        <summary class="bundle__summary">섹션별 실제 전달 기록 보기</summary>
        <div class="bundle__details-body">
          <p v-if="view?.passageSemantics" class="bundle__source-note" data-testid="bundle-passage-semantics">
            {{ view.passageSemantics }}
          </p>
          <p v-if="!deliveries.length" class="bundle__state" data-testid="bundle-no-delivery">
            저장된 섹션 전달 기록이 없습니다. 이 묶음은 수집만 됐고 어느 섹션이 무엇을 받았는지
            남아 있지 않습니다.
          </p>
          <ul v-else class="bundle__passages">
            <li
              v-for="(delivery, index) in deliveries"
              :key="`${delivery.sectionId}-${delivery.logicalCallId ?? index}`"
              class="bundle__delivery"
              data-testid="bundle-delivery-row"
            >
              <p class="bundle__delivery-head">
                <span class="bundle__passage-title">{{ delivery.sectionId }}</span>
                <span
                  v-if="delivery.modelDelivered"
                  class="bundle__chip"
                  data-testid="bundle-delivery-model"
                >모델 호출 · 전달 {{ delivery.passageIds.length }}구간</span>
                <span v-else class="bundle__chip" data-testid="bundle-delivery-no-model">
                  모델 호출 없음 (배당 등 결정적 처리)
                </span>
              </p>
              <p v-if="delivery.searchFindingIds.length" class="bundle__source-meta measured">
                검색 자료 {{ delivery.searchFindingIds.length }}건 전달 ·
                {{ delivery.searchFindingIds.join(', ') }}
              </p>
              <p class="bundle__source-meta measured">
                <span v-if="delivery.inputChars !== null">입력 {{ delivery.inputChars }}자</span>
                <span v-if="delivery.sentAttempts !== null"> · 전송 시도 {{ delivery.sentAttempts }}회</span>
                <span v-if="delivery.implementationVersion"> · {{ delivery.implementationVersion }}</span>
                <span v-if="delivery.promptVersion"> · {{ delivery.promptVersion }}</span>
                <span v-if="delivery.createdAt"> · {{ delivery.createdAt }}</span>
              </p>
              <p v-if="delivery.payloadSha256" class="bundle__source-meta measured bundle__hash">
                payload {{ delivery.payloadSha256.slice(0, 16) }}…
              </p>
              <p v-if="delivery.note" class="bundle__source-note">{{ delivery.note }}</p>
            </li>
          </ul>
        </div>
      </details>

      <details class="bundle__details" data-testid="bundle-passages">
        <summary class="bundle__summary">출처별 수집 구간(전달 후보) 보기</summary>
        <div class="bundle__details-body">
          <p v-if="!okSources.length" class="bundle__state">수집된 구간이 있는 출처가 없습니다.</p>
          <article
            v-for="source in okSources"
            :key="`passages-${source.sourceId}`"
            class="bundle__passage-group"
            data-testid="bundle-passage-group"
          >
            <h5 class="bundle__passage-title">{{ sourceLabel(source) }}</h5>
            <p v-if="!source.passages.length" class="bundle__state">
              이 출처에서는 구간이 추출되지 않았습니다.
            </p>
            <ul v-else class="bundle__passages">
              <li
                v-for="passage in source.passages"
                :key="passage.passageId ?? `${source.sourceId}-${passage.ordinal}`"
                :data-testid="`bundle-passage-${passageStatus(passage.passageId) ?? 'unknown'}`"
              >
                <span v-if="passage.heading" class="bundle__passage-heading">{{ passage.heading }}</span>
                {{ passage.text }}
                <span class="bundle__passage-meta measured">{{ passage.charCount ?? passage.text.length }}자</span>
                <span
                  v-if="passageStatus(passage.passageId) === 'delivered'"
                  class="bundle__chip"
                  data-testid="bundle-passage-delivered"
                >실제 전달됨</span>
                <span
                  v-else-if="passageStatus(passage.passageId) === 'candidate'"
                  class="bundle__chip"
                  data-testid="bundle-passage-candidate"
                >후보</span>
              </li>
            </ul>
          </article>
        </div>
      </details>

      <details v-if="dbSnapshot" class="bundle__details" data-testid="bundle-database">
        <summary class="bundle__summary">DB 경기 자료 (읽기 전용 스냅샷)</summary>
        <div class="bundle__details-body">
          <p v-if="dbSnapshot.collectedAt" class="bundle__source-meta measured">
            조회 시각 {{ dbSnapshot.collectedAt }}
            <span v-if="dbSnapshot.teamIdSpace"> · 팀 ID 공간 {{ dbSnapshot.teamIdSpace }}</span>
          </p>
          <p v-if="dbSnapshot.fixtureLabel" class="bundle__db-fixture">{{ dbSnapshot.fixtureLabel }}</p>
          <p class="bundle__source-note" data-testid="bundle-db-readable">
            {{ dbSnapshot.readable ? 'DB 자료를 읽었습니다.' : 'DB 자료를 읽지 못했습니다.' }}
            <span v-if="dbSnapshot.injuries.length === 0">
              부상 행 0건은 '부상자 없음'의 증거가 아닙니다.
            </span>
          </p>
          <table v-if="dbSnapshot.standings.length" class="bundle__table">
            <caption class="visually-hidden">순위 스냅샷</caption>
            <thead>
              <tr>
                <th scope="col">팀</th>
                <th scope="col">순위</th>
                <th scope="col">경기</th>
                <th scope="col">승점</th>
                <th scope="col">최근</th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="(row, index) in dbSnapshot.standings"
                :key="`standing-${row.teamId ?? index}`"
                data-testid="bundle-standing-row"
              >
                <td class="measured">{{ row.teamId ?? '—' }}</td>
                <td class="measured">{{ row.rank ?? '—' }}</td>
                <td class="measured">{{ row.played ?? '—' }}</td>
                <td class="measured">{{ row.points ?? '—' }}</td>
                <td class="measured">{{ row.form ?? '—' }}</td>
              </tr>
            </tbody>
          </table>
          <ul v-if="dbSnapshot.coverage.length" class="bundle__passages" data-testid="bundle-db-coverage">
            <li v-for="(row, index) in dbSnapshot.coverage" :key="`coverage-${index}`">
              {{ row.topic ?? '축' }} — {{ row.state ?? '상태 없음' }}
              <span v-if="row.detail"> ({{ row.detail }})</span>
            </li>
          </ul>
        </div>
      </details>

      <details v-if="odds" class="bundle__details" data-testid="bundle-odds">
        <summary class="bundle__summary">배당 수집 결과 (모델 호출 없음)</summary>
        <div class="bundle__details-body">
          <p v-if="!odds.quotes.length" class="bundle__state">
            정규시간 1X2 배당을 확보하지 못했습니다. 값을 추정해 채우지 않습니다.
          </p>
          <table v-else class="bundle__table">
            <caption class="visually-hidden">사이트별 정규시간 1X2 배당</caption>
            <thead>
              <tr>
                <th scope="col">사이트</th>
                <th scope="col">홈</th>
                <th scope="col">무</th>
                <th scope="col">원정</th>
                <th scope="col">시장 / 수집</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="(quote, index) in odds.quotes" :key="`odds-${quote.site}-${index}`" data-testid="bundle-odds-row">
                <th scope="row">{{ quote.site }}</th>
                <td class="measured">{{ quote.home ?? '—' }}</td>
                <td class="measured">{{ quote.draw ?? '—' }}</td>
                <td class="measured">{{ quote.away ?? '—' }}</td>
                <td class="bundle__source-note">
                  {{ quote.market ?? '시장 미표기' }} · {{ quote.observedAt ?? '시각 미확인' }}
                  <span v-if="!quote.complete"> · 불완전</span>
                </td>
              </tr>
            </tbody>
          </table>
          <p v-if="odds.unsupportedSites.length" class="bundle__source-note">
            지원하지 않는 사이트: {{ odds.unsupportedSites.join(', ') }}
          </p>
        </div>
      </details>

      <details v-if="groups.length" class="bundle__details" data-testid="bundle-discovery">
        <summary class="bundle__summary">조사 묶음 상태 보기</summary>
        <div class="bundle__details-body">
          <ul class="bundle__passages">
            <li v-for="group in groups" :key="group.group" data-testid="bundle-discovery-group">
              {{ group.group }} — {{ group.status ?? '상태 없음' }}
              <span class="bundle__source-meta measured">
                후보 {{ group.candidateCount }}개
                <template v-if="group.sentAttempts !== null"> · 전송 {{ group.sentAttempts }}회</template>
              </span>
            </li>
          </ul>
        </div>
      </details>
    </template>
  </section>
</template>

<style scoped>
.bundle {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
  border: var(--rule-hair) solid var(--color-rule);
  border-radius: var(--radius-panel);
  padding: var(--space-4);
}

.bundle__head {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}

.bundle__title {
  margin: 0;
  font-size: var(--text-lg);
}

.bundle__note,
.bundle__source-note,
.bundle__source-meta {
  margin: 0;
  font-size: var(--text-sm);
  color: var(--color-muted);
}

.bundle__facts {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(10rem, 1fr));
  gap: var(--space-1) var(--space-3);
  margin: 0;
}

.bundle__facts dt {
  font-size: var(--text-sm);
  color: var(--color-muted);
}

.bundle__facts dd {
  margin: 0;
  overflow-wrap: anywhere;
}

.bundle__state {
  margin: 0;
  padding: var(--space-2) var(--space-3);
  border-radius: var(--radius-control);
  background: var(--color-paper-2);
  font-size: var(--text-sm);
  color: var(--color-ink-2);
}

.bundle__state--error {
  background: var(--color-bad-soft);
  color: var(--color-bad);
}

.bundle__subtitle {
  margin: 0 0 var(--space-1);
  font-size: var(--text-sm);
  color: var(--color-muted);
}

.bundle__source-list,
.bundle__passages {
  margin: 0;
  padding-left: 1.1rem;
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
}

.bundle__source {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.bundle__source--failed .bundle__source-head {
  color: var(--color-bad);
}

.bundle__source-head {
  margin: 0;
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2);
  align-items: baseline;
}

.bundle__source-link {
  color: var(--color-cool);
}

.bundle__chip {
  font-size: var(--text-sm);
  padding: 1px var(--space-2);
  border: var(--rule-hair) solid var(--color-rule-2);
  border-radius: 999px;
  color: var(--color-muted);
}

.bundle__details {
  border-top: var(--rule-hair) solid var(--color-rule);
  padding-top: var(--space-2);
}

.bundle__summary {
  cursor: pointer;
  font-size: var(--text-sm);
  color: var(--color-ink-2);
}

.bundle__details-body {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  padding-top: var(--space-2);
}

.bundle__passage-group {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
}

.bundle__passage-title {
  margin: 0;
  font-size: var(--text-sm);
  color: var(--color-ink);
}

.bundle__passage-heading {
  display: block;
  font-size: var(--text-sm);
  color: var(--color-muted);
}

.bundle__passage-meta {
  margin-left: var(--space-2);
  font-size: var(--text-sm);
  color: var(--color-muted);
}

.bundle__delivery {
  display: flex;
  flex-direction: column;
  gap: 2px;
  border-bottom: var(--rule-hair) solid var(--color-rule);
  padding-bottom: var(--space-2);
}

.bundle__delivery:last-child {
  border-bottom: 0;
}

.bundle__delivery-head {
  margin: 0;
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2);
  align-items: baseline;
}

.bundle__hash {
  overflow-wrap: anywhere;
}

.bundle__db-fixture {
  margin: 0;
  color: var(--color-ink-2);
}

.bundle__table {
  width: 100%;
  border-collapse: collapse;
}

.bundle__table th,
.bundle__table td {
  text-align: left;
  padding: var(--space-1) var(--space-2);
  border-bottom: var(--rule-hair) solid var(--color-rule);
}

.visually-hidden {
  position: absolute;
  width: 1px;
  height: 1px;
  overflow: hidden;
  clip-path: inset(50%);
  white-space: nowrap;
}
</style>
