<script setup lang="ts">
import ManagementView from './ManagementView.vue'
import { managementApi } from '@/lib/api/management'
</script>
<template><ManagementView :api="managementApi" /></template>
