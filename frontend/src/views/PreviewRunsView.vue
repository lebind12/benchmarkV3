<script setup lang="ts">
/**
 * 관리자 실행 목록 (MP-01 범위).
 *
 * MP-01에는 실행 기록 저장소가 아직 없다. 그래서 이 화면은 실제로 존재하는
 * 것만 보여준다: 세션 확인, 그리고 보호된 실행 목록 조회가 돌려준 빈 목록.
 * 기록·검사 UI는 MP-02가 이 경로를 확장해 맡는다.
 */
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { authApi, previewApi, type SessionPayload } from '@/lib/api/http'

const router = useRouter()

const session = ref<SessionPayload | null>(null)
const runs = ref<unknown[] | null>(null)
const loading = ref(true)
const errorMessage = ref<string | null>(null)
const signingOut = ref(false)

async function signOut() {
  signingOut.value = true
  await authApi.logout()
  signingOut.value = false
  await router.push({ name: 'admin-login' })
}

async function load() {
  loading.value = true
  errorMessage.value = null

  const sessionResult = await authApi.session()
  if (!sessionResult.ok) {
    loading.value = false
    await router.push({ name: 'admin-login' })
    return
  }
  session.value = sessionResult.data

  const runsResult = await previewApi.runs()
  loading.value = false
  if (!runsResult.ok) {
    if (runsResult.kind === 'unauthenticated') {
      await router.push({ name: 'admin-login' })
      return
    }
    errorMessage.value = runsResult.message
    return
  }
  runs.value = runsResult.data.runs
}

onMounted(load)
</script>

<template>
  <div class="shell">
    <header class="shell__bar">
      <p class="shell__brand">경기 프리뷰 관리자</p>
      <div class="shell__account">
        <span v-if="session" class="shell__email">{{ session.email }}</span>
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
      <section class="panel" aria-labelledby="runs-title">
        <header class="panel__head">
          <h1 id="runs-title" class="panel__title">실행 목록</h1>
          <p class="panel__hint">
            경기 프리뷰 생성 실행이 여기에 쌓입니다. 호출 기록과 조사 결과는 다음 단계에서
            추가됩니다.
          </p>
        </header>

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

        <div v-else-if="runs && runs.length === 0" class="empty" data-testid="runs-empty">
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
              <th scope="col">상태</th>
              <th scope="col">요청 시각</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(run, index) in runs" :key="index">
              <td class="measured">{{ String(run) }}</td>
              <td>확인 필요</td>
              <td>확인 필요</td>
            </tr>
          </tbody>
        </table>
      </section>
    </main>
  </div>
</template>

<style scoped>
.shell__account .button {
  white-space: nowrap;
}
</style>
