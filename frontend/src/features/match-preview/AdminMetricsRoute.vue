<script setup lang="ts">
/**
 * 운영 지표 → 실행 검사 연결 (MP-04 공유 라우터 소유).
 *
 * MP-08의 `PreviewMetricsView.vue`는 자기 파일을 소유하므로 여기서 고치지 않는다.
 * 이 얇은 연결 화면이 그 화면을 그대로 띄우고 `select-run` 이벤트만 받아 실행 검사로
 * 이동한다. 지표 화면을 고치지 않고도 "표본 → 그 실행의 시도 원문" 이동이 성립한다.
 *
 * 필터 유지에 대해 정확히 적어 둔다: 지표 화면은 지금 선택한 필터를 이벤트로 함께
 * 내보내지 않는다. 그래서 이 연결은 실행 ID만 넘기고, 필터를 그대로 되돌려 붙이는
 * 일은 하지 않는다(없는 값을 만들어 붙이지 않는다). 필터 echo가 필요하면 MP-08이
 * `select-run`에 필터를 함께 내보내야 하며, 그 요구는 조정자에게 보고한다.
 */
import { useRouter } from 'vue-router'
import PreviewMetricsView from './PreviewMetricsView.vue'

const router = useRouter()

async function openRun(runId: string) {
  // 실행 목록 화면이 `run` 질의를 보고 해당 실행의 검사 화면을 연다.
  await router.push({ name: 'preview-runs', query: { run: runId } })
}
</script>

<template>
  <PreviewMetricsView @select-run="openRun" />
</template>
