<script setup lang="ts">
/**
 * D0 자료 패널 (MP-03).
 *
 * 이 패널은 D0가 확보한 자료를 **자료 종류별로** 보여준다. 노드마다 별도 승인을
 * 요구하지 않으며, 이 화면 역시 승인 단위가 아니다. 승인 단위는 섹션 워크플로우다.
 *
 * 표시 원칙:
 *
 * - 실행 성공과 근거 확보를 따로 보여준다. 실행이 성공해도 채택할 근거가 없을 수 있다.
 * - 빈 부상 응답을 "부상자 없음"으로 쓰지 않는다. 서버가 주는 상태·사유를 그대로 쓴다.
 * - 실행 방식(mock/replay/live)과 자료 출처(api/search)를 다른 축으로 표시한다.
 * - 스냅샷마다 수집 시각과 원문 아티팩트 참조를 함께 보여준다.
 */
import { computed } from 'vue'
import { coverageLabel, modeLabel, type D0ResultView } from '../fixtures'

const props = defineProps<{
  result: D0ResultView | null
  loading?: boolean
  errorMessage?: string | null
}>()

const claims = computed(() => props.result?.claims ?? [])
const coverage = computed(() => props.result?.coverage ?? [])
const adopted = computed(() => claims.value.filter((claim) => claim.decision === 'adopted'))
const excluded = computed(() => claims.value.filter((claim) => claim.decision === 'excluded'))
const snapshots = computed(() => props.result?.snapshots ?? [])

const statusLabel = computed(() => {
  const status = props.result?.result.status
  if (!status) return ''
  return status === 'succeeded' ? '실행 성공' : status === 'failed' ? '실행 실패' : status
})
</script>

