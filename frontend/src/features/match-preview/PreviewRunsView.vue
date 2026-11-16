<script setup lang="ts">
/**
 * 관리자 실행 목록 (MP-02 범위).
 *
 * 세션을 확인하고 저장된 실행 목록을 읽는다. 목록은 서버에 저장된 행만 보여주며
 * 화면을 여는 것만으로 외부 API·모델을 호출하지 않는다. 실행 생성은 명시적으로
 * 눌러야만 일어나고, MP-02에서는 녹화된 모의 실행만 만들 수 있다.
 */
import { computed, onMounted, ref } from 'vue'
import { RouterLink, useRoute, useRouter } from 'vue-router'
import { authApi } from '@/lib/api/http'
import { useAuthStore } from '@/stores/auth'
import { previewRunsApi } from '@/features/match-preview/api'
import RunInspector from '@/features/match-preview/RunInspector.vue'
import type { RunSummary } from '@/features/match-preview/types'

const router = useRouter()
const route = useRoute()
const auth = useAuthStore()

const userEmail = computed(() => auth.user?.email ?? null)
const runs = ref<RunSummary[] | null>(null)
const loading = ref(true)
const errorMessage = ref<string | null>(null)
const signingOut = ref(false)
const logoutError = ref<string | null>(null)
const creating = ref(false)
const createError = ref<string | null>(null)
const selectedRunId = ref<string | null>(null)
const notice = ref<string | null>(null)

async function redirectToLogin() {
  const next = typeof route.fullPath === 'string' && route.fullPath.startsWith('/') ? route.fullPath : '/admin/runs'
  await router.push({ name: 'login', query: { next } })
}

async function signOut() {
  signingOut.value = true
  logoutError.value = null
  const result = await authApi.logout()
  signingOut.value = false

  if (!result.ok) {
    // 로그아웃이 실패하면 서버 세션은 아직 살아 있다. 성공한 것처럼 로그인 화면으로
    // 보내지 않고, 실패를 알리고 같은 세션으로 다시 시도할 수 있게 둔다.
    logoutError.value = result.message
    return
  }

  auth.logout()
  await router.push({ name: 'login' })
}

/**
 * 지표 화면에서 넘어온 실행 ID. 표본에서 원문까지 같은 조건으로 이동하기 위해
 * 필터를 유지한 채 실행만 연다. 새 실행이나 외부 호출을 만들지 않는다(GET만).
 */
function requestedRunId(): string | null {
  const raw = route.query.run
  return typeof raw === 'string' && raw.length > 0 ? raw : null
}

/**
 * 지표 화면에서 실려 온 조회 필터. 실행을 본 뒤 같은 조건으로 지표 화면에 돌아갈
 * 때 쓴다. 지표 화면이 보내지 않은 값은 여기서 만들지 않는다.
 */
const metricsReturnQuery = computed<string | null>(() => {
  if (route.query.from !== 'metrics') return null
  const params = new URLSearchParams()
  for (const key of [
    'from_at',
    'to_at',
    'environment',
    'mode',
    'module_id',
    'model',
    'contract_version',
  ]) {
    for (const value of queryValues(route.query[key])) params.append(key, value)
  }
  return params.toString()
})

function queryValues(raw: unknown): string[] {
  if (typeof raw === 'string') return raw.length > 0 ? [raw] : []
  if (Array.isArray(raw)) {
    return raw.filter((entry): entry is string => typeof entry === 'string' && entry.length > 0)
  }
  return []
}

async function load() {
  loading.value = true
  errorMessage.value = null

  const verified = auth.verified && auth.user ? true : await auth.verifySession()
  if (!verified || !auth.user) {
    loading.value = false
    await redirectToLogin()
    return
  }
  if (!auth.isAdmin) {
    loading.value = false
    await router.push({ name: 'not-found' })
    return
  }

  const runsResult = await previewRunsApi.list()
  loading.value = false
  if (!runsResult.ok) {
    if (runsResult.kind === 'unauthenticated') {
      auth.logout()
      await redirectToLogin()
      return
    }
    errorMessage.value = runsResult.message
    return
  }
  runs.value = runsResult.data.runs

  const requested = requestedRunId()
  if (requested && runs.value.some((run) => run.run_id === requested)) {
    selectedRunId.value = requested
  }
}

