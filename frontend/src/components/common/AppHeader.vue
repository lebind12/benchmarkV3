<script setup lang="ts">
import { computed } from 'vue'
import { useAuthStore } from '@/stores/auth'
import { Button } from '@/components/ui/button'

const auth = useAuthStore()

const tabs = computed(() => {
  const base = [
    { path: '/', label: '홈' },
    { path: '/fixtures', label: '경기' },
    { path: '/standings', label: '순위' },
    { path: '/teams', label: '팀' },
    { path: '/players', label: '선수' },
    { path: '/stats', label: '스탯' },
    { path: '/news', label: '뉴스' },
  ]
  if (auth.isAdmin) {
    base.push({ path: '/admin', label: '관리' })
    base.push({ path: '/broadcast', label: '방송' })
  }
  return base
})

function toggleTheme() {
  const isDark = document.documentElement.classList.toggle('dark')
  localStorage.setItem('theme', isDark ? 'dark' : 'light')
}
</script>
<template>
  <header class="hdr" role="banner">
    <div class="hdr__inner app-container">
      <div class="hdr__logo">⚽ 벤치마크</div>
      <nav class="hdr__nav" aria-label="주요 메뉴">
        <router-link
          v-for="t in tabs"
          :key="t.path"
          :to="t.path"
          class="hdr__tab"
          active-class="hdr__tab--active"
          :data-testid="`nav-${t.label}`"
        >
          {{ t.label }}
        </router-link>
      </nav>
      <div class="hdr__right">
        <button
          type="button"
          class="hdr__icon"
          aria-label="테마 토글"
          data-testid="theme-toggle"
          @click="toggleTheme"
        >
          ☾
        </button>
        <router-link
          v-if="!auth.isLoggedIn"
          class="hdr__login"
          data-testid="auth-login"
          to="/auth/login"
        >
          로그인
        </router-link>
        <router-link
          v-if="!auth.isLoggedIn"
          to="/auth/signup"
          class="hdr__signup"
          data-testid="auth-signup"
        >
          회원가입
        </router-link>
        <Button
          v-else
          variant="outline"
          size="sm"
          class="hdr__login"
          data-testid="auth-profile"
        >
          프로필
        </Button>
      </div>
    </div>
  </header>
</template>
<style scoped>
.hdr {
  height: var(--header-height);
  border-bottom: 1px solid var(--color-border);
  background: var(--color-bg);
}
.hdr__inner {
  height: 100%;
  display: flex;
  align-items: center;
  gap: 16px;
}
.hdr__logo {
  flex: 0 0 auto;
  font-weight: 700;
}
.hdr__nav {
  min-width: 0;
  display: flex;
  gap: 16px;
  flex: 1 1 auto;
  overflow-x: auto;
  overflow-y: hidden;
  scrollbar-width: none;
}
.hdr__nav::-webkit-scrollbar { display: none; }
.hdr__tab {
  flex: 0 0 auto;
  text-decoration: none;
  color: var(--color-muted);
  padding: 6px 8px;
  border-radius: 4px;
}
.hdr__tab--active { color: var(--color-fg); font-weight: 600; }
.hdr__right {
  flex: 0 0 auto;
  display: flex;
  gap: 8px;
  align-items: center;
}
.hdr__icon,
.hdr__login,
.hdr__signup {
  background: transparent;
  border: 1px solid var(--color-border);
  color: var(--color-fg);
  padding: 4px 10px;
  border-radius: 6px;
  cursor: pointer;
  text-decoration: none;
}

@media (max-width: 560px) {
  .hdr__inner {
    gap: 8px;
  }

  .hdr__logo {
    max-width: 5.4rem;
    overflow: hidden;
    white-space: nowrap;
  }

  .hdr__nav {
    gap: 6px;
  }

  .hdr__tab {
    padding-inline: 4px;
  }

  .hdr__right {
    gap: 4px;
  }

  .hdr__icon,
  .hdr__login,
  .hdr__signup {
    padding-inline: 7px;
  }
}
</style>
