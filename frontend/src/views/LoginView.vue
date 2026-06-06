<script setup lang="ts">
import { computed, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { LogIn, Mail, LockKeyhole, ShieldCheck } from 'lucide-vue-next'
import { login } from '@/lib/api/auth'
import { useAuthStore } from '@/stores/auth'

const router = useRouter()
const auth = useAuthStore()

const form = reactive({
  email: '',
  password: '',
})
const isSubmitting = ref(false)
const error = ref<string | null>(null)
const success = ref<string | null>(null)

const canSubmit = computed(() =>
  form.email.trim().length > 0
  && form.password.length > 0
  && !isSubmitting.value,
)

function errorMessage(code: string): string {
  return {
    invalid_credentials: '이메일 또는 비밀번호가 올바르지 않습니다.',
    inactive_user: '비활성화된 계정입니다. 관리자에게 문의해주세요.',
    invalid_email: '이메일 형식을 확인해주세요.',
  }[code] ?? '로그인에 실패했습니다.'
}

async function onSubmit() {
  if (!canSubmit.value) {
    error.value = '이메일과 비밀번호를 입력해주세요.'
    return
  }

  isSubmitting.value = true
  error.value = null
  success.value = null
  try {
    const result = await login({
      email: form.email,
      password: form.password,
    })
    auth.setUser(result.user)
    success.value = '로그인되었습니다.'
    window.setTimeout(() => {
      void router.push('/')
    }, 500)
  } catch (err) {
    error.value = errorMessage((err as Error).message)
  } finally {
    isSubmitting.value = false
  }
}
</script>

<template>
  <main class="login-page">
    <section class="login-shell" aria-labelledby="login-title">
      <aside class="login-brief">
        <div class="login-brief__mark">
          <ShieldCheck :size="26" aria-hidden="true" />
        </div>
        <p class="login-brief__eyebrow">BENCH MARK ACCESS</p>
        <h1 id="login-title">계정으로 돌아가기</h1>
        <p>
          기본 로그인은 USER 권한으로 일반 페이지를 이어서 사용합니다.
          관리와 방송 도구는 ADMIN 권한 계정에서만 열립니다.
        </p>
        <dl>
          <div>
            <dt>세션 상태</dt>
            <dd>로컬 저장</dd>
          </div>
          <div>
            <dt>보호 영역</dt>
            <dd>ADMIN</dd>
          </div>
        </dl>
      </aside>

      <form class="login-form" data-testid="login-form" @submit.prevent="onSubmit">
        <header>
          <LogIn :size="20" aria-hidden="true" />
          <strong>로그인</strong>
        </header>

        <label>
          <span><Mail :size="15" aria-hidden="true" /> 이메일</span>
          <input
            v-model="form.email"
            type="email"
            autocomplete="email"
            placeholder="you@example.com"
            data-testid="login-email"
            required
          />
        </label>

        <label>
          <span><LockKeyhole :size="15" aria-hidden="true" /> 비밀번호</span>
          <input
            v-model="form.password"
            type="password"
            autocomplete="current-password"
            placeholder="비밀번호"
            data-testid="login-password"
            required
          />
        </label>

        <p v-if="error" class="login-message login-message--error" data-testid="login-error">
          {{ error }}
        </p>
        <p v-if="success" class="login-message login-message--success" data-testid="login-success">
          {{ success }}
        </p>

        <button
          type="submit"
          class="login-submit"
          data-testid="login-submit"
          :disabled="!canSubmit"
        >
          {{ isSubmitting ? '로그인 중' : '로그인' }}
        </button>

        <p class="login-alt">
          계정이 없으면
          <router-link to="/auth/signup" data-testid="login-signup-link">회원가입</router-link>
        </p>
      </form>
    </section>
  </main>
</template>

<style scoped>
.login-page {
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

.login-shell {
  width: min(900px, 100%);
  display: grid;
  grid-template-columns: minmax(0, 0.9fr) minmax(320px, 1fr);
  border: 1px solid var(--color-border);
  background: var(--color-card);
}

.login-brief {
  padding: 2rem;
  background: #101318;
  color: #f8fafc;
}

.login-brief__mark {
  width: 3rem;
  height: 3rem;
  display: grid;
  place-items: center;
  border: 1px solid rgba(255, 255, 255, 0.22);
  background: rgba(255, 255, 255, 0.08);
}

.login-brief__eyebrow {
  margin: 1.5rem 0 0.5rem;
  color: #9fd3c7;
  font-size: 0.78rem;
  font-weight: 700;
  letter-spacing: 0.08em;
}

.login-brief h1 {
  margin: 0;
  font-size: clamp(1.8rem, 3vw, 2.8rem);
  line-height: 1.05;
}

.login-brief p {
  color: rgba(248, 250, 252, 0.72);
  line-height: 1.65;
}

.login-brief dl {
  display: grid;
  gap: 0.75rem;
  margin: 2rem 0 0;
}

.login-brief dl div {
  display: flex;
  justify-content: space-between;
  gap: 1rem;
  padding-top: 0.75rem;
  border-top: 1px solid rgba(255, 255, 255, 0.14);
}

.login-brief dt {
  color: rgba(248, 250, 252, 0.58);
}

.login-brief dd {
  margin: 0;
  font-weight: 700;
}

.login-form {
  display: grid;
  gap: 1rem;
  align-content: center;
  padding: 2rem;
  background: var(--color-bg);
}

.login-form header {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding-bottom: 0.25rem;
  font-size: 1.1rem;
}

.login-form label {
  display: grid;
  gap: 0.45rem;
}

.login-form label span {
  display: inline-flex;
  align-items: center;
  gap: 0.35rem;
  color: var(--color-muted);
  font-size: 0.9rem;
  font-weight: 650;
}

.login-form input {
  width: 100%;
  box-sizing: border-box;
  padding: 0.78rem 0.85rem;
  border: 1px solid var(--color-border);
  border-radius: 0;
  background: var(--color-card);
  color: var(--color-fg);
}

.login-form input:focus {
  border-color: #0f766e;
  outline: 2px solid rgba(15, 118, 110, 0.18);
  outline-offset: 0;
}

.login-message {
  margin: 0;
  padding: 0.75rem 0.85rem;
  border: 1px solid;
  font-size: 0.9rem;
}

.login-message--error {
  border-color: rgba(220, 38, 38, 0.32);
  background: rgba(220, 38, 38, 0.08);
  color: #b91c1c;
}

.login-message--success {
  border-color: rgba(15, 118, 110, 0.34);
  background: rgba(15, 118, 110, 0.08);
  color: #0f766e;
}

.login-submit {
  height: 2.85rem;
  border: 0;
  background: #0f766e;
  color: white;
  font-weight: 800;
  cursor: pointer;
}

.login-submit:disabled {
  background: var(--color-border);
  color: var(--color-muted);
  cursor: not-allowed;
}

.login-alt {
  margin: 0;
  color: var(--color-muted);
  font-size: 0.92rem;
  text-align: center;
}

.login-alt a {
  color: #0f766e;
  font-weight: 800;
  text-decoration: none;
}

@media (max-width: 760px) {
  .login-page {
    place-items: stretch;
    padding: 1rem;
  }

  .login-shell {
    grid-template-columns: 1fr;
  }

  .login-brief,
  .login-form {
    padding: 1.35rem;
  }
}
</style>
