import type { CatalogLeague, CollectionRun, CollectionTarget, TranslationEntry, RunStatus, TranslationChange } from '@/lib/api/managementTypes'
export interface ManagementState { version: 1; catalog_updated_at?: string; targets: CollectionTarget[]; runs: CollectionRun[]; translations: TranslationEntry[]; changes: Record<string, TranslationChange[]>; scenario: string; next_id: number }
export const catalog: CatalogLeague[] = [
  { id: 39, name: '프리미어리그', name_en: 'Premier League', country: 'England', seasons: [2026, 2025], standings: true },
  { id: 2, name: '챔피언스리그', name_en: 'UEFA Champions League', country: 'World', seasons: [2026, 2025], standings: true },
  { id: 3, name: '유로파리그', name_en: 'UEFA Europa League', country: 'World', seasons: [2026, 2025], standings: true },
  { id: 48, name: '카라바오컵', name_en: 'League Cup', country: 'England', seasons: [2026, 2025], standings: false },
  { id: 45, name: 'FA컵', name_en: 'FA Cup', country: 'England', seasons: [2026, 2025], standings: false },
  { id: 1, name: '월드컵', name_en: 'World Cup', country: 'World', seasons: [2026, 2022], standings: true },
  { id: 140, name: '라리가', name_en: 'La Liga', country: 'Spain', seasons: [2026, 2025], standings: true },
]
catalog.push(
  {id:7,name:'아시안컵',name_en:'Asian Cup',country:'World',seasons:[2027,2023],standings:true,type:'Cup',aliases:['AFC 아시안컵'],featured:true},
  {id:23,name:'동아시안컵',name_en:'EAFF E-1 Football Championship',country:'World',seasons:[2025,2021],standings:true,type:'Cup',aliases:['동아시아','동아시아컵','E-1','EAFF'],featured:true},
  {id:803,name:'아시안게임',name_en:'Asian Games',country:'World',seasons:[2022,2018],standings:true,type:'Cup',aliases:['아시안게임','아시아 경기'],featured:true},
  {id:897,name:'여자 아시안컵',name_en:'Asian Cup Women',country:'World',seasons:[2026,2022],standings:true,type:'Cup',aliases:['AFC 여자 아시안컵'],featured:true},
  {id:900039,name:'Premier League',name_en:'Premier League',country:'Sample Country',seasons:[2026,2025],standings:true,type:'League'},
)
for (const league of catalog) { league.type ??= [39,140].includes(league.id) ? 'League' : 'Cup'; league.country_label ??= ({World:'국제대회',England:'잉글랜드',Spain:'스페인'} as Record<string,string>)[league.country] || league.country; league.aliases ??= league.id===39 ? ['EPL','잉글랜드 프리미어리그'] : []; league.featured ??= league.id !== 900039 }
for (const league of catalog) league.logo_url = `https://media.api-sports.io/football/leagues/${league.id}.png`
export const affiliationTeams = [
  { id: 42, name: '아스널', name_en: 'Arsenal', logo_url: 'https://media.api-sports.io/football/teams/42.png' },
  { id: 50, name: '맨체스터 시티', name_en: 'Manchester City', logo_url: 'https://media.api-sports.io/football/teams/50.png' },
  { id: 40, name: '리버풀', name_en: 'Liverpool', logo_url: 'https://media.api-sports.io/football/teams/40.png' },
]
export function createSeed(now = Date.now()): ManagementState {
  const iso = (offset: number) => new Date(now - offset).toISOString()
  const targets: CollectionTarget[] = [39, 2, 3, 48, 45, 39].map((id, i) => {
    const league = catalog.find((item) => item.id === id)!
    return { id: i + 1, league_id: id, logo_url: league.logo_url, name: league.name, name_en: league.name_en, country: league.country, season: i === 5 ? 2025 : 2026, is_active: i !== 4, include_details: true, include_players: i !== 3, include_standings: league.standings, fixture_limit: i === 2 ? 10 : null, initial_status: i === 3 ? '미수집' : i === 2 ? '일부 적재' : '최초 수집 완료', last_sync: i === 3 ? null : iso(3_600_000 + i * 900_000) }
  })
  const statuses: RunStatus[] = ['succeeded', 'partial_failed', 'cancelled', 'succeeded', 'interrupted', 'failed']
  const runs: CollectionRun[] = statuses.map((status, i) => {
    const started = iso((i + 1) * 43_200_000)
    const partial = status !== 'succeeded'
    return { id: `sample-${1006 - i}`, mode: i % 2 ? 'initial' : 'refresh', status, created_at: started, started_at: started, finished_at: new Date(new Date(started).getTime() + 66_000).toISOString(), cancel_requested_at: status === 'cancelled' ? started : null, actor: i % 2 ? '스트리머 지민' : '정기 수집', parent_run_id: null, progress: status === 'cancelled' || status === 'interrupted' ? 45 : 100, stage: '작업 종료', items: [0, 1].map((n) => ({ target_id: n + 1, name: targets[n].name, season: targets[n].season, status: partial && n === 1 ? status : 'succeeded', total: 80, saved: partial && n === 1 ? 24 : 80, failed: status === 'partial_failed' || status === 'failed' ? (n === 1 ? 4 : 0) : 0, pending: partial && n === 1 ? (status === 'partial_failed' || status === 'failed' ? 52 : 56) : 0 })), logs: [{ at: started, message: '선택한 리그·시즌의 수집을 시작했습니다.' }, { at: started, message: partial ? '처리 결과를 저장했습니다. 대상별 결과를 확인하세요.' : '모든 대상의 수집과 저장을 완료했습니다.' }] }
  })
  for (const run of runs) {
    if (['failed', 'partial_failed'].includes(run.status)) {
      run.logs.push(
        { at: run.finished_at!, code: 'API_TIMEOUT', level: 'warning', target_id: 2, stage: '경기 상세', attempt: 1, max_attempts: 3, message: 'ReadTimeout: GET /fixtures/events timeout after 30s' },
        { at: run.finished_at!, code: 'API_TIMEOUT', level: 'warning', target_id: 2, stage: '경기 상세', attempt: 2, max_attempts: 3, message: 'ReadTimeout: GET /fixtures/events timeout after 30s' },
        { at: run.finished_at!, code: run.status === 'failed' ? 'DB_WRITE_FAILED' : 'API_TIMEOUT', level: 'error', target_id: 2, stage: run.status === 'failed' ? '결과 저장' : '경기 상세', attempt: 3, max_attempts: 3, message: run.status === 'failed' ? 'IntegrityError: fixture upsert failed; transaction rolled back' : 'ReadTimeout: retries exhausted for /fixtures/events' },
        { at: run.finished_at!, code: 'API_RATE_LIMIT', level: 'error', target_id: 2, stage: '선수 통계', attempt: 3, max_attempts: 3, message: 'HTTP 429: API request limit reached; retries exhausted' },
      )
    }
  }
  const classifiedRun=runs.find(run=>run.id==='sample-1006')!
  classifiedRun.logs=[
    {at:classifiedRun.started_at,message:'Premier League (#39) season 2026: detail: /fixtures/events fixture=1557641 done',analysis:{code:'API_RESPONSE_RECEIVED',title:'경기 이벤트 조회 완료 · 경기 #1557641',action:'',category:'events',category_label:'경기 이벤트',level:'info',stage:'경기 이벤트',target:'Premier League · 2026 시즌',classified:true}},
    {at:classifiedRun.started_at,message:'League Cup (#48) season 2026: players page=67/103 rows=20',analysis:{code:'PLAYER_PAGE_PROCESSED',title:'선수 기록 처리 · 67/103페이지 · 20개',action:'',category:'players',category_label:'선수 기록',level:'info',stage:'선수 기록',target:'League Cup · 2026 시즌',classified:true}},
    {at:classifiedRun.finished_at!,message:'daily-sync: skipped because distributed lock is held',analysis:{code:'RUN_SKIPPED',title:'다른 수집이 실행 중이어서 이번 실행을 건너뜀',action:'',category:'run',category_label:'실행 제어',level:'info',stage:null,target:null,classified:true}},
  ]
  const entries = [
    ['league', 'Premier League', '잉글랜드 · #39', '프리미어리그', 'EPL'],
    ['league', 'UEFA Champions League', '유럽 · #2', '챔피언스리그', 'UCL'],
    ['league', 'FA Cup', '잉글랜드 · #45', null, null],
    ['team', 'Arsenal', '프리미어리그 · #42', '아스널', '아스널'],
    ['team', 'Tottenham Hotspur', '프리미어리그 · #47', '토트넘 홋스퍼', null],
    ['team', 'Liverpool', '프리미어리그 · #40', '리버풀', '리버풀'],
    ['player', 'Bukayo Saka', '아스널 · #1460', '부카요 사카', '사카'],
    ['player', 'Phil Foden', '맨체스터 시티 · #631', null, null],
    ['player', 'Mohamed Salah', '선수 샘플 · #306', '모하메드 살라', '살라'],
    ['coach', 'Mikel Arteta', '감독 샘플 · #641', '미켈 아르테타', '아르테타'],
    ['coach', 'Arne Slot', '감독 샘플 · #864', null, null],
    ['coach', 'Pep Guardiola', '감독 샘플 · #4', '펩 과르디올라', '과르디올라'],
  ] as const
  const translations: TranslationEntry[] = entries.map((row, i) => ({ id: i + 1, type: row[0], original: row[1], context: row[2], name_ko: row[3], short_name_ko: row[4], protected: i % 3 === 0, version: 1, editor: i % 3 === 0 ? '스트리머 지민' : '자동번역', updated_at: iso(7_200_000 + i * 120_000) }))
  const affiliations = [[{league_id:39,team_id:42},{league_id:2,team_id:42}], [{league_id:39,team_id:50}], [{league_id:39,team_id:40}]]
  translations.filter(row => row.type === 'player').forEach((row,i) => { row.affiliations = affiliations[i] })
  translations.filter(row => row.type === 'coach').forEach((row,i) => { row.affiliations = affiliations[i === 1 ? 2 : i === 2 ? 1 : 0] })
  return { version: 1, targets, runs, translations, changes: {}, scenario: 'normal', next_id: 20 }
}
