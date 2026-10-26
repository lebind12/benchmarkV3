import type { CollectionRun, RunStatus } from '@/lib/api/managementTypes'

export const statusLabels: Record<RunStatus, string> = {
  queued: '준비 중', running: '수집 중', cancel_requested: '취소 요청됨', succeeded: '완료',
  partial_failed: '부분 실패', failed: '실패', cancelled: '취소됨', interrupted: '중단됨',
}
export const entityLabels = { league: '리그', team: '팀', player: '선수', coach: '감독' } as const
export function dateTime(value: string | null) {
  if (!value) return '기록 없음'
  return new Intl.DateTimeFormat('ko-KR', { timeZone: 'Asia/Seoul', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hour12: false }).format(new Date(value))
}
export function dayKey(value: string) {
  return new Intl.DateTimeFormat('sv-SE', { timeZone: 'Asia/Seoul', year: 'numeric', month: '2-digit', day: '2-digit' }).format(new Date(value))
}
export function runTotals(run: CollectionRun) {
  return run.items.reduce((sum, item) => ({ saved: sum.saved + item.saved, failed: sum.failed + item.failed, pending: sum.pending + item.pending, total: sum.total + item.total }), { saved: 0, failed: 0, pending: 0, total: 0 })
}
export function retryIds(run: CollectionRun) {
  return run.items.filter((item) => item.status !== 'succeeded' && (item.failed > 0 || item.pending > 0 || ['cancelled', 'interrupted', 'failed', 'partial_failed'].includes(item.status))).map((item) => item.target_id)
}
