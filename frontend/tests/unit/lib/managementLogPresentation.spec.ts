import { describe, expect, it } from 'vitest'
import { presentLog, logStatistics } from '@/components/management/logPresentation'
import { createSeed } from '../../fixtures/management/data'

describe('management log presentation', () => {
  it('uses server classification for normal historical progress and preserves raw data',()=>{
    const log=createSeed().runs.find(run=>run.id==='sample-1006')!.logs[0]
    expect(presentLog(log)).toMatchObject({title:'경기 이벤트 조회 완료 · 경기 #1557641',category:'events',level:'info',classified:true})
    expect(log.message).toContain('/fixtures/events fixture=1557641 done')
  })
  it('shows classified retained legacy causes and preserves the unclassified count',()=>{
    const run=createSeed().runs[0]
    run.logs=[];run.log_statistics_scope='retained';run.log_unclassified_count=2
    run.log_statistics={API_PLAN_RESTRICTED:{code:'API_PLAN_RESTRICTED',errors:4,warnings:0,target_ids:[]}}
    const stats=logStatistics([run])
    expect(stats.groups[0]).toMatchObject({title:'요금제·시즌 접근 제한',errors:4})
    expect(stats.unknown).toBe(2)
  })
  it('uses stable codes for Korean labels and preserves the original message', () => {
    const log = { at: '2026-10-25', message: 'HTTP 429: upstream message', code: 'API_RATE_LIMIT', level: 'error' as const }
    expect(presentLog(log)).toMatchObject({ title: '외부 API 호출 한도 초과', level: 'error', code: 'API_RATE_LIMIT' })
    expect(log.message).toBe('HTTP 429: upstream message')
  })
  it('does not invent a reason or severity for unstructured historical messages', () => {
    expect(presentLog({ at: '', message: 'unknown response 429 failure' })).toMatchObject({ title: '기존 처리 기록 · 원문 확인 필요', classified: false, level: 'info' })
    expect(presentLog({ at: '', message: 'foreign message', code: 'NEW_CODE', level: 'error' })).toMatchObject({ code: 'UNCLASSIFIED', level: 'error' })
  })
  it('maps known historical progress to Korean while leaving the raw message unchanged', () => {
    const log = { at: '', message: 'daily-sync: loaded 6 configured specs' }
    expect(presentLog(log)).toMatchObject({ title: '수집 설정을 불러왔습니다.', classified: true })
    expect(log.message).toBe('daily-sync: loaded 6 configured specs')
  })
  it('recognises a narrow existing failure format without inferring a cause', () => {
    expect(presentLog({ at: '', message: 'EPL 2026: fixtures failed: remote failure' })).toMatchObject({ title: '경기 목록 수집 실패 · 원인 미분류', code: 'UNCLASSIFIED', level: 'error' })
  })
  it('counts retries separately from errors and counts affected runs and targets', () => {
    const runs = createSeed().runs.filter(run => ['failed', 'partial_failed'].includes(run.status))
    const stats = logStatistics(runs)
    expect(stats.groups.find(group => group.code === 'API_TIMEOUT')).toMatchObject({ errors: 1, warnings: 4 })
    expect(stats.groups.find(group => group.code === 'API_TIMEOUT')?.runs.size).toBe(2)
    expect(stats.groups.find(group => group.code === 'API_TIMEOUT')?.targets.size).toBe(2)
    expect(stats.groups.find(group => group.code === 'DB_WRITE_FAILED')?.errors).toBe(1)
    expect(stats.unknown).toBe(4)
    expect(logStatistics([]).groups).toEqual([])
  })
})


it('uses complete server counters instead of recounting a truncated log tail', () => {
  const run = createSeed().runs[0]
  run.logs = [{at: '', message: 'timeout', code: 'API_TIMEOUT', level: 'error'}]
  run.log_statistics = { API_TIMEOUT: {code:'API_TIMEOUT', errors:1100, warnings:2, target_ids:[1]} }
  expect(logStatistics([run]).groups[0]).toMatchObject({code:'API_TIMEOUT',errors:1100,warnings:2})
})


it('does not count an explicitly informational progress summary as a second failure', () => {
  expect(presentLog({at:'',message:'EPL: teams failed: timeout',code:'PROGRESS',level:'info'}).level).toBe('info')
})