async function createMockRun() {
  creating.value = true
  createError.value = null
  notice.value = null
  const result = await previewRunsApi.createMockDemo()
  creating.value = false
  if (!result.ok) {
    createError.value = result.message
    return
  }
  notice.value = `녹화된 모의 실행을 만들었습니다 (외부 호출 ${result.data.external_calls}회).`
  await load()
  selectedRunId.value = result.data.run_id
}

onMounted(load)

const hasRuns = computed(() => (runs.value?.length ?? 0) > 0)

function modeLabel(mode: RunSummary['mode']): string {
  if (mode === 'live') return '실호출 (live)'
  if (mode === 'replay') return '저장 응답 재생 (replay)'
  return '모의 (mock)'
}

function formatTime(value: string | null): string {
  if (!value) return '—'
  const parsed = new Date(value)
  if (Number.isNaN(parsed.getTime())) return value
  return parsed.toISOString().replace('T', ' ').replace('.000Z', 'Z')
}
</script>

<template>
  <div class="shell">
    <header class="shell__bar">
      <p class="shell__brand">경기 프리뷰 관리자</p>
      <nav class="shell__nav" aria-label="관리자 화면">
        <!-- 경로 문자열을 쓴다. 이름 기반 이동은 라우터에 그 경로가 없을 때 해석
             오류를 내므로, 화면이 라우터 등록 여부에 묶이지 않게 한다. -->
        <RouterLink class="shell__nav-link" to="/admin/runs">실행 목록</RouterLink>
        <RouterLink class="shell__nav-link" to="/admin/sections">섹션 실행</RouterLink>
        <RouterLink class="shell__nav-link" to="/admin/fixtures">경기 선택</RouterLink>
        <RouterLink class="shell__nav-link" to="/admin/metrics">운영 지표</RouterLink>
      </nav>
      <div class="shell__account">
        <span v-if="userEmail" class="shell__email">{{ userEmail }}</span>
        <p v-if="logoutError" class="shell__logout-error" role="alert" data-testid="logout-error">
          로그아웃하지 못했습니다. {{ logoutError }}
        </p>
        <button
          class="button button--quiet"
          type="button"
          :disabled="signingOut"
          data-testid="logout"
          @click="signOut"
        >
          {{ signingOut ? '로그아웃 중…' : '로그아웃' }}
        </button>
      </div>
    </header>

    <main class="shell__main">
      <section class="panel" aria-labelledby="runs-title" data-testid="runs-panel">
        <header class="panel__head">
          <h1 id="runs-title" class="panel__title">실행 목록</h1>
          <p class="panel__hint">
            저장된 실행을 열면 모듈별 요청·원문 응답·정규화 변환·다음 입력과 결과 버전을 확인할 수
            있습니다. 목록 조회는 외부 API·모델을 호출하지 않습니다.
          </p>
          <!-- 지표에서 내려온 경우, 같은 조회 조건으로 지표 화면에 돌아갈 수 있게 한다. -->
          <p v-if="metricsReturnQuery !== null" class="panel__hint" data-testid="metrics-return">
            <RouterLink
              class="button button--quiet"
              :to="`/admin/metrics${metricsReturnQuery ? `?${metricsReturnQuery}` : ''}`"
            >
              같은 조건으로 운영 지표로 돌아가기
            </RouterLink>
          </p>
        </header>

        <div class="actions">
          <button
            class="button"
            type="button"
            :disabled="creating"
            data-testid="create-mock-run"
            @click="createMockRun"
          >
            {{ creating ? '만드는 중…' : '녹화된 모의 실행 만들기' }}
          </button>
          <p class="actions__note">
            외부 모델·API를 호출하지 않는 시연 실행입니다. 실제 AI 조사 결과가 아닙니다.
          </p>
        </div>

        <p v-if="notice" class="notice notice--info" data-testid="create-notice">{{ notice }}</p>
        <p
          v-if="createError"
          class="notice notice--error"
          role="alert"
          data-testid="create-error"
        >
          {{ createError }}
        </p>

        <p v-if="errorMessage" class="notice notice--error" role="alert" data-testid="runs-error">
          {{ errorMessage }}
          <button class="button button--quiet" type="button" @click="load">다시 시도</button>
        </p>

        <div v-else-if="loading" class="skeleton" aria-busy="true" aria-live="polite">
          <span class="visually-hidden">실행 목록을 불러오는 중입니다.</span>
          <div class="skeleton__row" />
          <div class="skeleton__row" />
          <div class="skeleton__row" />
        </div>

        <div v-else-if="runs && !hasRuns" class="empty" data-testid="runs-empty">
          <p class="empty__title">아직 실행 기록이 없습니다.</p>
          <p class="empty__body">
            첫 실행을 만들면 이 목록에 나타납니다. 지금은 조회할 기록이 없다는 뜻이며, 오류가
            아닙니다.
          </p>
        </div>

        <table v-else-if="runs" class="table" data-testid="runs-table">
          <caption>저장된 실행 {{ runs.length }}건</caption>
          <thead>
            <tr>
              <th scope="col">실행 ID</th>
              <th scope="col">실행 방식</th>
              <th scope="col">상태</th>
              <th scope="col">요청 시각</th>
              <th scope="col">모듈·시도</th>
              <th scope="col"><span class="visually-hidden">검사 열기</span></th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="run in runs" :key="run.run_id">
              <td class="measured">
                {{ run.run_id.slice(0, 8) }}
                <span v-if="run.label" class="run-label">{{ run.label }}</span>
              </td>
              <td>
                <span class="chip" :class="{ 'chip--mock': run.mode !== 'live' }">
                  {{ modeLabel(run.mode) }}
                </span>
                <span class="measured run-env">{{ run.environment }}</span>
              </td>
              <td class="measured">
                {{ run.status }} / {{ run.quality }}
                <span v-if="run.cancelled_at" class="run-cancelled">취소됨</span>
              </td>
              <td class="measured">{{ formatTime(run.requested_at) }}</td>
              <td class="measured">{{ run.module_count }} / {{ run.attempt_count }}</td>
              <td>
                <button
                  class="button button--quiet"
                  type="button"
                  :data-testid="`open-run-${run.run_id}`"
                  @click="selectedRunId = run.run_id"
                >
                  검사
                </button>
              </td>
            </tr>
          </tbody>
        </table>
      </section>

      <section v-if="selectedRunId" class="panel panel--inspector">
        <RunInspector
          :key="selectedRunId"
          :run-id="selectedRunId"
          @closed="selectedRunId = null"
          @cancelled="load"
        />
      </section>
    </main>
  </div>
