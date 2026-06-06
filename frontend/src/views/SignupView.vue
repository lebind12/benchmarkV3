<script setup lang="ts">
import { computed, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { UserPlus, Mail, LockKeyhole, Badge } from 'lucide-vue-next'
import { signup } from '@/lib/api/auth'
import { useAuthStore } from '@/stores/auth'

const router = useRouter()
const auth = useAuthStore()

const form = reactive({
  email: '',
  nickname: '',
  password: '',
  confirmPassword: '',
})
const isSubmitting = ref(false)
const error = ref<string | null>(null)
const success = ref<string | null>(null)

const canSubmit = computed(() =>
  form.email.trim().length > 0
  && form.password.length >= 8
  && form.password === form.confirmPassword
  && !isSubmitting.value,
)

function errorMessage(code: string): string {
  return {
    email_already_registered: '이미 등록된 이메일입니다.',
    weak_password: '비밀번호는 8자 이상이며 영문과 숫자를 포함해야 합니다.',
    invalid_email: '이메일 형식을 확인해주세요.',
  }[code] ?? '회원가입을 완료하지 못했습니다.'
}

async function onSubmit() {
  if (!canSubmit.value) {
    error.value = form.password !== form.confirmPassword
      ? '비밀번호 확인이 일치하지 않습니다.'
      : '입력값을 확인해주세요.'
    return
  }

  isSubmitting.value = true
  error.value = null
  success.value = null
  try {
    const result = await signup({
      email: form.email,
      password: form.password,
      nickname: form.nickname || undefined,
    })
    auth.setUser(result.user)
    success.value = '가입이 완료되었습니다.'
    window.setTimeout(() => {
      void router.push('/')
    }, 700)
  } catch (err) {
    error.value = errorMessage((err as Error).message)
  } finally {
    isSubmitting.value = false
  }
}
</script>

<template>
  <main class="signup-page">
    <section class="signup-shell" aria-labelledby="signup-title">
      <form class="signup-form" data-testid="signup-form" @submit.prevent="onSubmit">
        <header>
          <UserPlus :size="20" aria-hidden="true" />
          <strong id="signup-title">회원가입</strong>
        </header>

        <label>
          <span><Mail :size="15" aria-hidden="true" /> 이메일</span>
          <input
            v-model="form.email"
            type="email"
            autocomplete="email"
            placeholder="you@example.com"
            data-testid="signup-email"
            required
          />
        </label>

        <label>
          <span><Badge :size="15" aria-hidden="true" /> 닉네임</span>
          <input
            v-model="form.nickname"
            type="text"
            autocomplete="nickname"
            placeholder="표시 이름"
            data-testid="signup-nickname"
            maxlength="40"
          />
        </label>

        <label>
          <span><LockKeyhole :size="15" aria-hidden="true" /> 비밀번호</span>
          <input
            v-model="form.password"
            type="password"
            autocomplete="new-password"
            placeholder="영문과 숫자 포함 8자 이상"
            data-testid="signup-password"
            required
          />
        </label>

        <label>
          <span><LockKeyhole :size="15" aria-hidden="true" /> 비밀번호 확인</span>
          <input
            v-model="form.confirmPassword"
            type="password"
            autocomplete="new-password"
            placeholder="한 번 더 입력"
            data-testid="signup-confirm-password"
            required
          />
        </label>

        <p v-if="error" class="signup-message signup-message--error" data-testid="signup-error">
          {{ error }}
        </p>
        <p v-if="success" class="signup-message signup-message--success" data-testid="signup-success">
          {{ success }}
        </p>

        <button
          type="submit"
          class="signup-submit"
          data-testid="signup-submit"
          :disabled="!canSubmit"
        >
          {{ isSubmitting ? '가입 처리 중' : '계정 만들기' }}
        </button>
      </form>
    </section>
  </main>
</template>

<style scoped>
.signup-page {
  height: calc(100vh - var(--header-height));
  min-height: 0;
  display: grid;
  place-items: center;
  padding: 2rem 1rem;
  box-sizing: border-box;
  overflow-y: auto;
  overflow-x: hidden;
  background:
    linear-gradient(90deg, rgba(17, 24, 39, 0.04) 1px, transparent 1px),
    linear-gradient(0deg, rgba(17, 24, 39, 0.04) 1px, transparent 1px),
    var(--color-bg);
  background-size: 44px 44px;
}

.signup-shell {
  width: min(520px, 100%);
  border: 1px solid var(--color-border);
  background: var(--color-card);
}

.signup-form {
  display: grid;
  gap: 1rem;
  padding: 2rem;
  background: var(--color-bg);
}

.signup-form header {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding-bottom: 0.25rem;
  font-size: 1.1rem;
}

.signup-form label {
  display: grid;
  gap: 0.45rem;
}

.signup-form label span {
  display: inline-flex;
  align-items: center;
  gap: 0.35rem;
  color: var(--color-muted);
  font-size: 0.9rem;
  font-weight: 650;
}

.signup-form input {
  width: 100%;
  box-sizing: border-box;
  padding: 0.78rem 0.85rem;
  border: 1px solid var(--color-border);
  border-radius: 0;
  background: var(--color-card);
  color: var(--color-fg);
}

.signup-form input:focus {
  border-color: #0f766e;
  outline: 2px solid rgba(15, 118, 110, 0.18);
  outline-offset: 0;
}

.signup-message {
  margin: 0;
  padding: 0.75rem 0.85rem;
  border: 1px solid;
  font-size: 0.9rem;
}

.signup-message--error {
  border-color: rgba(220, 38, 38, 0.32);
  background: rgba(220, 38, 38, 0.08);
  color: #b91c1c;
}

.signup-message--success {
  border-color: rgba(15, 118, 110, 0.34);
  background: rgba(15, 118, 110, 0.08);
  color: #0f766e;
}

.signup-submit {
  height: 2.85rem;
  border: 0;
  background: #0f766e;
  color: white;
  font-weight: 800;
  cursor: pointer;
}

.signup-submit:disabled {
  background: var(--color-border);
  color: var(--color-muted);
  cursor: not-allowed;
}

@media (max-width: 760px) {
  .signup-page {
    place-items: stretch;
    padding: 1rem;
  }

  .signup-form {
    padding: 1.35rem;
  }
}
</style>
