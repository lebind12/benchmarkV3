<script setup lang="ts">
/**
 * 경기 선택 (MP-03).
 *
 * 이 화면이 지키는 것:
 *
 * - 목록은 **저장된 자료만** 읽는다. 화면을 열거나 새로 고쳐도 외부 수집이 일어나지
 *   않는다. 수집은 관리자가 조건을 넣고 "목록 수집"을 눌렀을 때만 실행된다.
 * - 경기 식별은 외부 API 경기 ID(`fixture_id`)로 하고, 저장 행 ID(`internal_id`)와
 *   섞지 않는다. 화면에도 두 값을 구분해 표시한다.
 * - 저장된 경기 자료 읽기 권한이 없으면 빈 목록으로 꾸미지 않고, 필요한 SELECT 경계를
 *   그대로 보여준다.
 * - 목록 수집 결과의 실행 방식(mock/replay/live)을 항상 함께 표시한다.
 */
import { computed, onMounted, ref } from 'vue'
import {
  modeLabel,
  previewDataApi,
  type FixtureCandidate,
  type FixtureListResponse,
  type ImportFixturesResponse,
} from './fixtures'

const emit = defineEmits<{ (event: 'select', fixture: FixtureCandidate): void }>()

const listing = ref<FixtureListResponse | null>(null)
const loading = ref(true)
const errorMessage = ref<string | null>(null)

const leagueId = ref('39')
const date = ref(new Date().toISOString().slice(0, 10))
const timezoneName = ref('Asia/Seoul')

const importing = ref(false)
const importError = ref<string | null>(null)
const importedResult = ref<ImportFixturesResponse | null>(null)

const candidates = computed(() => listing.value?.fixtures ?? [])
const access = computed(() => listing.value?.stored_access ?? null)

function isToday(iso: string): boolean {
  return iso.slice(0, 10) === new Date().toISOString().slice(0, 10)
}

async function load() {
  loading.value = true
  errorMessage.value = null
  const result = await previewDataApi.listFixtures()
  loading.value = false
  if (!result.ok) {
    // 404는 라우터 미등록(통합 전)이며 빈 목록과 다른 상태다.
    errorMessage.value =
      result.status === 404
        ? '경기 목록 경로가 아직 서버에 연결되지 않았습니다. 통합 소유자가 라우터를 등록해야 합니다.'
        : result.message
    listing.value = null
    return
  }
  listing.value = result.data
}

async function importFixtures() {
  importing.value = true
  importError.value = null
  importedResult.value = null
  const result = await previewDataApi.importFixtures({
    league_id: Number(leagueId.value),
    date: date.value,
    timezone: timezoneName.value,
  })
  importing.value = false
  if (!result.ok) {
    importError.value = result.message
    return
  }
  importedResult.value = result.data
  await load()
}

function select(fixture: FixtureCandidate) {
  if (!fixture.selectable) return
  emit('select', fixture)
}

function originLabel(fixture: FixtureCandidate): string {
  if (fixture.origin === 'stored_db') return '기존 DB 저장 경기'
  if (fixture.origin === 'catalog_import') return '저장된 목록 수집'
  return fixture.origin
}

onMounted(load)
</script>