</template>

<style scoped>
.shell__nav {
  display: flex;
  gap: var(--space-3);
  font-size: var(--text-sm);
}

.shell__nav-link {
  color: var(--color-ink-2);
  text-decoration: none;
}

.shell__nav-link.router-link-active {
  color: var(--color-ink);
  text-decoration: underline;
}

.shell__account .button {
  white-space: nowrap;
}

.shell__logout-error {
  font-size: var(--text-sm);
  color: var(--color-ink);
  background: var(--color-bad-soft);
  border: var(--rule-hair) solid var(--color-bad);
  border-radius: var(--radius-control);
  padding: var(--space-1) var(--space-2);
}

.actions {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  flex-wrap: wrap;
  margin-bottom: var(--space-4);
}

.actions__note {
  font-size: var(--text-sm);
  color: var(--color-muted);
}

.chip {
  font-size: var(--text-sm);
  padding: 0 var(--space-2);
  border-radius: var(--radius-control);
  border: var(--rule-hair) solid var(--color-rule-2);
  color: var(--color-ink-2);
  white-space: nowrap;
}

.chip--mock {
  border-color: var(--color-accent);
  color: var(--color-accent);
}

.run-label,
.run-env {
  display: block;
  font-size: var(--text-sm);
  color: var(--color-muted);
}

.run-cancelled {
  display: block;
  font-size: var(--text-sm);
  color: var(--color-bad);
}

.panel--inspector {
  margin-top: var(--space-4);
}

@media (max-width: 40rem) {
  .shell__logout-error {
    flex-basis: 100%;
  }
}
</style>
