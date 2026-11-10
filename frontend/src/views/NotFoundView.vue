<script setup lang="ts">
import { RouterLink } from 'vue-router'
</script>

<template>
  <div class="shell">
    <main class="shell__main">
      <section class="panel" aria-labelledby="not-found-title">
        <header class="panel__head">
          <h1 id="not-found-title" class="panel__title">페이지를 찾을 수 없습니다</h1>
          <p class="panel__hint">주소가 바뀌었거나 존재하지 않는 경로입니다.</p>
        </header>
        <RouterLink class="button button--quiet" :to="{ name: 'admin-login' }">
          로그인 화면으로
        </RouterLink>
      </section>
    </main>
  </div>
</template>