<template>
  <section class="fixture-selector">
    <header>
      <h2>경기 선택</h2>
      <p class="hint">
        목록은 저장된 자료만 읽습니다. 수집은 아래에서 조건을 넣고 직접 실행할 때만
        일어납니다.
      </p>
    </header>

    <p v-if="loading" class="state">저장된 경기 목록을 읽는 중입니다.</p>
    <p v-else-if="errorMessage" class="state error">{{ errorMessage }}</p>

    <template v-else>
      <p v-if="listing" class="note" data-test="list-note">{{ listing.note }}</p>

      <p
        v-if="access && !access.readable"
        class="state warning"
        data-test="access-blocked"
      >
        기존 DB 경기 자료 읽기 권한이 없습니다. 필요한 경계:
        <code v-for="grant in access.required" :key="grant">{{ grant }}</code>
      </p>

      <table v-if="candidates.length > 0" class="fixtures" data-test="fixture-table">
        <thead>
          <tr>
            <th>경기</th>
            <th>리그</th>
            <th>킥오프</th>
            <th>출처</th>
            <th>식별자</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="fixture in candidates"
            :key="fixture.fixture_id"
            data-test="fixture-row"
            :class="{ today: isToday(fixture.kickoff_at) }"
          >
            <td>
              {{ fixture.label }}
              <span v-if="!fixture.selectable" class="badge">팀 미확정</span>
            </td>
            <td>{{ fixture.league_name ?? fixture.league_id }}</td>
            <td>{{ fixture.kickoff_at }}</td>
            <td>
              {{ originLabel(fixture) }}
              <span v-if="fixture.mode" class="badge mode">{{ modeLabel(fixture.mode) }}</span>
            </td>
            <td class="identifiers">
              <span>fixture_id {{ fixture.fixture_id }}</span>
              <span class="muted">{{ fixture.origin_note }}</span>
            </td>
            <td>
              <button
                type="button"
                :disabled="!fixture.selectable"
                data-test="select-fixture"
                @click="select(fixture)"
              >
                이 경기로 자료 준비
              </button>
            </td>
          </tr>
        </tbody>
      </table>

      <p v-else class="state" data-test="no-fixtures">
        저장된 경기 후보가 없습니다. 이는 수집 실패와 다른 상태입니다.
      </p>

      <details class="import">
        <summary>경기 목록 수집 (명시적 실행)</summary>
        <form @submit.prevent="importFixtures">
          <label>
            리그 ID
            <input v-model="leagueId" type="number" min="1" required />
          </label>
          <label>
            날짜
            <input v-model="date" type="date" required />
          </label>
          <label>
            시간대
            <input v-model="timezoneName" type="text" required />
          </label>
          <button type="submit" :disabled="importing" data-test="import-fixtures">
            {{ importing ? '수집 중…' : '목록 수집' }}
          </button>
        </form>
        <p v-if="importError" class="state error">{{ importError }}</p>
        <div v-if="importedResult" class="import-result" data-test="import-result">
          <p>
            실행 <code>{{ importedResult.run_id }}</code> · {{ importedResult.fixtures.length }}건 ·
            {{ modeLabel(importedResult.mode) }} · 외부 호출
            {{ importedResult.external_calls }}회 (실행기 호출
            {{ importedResult.provider_calls }}회)
          </p>
          <p v-for="entry in importedResult.coverage" :key="entry.topic + entry.state" class="muted">
            {{ entry.topic }}: {{ entry.state }}<template v-if="entry.detail"> — {{ entry.detail }}</template>
          </p>
        </div>
      </details>
    </template>
  </section>
</template>

<style scoped>
.fixture-selector {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}
.hint,
.note,
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
.state.warning {
  background: #fff7e6;
  color: #7a4a00;
}
.fixtures {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.9rem;
}
.fixtures th,
.fixtures td {
  padding: 0.4rem 0.5rem;
  border-bottom: 1px solid #e3e7ea;
  text-align: left;
  vertical-align: top;
}
.fixtures tr.today {
  background: #f7fbff;
}
.identifiers {
  display: flex;
  flex-direction: column;
  gap: 0.15rem;
  max-width: 18rem;
}
.badge {
  display: inline-block;
  margin-left: 0.35rem;
  padding: 0.05rem 0.35rem;
  border-radius: 0.25rem;
  background: #eef2f5;
  font-size: 0.75rem;
}
.badge.mode {
  background: #eaf4ff;
}
.import {
  margin-top: 0.5rem;
}
.import form {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
  align-items: flex-end;
  margin-top: 0.5rem;
}
.import label {
  display: flex;
  flex-direction: column;
  font-size: 0.8rem;
  gap: 0.2rem;
}
</style>
