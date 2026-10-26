import type { RunLog, CollectionRun } from '@/lib/api/managementTypes'

const events: Record<string, { title: string; action: string }> = {
  API_PLAN_RESTRICTED: { title: '요금제·시즌 접근 제한', action: '당시 API 응답의 지원 시즌과 계정 설정을 확인하세요.' },
  API_TIMEOUT: { title: '외부 API 응답 지연', action: '제한 시간 내 응답을 받지 못했습니다. 최대 재시도 후에도 실패한 대상만 다시 실행하세요.' },
  API_RATE_LIMIT: { title: '외부 API 호출 한도 초과', action: '호출 한도 회복 후 다시 실행하세요. 동시에 실행 중인 작업과 사용량을 확인하세요.' },
  DB_RETRY: { title: 'DB 잠금 충돌 재시도', action: '일시적인 잠금 충돌로 저장 작업을 재시도합니다.' },
  DB_WRITE_FAILED: { title: '데이터 저장 실패', action: '저장 오류 원문과 실패 대상을 확인하세요. 제약 조건 오류는 원인 해결 후 재실행이 필요합니다.' },
  API_UPSTREAM_ERROR: { title: '외부 API 서버 오류', action: '재시도 후에도 실패한 대상을 확인하고 이후 다시 실행하세요.' },
  API_REQUEST_FAILED: { title: '외부 API 요청 실패', action: '요청 경로와 응답 원문을 확인하세요.' },
  API_AUTH_FAILED: { title: '외부 API 인증 실패', action: 'API-Football 인증 설정을 확인해야 합니다.' },
  RUN_FINISHED: { title: '수집 실행 종료', action: '' },
  RUN_FAILED: { title: '수집 실행 실패', action: '오류 원문과 실행 설정을 확인하세요.' },
  TARGET_FAILED: { title: '대상 수집 실패', action: '대상과 처리 단계의 원문을 확인하세요.' },
  RUN_INTERRUPTED: { title: '수집 프로세스 중단', action: '저장된 데이터는 유지됩니다. 미완료 대상을 다시 실행하세요.' },
  RUN_CANCELLED: { title: '수집 취소 완료', action: '이미 저장된 데이터는 유지됩니다.' },
  RUN_STARTED: { title: '수집 시작', action: '' },
  RUN_COMPLETED: { title: '수집 완료', action: '' },
}
export const stageLabels: Record<string, string> = { teams: '팀', fixtures: '경기 목록', standings: '순위표', players: '선수 통계' }
export function presentLog(log: RunLog) {
  if (log.analysis) return {...log.analysis}
  const event = log.code ? events[log.code] : undefined
  // Only explicitly recognised legacy formats are labelled. Unknown messages remain intact.
  const legacy = (!log.code || log.code === 'PROGRESS') ? log.message.match(/^(.+): (teams|fixtures|standings|players) failed: (.+)$/) : null
  const legacyInfo = (!log.code || log.code === 'PROGRESS') ? [
    { pattern: /^daily-sync: run started origin=(.+)$/, title: '수집 실행을 시작했습니다.' },
    { pattern: /^daily-sync: measuring update size$/, title: '갱신 대상 건수를 확인합니다.' },
    { pattern: /^daily-sync: loaded (\d+) configured specs$/, title: '수집 설정을 불러왔습니다.' },
    { pattern: /^daily-sync: run finished status=(.+) duration=(.+)s$/, title: '수집 실행을 종료했습니다.' },
    { pattern: /^(.+): complete$/, title: '대상의 수집을 완료했습니다.' },
    { pattern: /^(.+): start$/, title: '대상의 수집을 시작했습니다.' },
  ].find(rule => rule.pattern.test(log.message)) : undefined
  const error = log.level === 'error' || (!log.level && !!legacy)
  const warning = log.level === 'warning'
  const category = legacy ? legacy[2] : event ? (log.code!.startsWith('API_') || log.code!.startsWith('DB_') ? 'error' : 'run') : legacyInfo ? (/loaded|measuring/.test(log.message) ? 'preparation' : 'run') : 'unclassified'
  const categoryLabel = ({error:'요청·저장 오류',run:'실행 제어',preparation:'수집 준비',unclassified:'미분류'} as Record<string,string>)[category] ?? stageLabels[category]
  return {
    code: event ? log.code! : error || warning ? 'UNCLASSIFIED' : 'INFO',
    title: event?.title ?? (legacy ? `${stageLabels[legacy[2]]} 수집 실패 · 원인 미분류` : log.code && log.code !== 'PROGRESS' ? '알 수 없는 이벤트 · 원문 확인 필요' : legacyInfo?.title ?? (/[가-힣]/.test(log.message) ? log.message : '기존 처리 기록 · 원문 확인 필요')),
    action: event?.action ?? (error ? '기록된 원문을 확인하세요. 이 로그만으로 구체적인 원인을 확정할 수 없습니다.' : ''),
    level: error ? 'error' : warning ? 'warning' : 'info',
    stage: log.stage ?? (legacy ? stageLabels[legacy[2]] : null),
    category,
    category_label: categoryLabel,
    target: null as string | null,
    classified: !!event || !!legacy || !!legacyInfo,
  }
}
export function logStatistics(runs: CollectionRun[]) {
  const groups = new Map<string, { code: string; title: string; errors: number; warnings: number; runs: Set<string>; targets: Set<string> }>()
  let unknown = 0
  for (const run of runs) {
    unknown += run.log_unclassified_count ?? run.logs.filter(log => !presentLog(log).classified && !log.level).length
    if (run.log_statistics) {
      for (const entry of Object.values(run.log_statistics)) {
        const code = events[entry.code] ? entry.code : 'UNCLASSIFIED'
        const group = groups.get(code) ?? { code, title: events[entry.code]?.title ?? '원인 미분류', errors: 0, warnings: 0, runs: new Set<string>(), targets: new Set<string>() }
        group.errors += entry.errors; group.warnings += entry.warnings; group.runs.add(run.id)
        entry.target_ids.forEach(id => group.targets.add(`${run.id}:${id}`))
        groups.set(code, group)
      }
      continue
    }
    for (const log of run.logs) {
    const view = presentLog(log)
    if (view.level === 'info') continue
    const group = groups.get(view.code) ?? { code: view.code, title: view.code === 'UNCLASSIFIED' ? '원인 미분류' : view.title, errors: 0, warnings: 0, runs: new Set<string>(), targets: new Set<string>() }
    if (view.level === 'error') group.errors++; else group.warnings++
    group.runs.add(run.id)
    if (log.target_id !== undefined) group.targets.add(`${run.id}:${log.target_id}`)
    groups.set(view.code, group)
    }
  }
  return { groups: [...groups.values()], unknown }
}
