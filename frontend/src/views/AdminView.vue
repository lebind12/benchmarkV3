<script setup lang="ts">
import ManagementView from './ManagementView.vue'
import { managementApi } from '@/lib/api/management'
</script>
<template><div class="admin-news-entry app-container"><RouterLink to="/admin/news-analysis">글 속 축구 정보</RouterLink></div><ManagementView :api="managementApi" /></template>
<style scoped>.admin-news-entry{position:absolute;top:calc(var(--header-height) + 6px);right:16px;width:auto;padding:0;font-size:12px;z-index:1}.admin-news-entry a{color:#2563eb;text-decoration:underline;text-underline-offset:3px}</style>
