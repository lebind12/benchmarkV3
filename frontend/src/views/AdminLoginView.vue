<script setup lang="ts">
/**
 * 관리자 로그인 화면.
 *
 * 실패 이유는 서버 응답의 종류에 따라 구분해 보여준다. 어떤 계정이 존재하는지
 * 알려주지 않기 위해 아이디/비밀번호 오류 메시지는 하나로 합친다.
 */
import { computed, nextTick, ref } from 'vue'
import { useRouter } from 'vue-router'
import { authApi, type ApiFailure } from '@/lib/api/http'

const router = useRouter()

const email = ref('')
const password = ref('')
const submitting = ref(false)
const formError = ref<string | null>(null)
const emailInput = ref<HTMLInputElement | null>(null)
const passwordInput = ref<HTMLInputElement | null>(null)

const isSubmittable = computed(
  () => email.value.trim().length > 0 && password.value.length > 0 && !submitting.value,
)

function focusFirstInvalidField() {
  nextTick(() => {
    if (email.value.trim().length === 0) {
      emailInput.value?.focus()
    } else {
      passwordInput.value?.focus()
    }
  })
}

function handleFailure(failure: ApiFailure) {
  formError.value = failure.message
  if (failure.kind === 'unauthenticated') {
    password.value = ''
  }
  focusFirstInvalidField()
}

async function submit() {
  if (!isSubmittable.value) {
    formError.value = '이메일과 비밀번호를 모두 입력하세요.'
    focusFirstInvalidField()
    return
  }

  submitting.value = true
  formError.value = null
  const result = await authApi.login(email.value.trim(), password.value)
  submitting.value = false

  if (!result.ok) {
    handleFailure(result)
    return
  }

  await router.push({ name: 'preview-runs' })
}
</script>

<template>
  <div class="login">
    <main class="login__card panel" aria-labelledby="login-title">
      <header class="panel__head">
        <h1 id="login-title" class="panel__title">경기 프리뷰 관리자</h1>
        <p class="panel__hint">관리자 계정으로 로그인합니다.</p>
      </header>

      <p v-if="formError" class="notice notice--error" role="alert" data-testid="login-error">
        {{ formError }}
      </p>

      <form novalidate @submit.prevent="submit">
        <div class="field">
          <label class="label" for="login-email">이메일</label>
          <input
            id="login-email"
            ref="emailInput"
            v-model="email"
            class="input"
            type="email"
            name="email"
            autocomplete="username"
            :aria-invalid="formError ? 'true' : 'false'"
            :disabled="submitting"
            data-testid="login-email"
          />
        </div>

        <div class="field">
          <label class="label" for="login-password">비밀번호</label>
          <input
            id="login-password"
            ref="passwordInput"
            v-model="password"
            class="input"
            type="password"
            name="password"
            autocomplete="current-password"
            :aria-invalid="formError ? 'true' : 'false'"
            :disabled="submitting"
            data-testid="login-password"
          />
        </div>

        <button
          class="button button--block"
          type="submit"
          :disabled="submitting"
          data-testid="login-submit"
        >
          {{ submitting ? '확인 중…' : '로그인' }}
        </button>
      </form>

      <p class="login__foot">회원가입은 제공하지 않습니다. 계정은 운영 담당자가 발급합니다.</p>
    </main>
  </div>
</template>

<style scoped>
.login {
  min-height: 100vh;
  display: grid;
  place-items: center;
  padding: var(--space-5);
}

.login__card {
  width: 100%;
  max-width: 26rem;
}

.login .button {
  white-space: nowrap;
}

.login__foot {
  margin-top: var(--space-5);
  font-size: var(--text-sm);
  color: var(--color-muted);
}
</style>