<template>
  <section class="data-panel">
    <header>
      <h3>D0 경기·API 자료</h3>
      <p class="hint">
        조사 모듈이 쓰는 공통 자료 묶음입니다. 모델 호출은 없고, 자료 준비 단계에는 별도
        승인을 요구하지 않습니다.
      </p>
    </header>

    <p v-if="loading" class="state">D0 결과를 읽는 중입니다.</p>
    <p v-else-if="errorMessage" class="state error" data-test="d0-error">{{ errorMessage }}</p>
    <p v-else-if="!result" class="state" data-test="d0-empty">
      아직 D0를 실행하지 않았습니다.
    </p>

    <template v-else>
      <dl class="summary" data-test="d0-summary">
        <div>
          <dt>경기</dt>
          <dd data-test="d0-fixture">
            fixture_id {{ result.fixture.fixture_id }} · 리그 {{ result.fixture.league_id }} ·
            시즌 {{ result.fixture.season }}
          </dd>
        </div>
        <div>
          <dt>킥오프</dt>
          <dd>{{ result.fixture.kickoff_at }}</dd>
        </div>
        <div>
          <dt>실행 방식</dt>
          <dd data-test="d0-mode">{{ modeLabel(result.mode) }}</dd>
        </div>
        <div>
          <dt>실행 상태</dt>
          <dd data-test="d0-status">
            {{ statusLabel }}
            <span class="muted">(품질 {{ result.result.quality }})</span>
          </dd>
        </div>
        <div>
          <dt>결과 버전</dt>
          <dd>{{ result.result.version }} · 구현 {{ result.result.implementation_version }}</dd>
        </div>
        <div>
          <dt>외부 API 호출</dt>
          <dd data-test="d0-external-calls">
            {{ result.external_calls }}회
            <span class="muted">
              (실행기 호출 {{ result.provider_calls }}회 · live만 외부 호출로 셉니다)
            </span>
          </dd>
        </div>
      </dl>

      <h4>자료별 확보 상태</h4>
      <table class="coverage" data-test="d0-coverage">
        <thead>
          <tr>
            <th>자료</th>
            <th>상태</th>
            <th>사유</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="entry in coverage" :key="entry.topic + entry.state">
            <td>{{ entry.topic }}</td>
            <td :class="['state-chip', entry.state]" data-test="coverage-state">
              {{ coverageLabel(entry.state) }}
            </td>
            <td class="muted">{{ entry.detail ?? '' }}</td>
          </tr>
        </tbody>
      </table>

      <h4>채택한 근거 ({{ adopted.length }}건)</h4>
      <ul v-if="adopted.length > 0" class="claims" data-test="d0-claims">
        <li v-for="claim in adopted" :key="claim.claim_id">
          <span class="kind">{{ claim.kind }}</span>
          {{ claim.text }}
          <span v-if="claim.decision_reason" class="muted">— {{ claim.decision_reason }}</span>
        </li>
      </ul>
      <p v-else class="state">채택한 근거가 없습니다. 실행 성공과 근거 확보는 별개입니다.</p>

      <details v-if="excluded.length > 0" class="excluded">
        <summary>채택하지 않은 근거 ({{ excluded.length }}건)</summary>
        <ul>
          <li v-for="claim in excluded" :key="claim.claim_id">
            {{ claim.text }}
            <span v-if="claim.decision_reason" class="muted">— {{ claim.decision_reason }}</span>
          </li>
        </ul>
      </details>

      <h4>자료 스냅샷 ({{ snapshots.length }}건)</h4>
      <table v-if="snapshots.length > 0" class="snapshots" data-test="d0-snapshots">
        <thead>
          <tr>
            <th>출처</th>
            <th>제공자</th>
            <th>수집 시각</th>
            <th>검증</th>
            <th>원문</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="snapshot in snapshots" :key="snapshot.snapshot_id">
            <td>{{ snapshot.source_kind }}</td>
            <td>{{ snapshot.provider }}</td>
            <td>{{ snapshot.collected_at }}</td>
            <td>{{ snapshot.validation_status }}</td>
            <td>
              <span v-if="snapshot.artifact_id" class="mono">{{ snapshot.artifact_id }}</span>
              <span v-else class="muted">원문 없음(호출 실패 또는 본문 미보존)</span>
            </td>
          </tr>
        </tbody>
      </table>
      <p v-else class="state">저장된 스냅샷이 없습니다.</p>

      <details v-if="result.diagnostics.length > 0" class="diagnostics">
        <summary>내부 진단 (독자용 아님)</summary>
        <ul>
          <li v-for="note in result.diagnostics" :key="note">{{ note }}</li>
        </ul>
      </details>
    </template>
  </section>
</template>

<style scoped>
.data-panel {
  display: flex;
  flex-direction: column;
  gap: 0.6rem;
}
.hint,
.muted {
  color: #566;
  font-size: 0.85rem;
}
.state {
  margin: 0;
  padding: 0.5rem 0.75rem;
  border-radius: 0.375rem;
  background: #f4f6f8;
}
.state.error {
  background: #fdecec;
  color: #8a1c1c;
}
.summary {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(14rem, 1fr));
  gap: 0.5rem;
  margin: 0;
}
.summary dt {
  font-size: 0.75rem;
  color: #667;
}
.summary dd {
  margin: 0;
  font-size: 0.9rem;
}
table {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.85rem;
}
th,
td {
  padding: 0.35rem 0.5rem;
  border-bottom: 1px solid #e3e7ea;
  text-align: left;
  vertical-align: top;
}
.state-chip {
  white-space: nowrap;
}
.state-chip.available {
  color: #1c6b35;
}
.state-chip.call_error,
.state-chip.validation_rejected {
  color: #8a1c1c;
}
.state-chip.unknown,
.state-chip.api_not_provided {
  color: #7a4a00;
}
.claims {
  margin: 0;
  padding-left: 1.1rem;
}
.claims .kind {
  font-size: 0.75rem;
  padding: 0.05rem 0.3rem;
  border-radius: 0.25rem;
  background: #eef2f5;
}
.mono {
  font-family: ui-monospace, SFMono-Regular, monospace;
  font-size: 0.78rem;
}
</style>
