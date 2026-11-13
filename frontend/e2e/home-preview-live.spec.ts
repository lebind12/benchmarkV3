/**
 * 홈 저장 프리뷰 e2e (합성 응답).
 *
 * 이 파일이 검증하는 것은 **합성 문서 응답**에 대한 화면 동작이다. 실제 승인된 저장
 * 문서의 실화면 성공을 뜻하지 않는다. 실제 문서 확인은 조정자가 승인 기록과 함께 한다.
 *
 * 계약이 바뀐 지점: 홈은 이제 `/api/v1/home/fixtures/{id}/document` 하나만 읽고
 * `/prematch`를 호출하지 않는다. 옛 UI(`.hp-lead`·출처 접이식·자료 확인 현황·
 * key-absence·player-watchpoint·생성 예정 시각)는 이번 설계에서 제거됐다. 그 자리는
 * 저장 본문(`match-preview-body`)의 카드·본문 섹션과 단일 없음 안내가 대신한다.
 */
import { test, expect } from '@playwright/test'
import { readFileSync } from 'node:fs'
const recommendations = JSON.parse(readFileSync(new URL('../src/mocks/home-preview/recommendations.json', import.meta.url), 'utf8'))

const PLAYER_PHOTO = 'https://media.api-sports.io/football/players/1100.png'
const TEAM_LOGO = 'https://media.api-sports.io/football/teams/50.png'

function fixtureBlock(fixtureId: number) {
  const row = recommendations.items.find((item: any) => item.fixture_id === fixtureId) ?? recommendations.items[0]
  return {
    external_id: fixtureId,
    kickoff_at: row.kickoff_at,
    league: row.competition.name,
    home: { external_id: row.home.external_id, name: row.home.name, logo_url: TEAM_LOGO },
    away: { external_id: row.away.external_id, name: row.away.name, logo_url: null },
  }
}

function section(sectionId: string, title: string, body: string, structured?: unknown) {
  return {
    section_result_id: `${sectionId}-1`,
    run_id: 'run-synthetic-1',
    workflow_id: sectionId,
    workflow_version: 'v1',
    version: 1,
    title,
    body,
    sources: [{ label: '경기 기록', kind: 'db', url: 'https://source.example.test/a' }],
    quality: 'ready',
    partial: false,
    created_at: '2026-11-12T12:00:00Z',
    ...(structured === undefined ? {} : { structured }),
  }
}

/** 저장 문서 하나. 카드(선수·부상·매체·배당·전망)와 본문 섹션을 함께 담는다. */
function document(fixtureId: number) {
  const fixture = fixtureBlock(fixtureId)
  return {
    schema_version: '1.0',
    fixture_id: fixtureId,
    status: 'available',
    reason: null,
    reason_text: null,
    absence: null,
    saved_at: '2026-11-12T12:00:00Z',
    run_id: 'run-synthetic-1',
    complete: true,
    fixture,
    headline: '주목 선수',
    sections: [
      section('section_players', '주목 선수', '선정 선수: 홀란드\n선정 이유: 최근 5경기 6골', {
        structured_version: 'mp11-structured-2',
        workflow_id: 'section_players',
        players: [
          { player: '홀란드', reason: '최근 5경기 6골', team: fixture.home.name, external_player_id: 1100, team_external_id: fixture.home.external_id, photo_url: PLAYER_PHOTO },
        ],
        injuries: [],
        media: [],
        odds: [],
        forecast: null,
      }),
      section('section_availability', '부상·결장', '핵심 수비수 결장', {
        structured_version: 'mp11-structured-2',
        workflow_id: 'section_availability',
        players: [],
        injuries: [
          { player: '디아스', team: fixture.away.name, status: 'out', summary: '햄스트링 부상', external_player_id: 1101, team_external_id: fixture.away.external_id, photo_url: null },
        ],
        media: [],
        odds: [],
        forecast: null,
      }),
      section('section_outlook', '외부 매체 전망', '매체는 접전을 예상합니다.', {
        structured_version: 'mp11-structured-2',
        workflow_id: 'section_outlook',
        players: [],
        injuries: [],
        media: [{ publisher: '스카이 스포츠', statement: '매체는 접전을 예상합니다.', predicted_score: '2-1', published_at: '2026-11-12T09:00:00Z' }],
        odds: [],
        forecast: null,
      }),
      section('section_odds', '배당', '정규시간 승무패 배당입니다.', {
        structured_version: 'mp11-structured-2',
        workflow_id: 'section_odds',
        players: [],
        injuries: [],
        media: [],
        odds: [{ bookmaker: '테스트북', market: '1X2', observedAt: '2026-11-12T09:00:00Z', home: '1.65', draw: '3.80', away: '4.50' }],
        forecast: null,
      }),
      section('section_ai_forecast', 'AI 경기 전망', `저장된 전망 본문 경기 ${fixtureId}`, {
        structured_version: 'mp11-structured-2',
        workflow_id: 'section_ai_forecast',
        players: [],
        injuries: [],
        media: [],
        odds: [],
        forecast: { lean: 'home', score: '2-1', reasoning: ['최근 득점 흐름이 좋습니다.'], note: null },
      }),
    ],
  }
}

/** 문서 없음. ┃absence┃ 상태만 다르다. */
function absentDocument(fixtureId: number, state: 'upcoming' | 'upcoming_overdue' | 'past' = 'upcoming') {
  return {
    schema_version: '1.0',
    fixture_id: fixtureId,
    status: 'none',
    reason: 'no_stored_run',
    reason_text: '이 경기의 저장 실행이 없습니다.',
    absence: { state, remaining_seconds: state === 'past' ? -3600 : 3600 },
    saved_at: null,
    run_id: null,
    complete: null,
    fixture: fixtureBlock(fixtureId),
    headline: null,
    sections: [],
  }
}

/** 사진 요청은 합성 SVG로 응답해 실제 외부 호출을 만들지 않는다. */
async function stubImages(page: any) {
  await page.route('https://media.api-sports.io/**', (route: any) =>
    route.fulfill({ contentType: 'image/svg+xml', body: '<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10"><rect width="10" height="10" fill="gray"/></svg>' }),
  )
}

test('synthetic stored document renders on first entry and follows the selected fixture', async ({ page }) => {
  const errors: string[] = []
  page.on('pageerror', error => errors.push(error.message))
  await stubImages(page)
  await page.route('**/api/v1/home/**', async route => {
    const path = new URL(route.request().url()).pathname
    if (path.endsWith('/recommendations')) return route.fulfill({ json: recommendations })
    if (path.endsWith('/document')) return route.fulfill({ json: document(Number(path.split('/').at(-2))) })
    return route.fulfill({ json: { items: [], rows: [] } })
  })
  await page.goto('/')
  const home = page.getByTestId('home-preview-real')
  await expect(home.getByRole('heading', { name: '오늘의 매치', exact: true })).toBeVisible()

  // 첫 진입: 별도 클릭 없이 기본 선택 경기의 저장 본문이 보인다.
  const body = home.getByTestId('match-preview-body')
  await expect(body).toBeVisible()
  await expect(home.getByTestId('stored-preview-document')).toBeVisible()
  await expect(body.locator('.mpv-entry__name').first()).toContainText('홀란드')
  await expect(home.locator('.hp-tools')).toHaveCount(0)
  await expect(page.getByText('일정 타임라인', { exact: true })).toHaveCount(0)

  // 저장 시각 표기. 옛 '생성 예정' 문구는 없음 안내로 옮겼다.
  await expect(home.getByTestId('preview-generation-time')).toContainText('저장')

  // 카드가 저장 구조 값으로 그려진다: 예상 점수·우세팀·매체·배당.
  await expect(body.locator('.mpv-prediction__score')).toContainText('2')
  await expect(body.locator('.mpv-media__text')).toContainText('접전')
  const oddsCells = body.locator('.mpv-odds__cell dd')
  await expect(oddsCells).toHaveText(['1.65', '3.80', '4.50'])
  await expect(body.locator('.mpv-entry__photo img').first()).toHaveAttribute('src', PLAYER_PHOTO)
  // 팀 로고도 DOC-PRESENT 필수 항목이다. 서버가 준 주소만 쓰고 추측해 만들지 않는다.
  await expect(body.locator('.mpv-team__head img').first()).toHaveAttribute('src', TEAM_LOGO)

  // 섹션별 흐림→선명 대상에 --reveal 값이 실제로 설정된다.
  await expect(home.locator('.hp-stored-document .mpv-section').first()).toHaveAttribute('style', /--reveal/)

  // 선택 전환: 경기 ID·본문이 함께 바뀐다.
  await expect(home.getByTestId('selected-preview')).toHaveAttribute('data-fixture-id', '90002')
  await home.getByRole('button', { name: '다음 추천 경기', exact: true }).click()
  await expect(home.getByTestId('selected-preview')).toHaveAttribute('data-fixture-id', '90001')
  await expect(body).toBeVisible()
  // 배당 라벨이 **선택 경기의 두 팀**을 따라간다(옛 'odds follow selected teams' 요구).
  const nextFixture = fixtureBlock(90001)
  await expect(body.locator('.mpv-odds__cell dt').first()).toHaveText(`${nextFixture.home.name} 승`)
  await expect(body.locator('.mpv-odds__cell dt').last()).toHaveText(`${nextFixture.away.name} 승`)

  // 옛 대진을 요약하는 접이식/아코디언 UI는 홈에서 제거됐고, 같은 정보는 저장 본문 카드가 보여준다.
  await expect(home.getByTestId('preview-sources')).toHaveCount(0)
  await expect(home.getByTestId('data-gap-summary')).toHaveCount(0)
  expect(errors).toEqual([])
})

test('late document for an old selection cannot replace the new selection', async ({ page }) => {
  let release: (() => void) | undefined
  await stubImages(page)
  await page.route('**/api/v1/home/**', async route => {
    const path = new URL(route.request().url()).pathname
    if (path.endsWith('/recommendations')) return route.fulfill({ json: recommendations })
    if (path.endsWith('/document')) {
      const id = Number(path.split('/').at(-2))
      // 첫 경기(기본 선택 90002)의 응답을 붙잡아 두고, 전환 뒤에 늦게 푼다.
      if (id === 90002) await new Promise<void>(resolve => { release = resolve })
      return route.fulfill({ json: document(id) }).catch(() => {})
    }
    return route.fulfill({ json: { items: [], rows: [] } })
  })
  await page.goto('/')
  const home = page.getByTestId('home-preview-real')
  await expect(home.getByTestId('selected-preview')).toHaveAttribute('data-fixture-id', '90002')
  await home.getByRole('button', { name: '다음 추천 경기', exact: true }).click()
  await expect(home.getByTestId('selected-preview')).toHaveAttribute('data-fixture-id', '90001')
  await expect(home.getByTestId('match-preview-body')).toContainText('경기 90001')
  // 붙잡아 둔 이전 경기 응답이 늦게 도착해도 현재 경기 본문을 덮지 않는다.
  release?.()
  await expect(home.getByTestId('selected-preview')).toHaveAttribute('data-fixture-id', '90001')
  await expect(home.getByTestId('match-preview-body')).toContainText('경기 90001')
  await expect(home.getByTestId('match-preview-body')).not.toContainText('경기 90002')
})

test('contract-violating document response shows the error state instead of a body', async ({ page }) => {
  // 옛 '모의 payload 거부' 요구를 현재 계약으로 옮긴 검사다. 모의 결과 차단은 이제 서버가
  // 하므로(백엔드 직접 검사), 프론트가 지켜야 할 것은 **계약 위반 응답을 성공으로 그리지
  // 않는 것**이다. available 상태인데 sections가 비면 계약 위반이다.
  await page.route('**/api/v1/home/**', async route => {
    const path = new URL(route.request().url()).pathname
    if (path.endsWith('/recommendations')) return route.fulfill({ json: recommendations })
    if (path.endsWith('/document')) {
      const value = document(Number(path.split('/').at(-2)))
      return route.fulfill({ json: { ...value, sections: [] } })
    }
    return route.fulfill({ json: { items: [], rows: [] } })
  })
  await page.goto('/')
  const home = page.getByTestId('home-preview-real')
  await expect(home.getByTestId('stored-document-error')).toBeVisible()
  await expect(home.getByTestId('match-preview-body')).toHaveCount(0)
  await expect(home.getByTestId('stored-document-absent')).toHaveCount(0)
})

test('document read error stays an error and never becomes the absence notice', async ({ page }) => {
  await page.route('**/api/v1/home/**', async route => {
    const path = new URL(route.request().url()).pathname
    if (path.endsWith('/recommendations')) return route.fulfill({ json: recommendations })
    if (path.endsWith('/document')) return route.fulfill({ status: 503, json: { detail: 'home_preview_document_unavailable' } })
    return route.fulfill({ json: { items: [], rows: [] } })
  })
  await page.goto('/')
  const home = page.getByTestId('home-preview-real')
  await expect(home.getByTestId('stored-document-error')).toContainText('불러오지 못했습니다')
  // 다시 확인 동작은 오류 상태에만 있다.
  await expect(home.getByTestId('stored-document-error').getByRole('button', { name: '다시 확인' })).toBeVisible()
  await expect(home.getByTestId('stored-document-absent')).toHaveCount(0)
  await expect(home.getByTestId('match-preview-body')).toHaveCount(0)
})

test('absent document shows one notice with no body, cards, or buttons', async ({ page }) => {
  await page.route('**/api/v1/home/**', async route => {
    const path = new URL(route.request().url()).pathname
    if (path.endsWith('/recommendations')) return route.fulfill({ json: recommendations })
    if (path.endsWith('/document')) return route.fulfill({ json: absentDocument(Number(path.split('/').at(-2))) })
    return route.fulfill({ json: { items: [], rows: [] } })
  })
  await page.goto('/')
  const home = page.getByTestId('home-preview-real')
  const absent = home.getByTestId('stored-document-absent')
  await expect(absent).toBeVisible()
  await expect(absent).toContainText('킥오프 6시간')
  // 빈 본문 카드·중복 생성 예정 설명·버튼을 붙이지 않는다.
  await expect(home.getByTestId('match-preview-body')).toHaveCount(0)
  await expect(absent.locator('button')).toHaveCount(0)
  await expect(home.getByTestId('preview-generation-time')).toHaveCount(0)
})

test('absent document inside the six hour window asks for generation instead of the default notice', async ({ page }) => {
  await page.route('**/api/v1/home/**', async route => {
    const path = new URL(route.request().url()).pathname
    if (path.endsWith('/recommendations')) return route.fulfill({ json: recommendations })
    if (path.endsWith('/document')) return route.fulfill({ json: absentDocument(Number(path.split('/').at(-2)), 'upcoming_overdue') })
    return route.fulfill({ json: { items: [], rows: [] } })
  })
  await page.goto('/')
  const absent = page.getByTestId('home-preview-real').getByTestId('stored-document-absent')
  await expect(absent).toContainText('아직 생성되지 않았습니다')
  // 실제 실패 근거가 없으므로 생성 실패로 단정하지 않는다.
  await expect(absent).not.toContainText('실패했습니다')
})

for (const viewport of [{ width: 1440, height: 1000 }, { width: 390, height: 844 }]) {
  test(`home has one scroll owner without decoration overflow: ${viewport.width}`, async ({ page }) => {
    await page.setViewportSize(viewport)
    await stubImages(page)
    const homeRequests: string[] = []
    await page.route('**/api/v1/home/**', async route => {
      const path = new URL(route.request().url()).pathname
      homeRequests.push(path)
      if (path.endsWith('/recommendations')) return route.fulfill({ json: recommendations })
      if (path.endsWith('/document')) return route.fulfill({ json: document(Number(path.split('/').at(-2))) })
      return route.fulfill({ json: { items: [], rows: [] } })
    })
    await page.goto('/')
    const home = page.getByTestId('home-preview-real')
    await expect(home.getByTestId('match-preview-body')).toBeVisible()
    await expect(page.locator('main')).toHaveCount(1)
    const metrics = await page.getByTestId('ui-review-home-page').evaluate(root => {
      const section = root.querySelector<HTMLElement>('.hp-live-section')!
      const stage = root.querySelector<HTMLElement>('.hp-preview-stage')!
      const backdrop = root.querySelector<HTMLElement>('.hp-preview-backdrop')!
      const box = root.getBoundingClientRect()
      const scrollOwners = [root, ...root.querySelectorAll<HTMLElement>('*')].filter(el => el.clientHeight > 0 && el.scrollHeight > el.clientHeight + 1 && ['auto', 'scroll'].includes(getComputedStyle(el).overflowY))
      return { bottom: box.bottom, viewportHeight: innerHeight, scrollOwners: scrollOwners.map(el => el === root ? 'home' : el.className), scrollbar: getComputedStyle(root).scrollbarWidth,
        extraX: section.scrollWidth - section.clientWidth, extraY: section.scrollHeight - section.clientHeight,
        clip: getComputedStyle(backdrop).overflow, decorationHeight: backdrop.getBoundingClientRect().height, stageHeight: stage.getBoundingClientRect().height }
    })
    expect(metrics.bottom).toBeLessThanOrEqual(metrics.viewportHeight + 1)
    expect(metrics.scrollOwners).toEqual(['home'])
    expect(metrics.scrollbar).toBe('none')
    // 좁은 폭에서도 저장 본문이 가로로 넘치지 않는다.
    expect(metrics.extraX).toBeLessThanOrEqual(1)
    expect(metrics.extraY).toBeLessThanOrEqual(24) // reveal translation may extend the last element by 20px
    expect(metrics.clip).toBe('clip')
    expect(metrics.decorationHeight).toBeLessThanOrEqual(metrics.stageHeight)
    // 홈은 추천 목록과 저장 문서만 읽는다. 옛 prematch를 호출하지 않는다.
    expect(homeRequests.every(path => path.endsWith('/recommendations') || path.endsWith('/document'))).toBe(true)
    expect(homeRequests.some(path => path.endsWith('/prematch'))).toBe(false)
    const owner = page.getByTestId('ui-review-home-page')
    await owner.focus()
    await page.keyboard.press('PageDown')
    await expect.poll(() => owner.evaluate(el => el.scrollTop)).toBeGreaterThan(0)
    await home.getByTestId('preview-detail-link').scrollIntoViewIfNeeded()
    await expect(home.getByTestId('preview-detail-link')).toBeVisible()
    await page.screenshot({ path: `../out/home-preview/scroll-diagnosis/fixed-${viewport.width}.png` })
  })
}

for (const viewport of [{ width: 1440, height: 1000 }, { width: 390, height: 844 }]) {
  test(`empty home has no unnecessary scrolling: ${viewport.width}`, async ({ page }) => {
    await page.setViewportSize(viewport)
    await page.route('**/api/v1/home/recommendations', route => route.fulfill({ json: {
      ...recommendations, display_date: recommendations.requested_date, fallback_reason: null, items: [], today_results: [],
    } }))
    await page.goto('/')
    await expect(page.getByRole('heading', { name: '아직 추천할 경기가 없습니다', exact: true })).toBeVisible()
    const metrics = await page.getByTestId('ui-review-home-page').evaluate(el => ({ extraY: el.scrollHeight - el.clientHeight, extraX: el.scrollWidth - el.clientWidth }))
    expect(metrics.extraY).toBe(0)
    expect(metrics.extraX).toBe(0)
  })
}

for (const role of ['public', 'USER', 'STREAMER', 'ADMIN'] as const) {
  test(`home and match detail share broadcast permission: ${role}`, async ({ page }) => {
    // Cached ADMIN values must not replace the user returned by the session endpoint.
    const user = { id: 1, email: 'viewer@example.test', role, nickname: 'Viewer', is_active: true }
    await page.addInitScript(({ authenticated }) => {
      localStorage.setItem('mockRole', 'ADMIN')
      if (authenticated) localStorage.setItem('authUser', JSON.stringify({ role: 'ADMIN' }))
    }, { authenticated: role !== 'public' })
    await page.route('**/api/v1/auth/**', route => route.fulfill({ json: { user, access_token: 'fixture-session' } }))
    await stubImages(page)
    await page.route('**/api/v1/home/**', async route => {
      const path = new URL(route.request().url()).pathname
      if (path.endsWith('/recommendations')) return route.fulfill({ json: recommendations })
      if (path.endsWith('/document')) return route.fulfill({ json: document(Number(path.split('/').at(-2))) })
      return route.fulfill({ json: { items: [], rows: [] } })
    })
    const detail = JSON.parse(readFileSync(new URL('../src/mocks/data/fixture-detail/match.1000001.json', import.meta.url), 'utf8'))
    await page.route('**/api/v1/fixtures/**', route => {
      const path = new URL(route.request().url()).pathname
      return /\/fixtures\/\d+$/.test(path) ? route.fulfill({ json: detail }) : route.fulfill({ status: 503, json: { detail: 'Fixture subsection unavailable' } })
    })
    await page.goto('/')
    if (role !== 'public') await expect(page.getByRole('button', { name: '로그아웃', exact: true })).toBeVisible()
    await expect(page.getByTestId('home-preview-real').getByTestId('match-preview-body')).toBeVisible()
    const trigger = page.getByTestId('broadcast-picker-trigger')
    await expect(trigger).toHaveCount(role === 'ADMIN' ? 1 : 0)
    if (role === 'ADMIN') {
      for (const size of [{ width: 1440, height: 1000 }, { width: 390, height: 844 }]) {
        await page.setViewportSize(size)
        const left = await trigger.boundingBox(), right = await page.getByRole('link', { name: '전체 경기', exact: true }).boundingBox()
        expect(left!.x + left!.width).toBeLessThanOrEqual(right!.x)
        await trigger.click()
        const picker = page.getByRole('dialog', { name: '방송 화면 선택' })
        await expect(picker).toBeVisible()
        await expect(picker.getByTestId('program-link')).toHaveAttribute('href', '/broadcast-program.html?fixtureId=90002&league=premier-league')
        await expect(picker.getByTestId('watch-together-link')).toHaveAttribute('href', '/broadcast.html?fixtureId=90002&league=premier-league')
        await expect(picker.getByTestId('program-link')).toHaveAttribute('target', '_blank')
        const box = await picker.boundingBox()
        expect(box!.x).toBeGreaterThanOrEqual(0)
        expect(box!.x + box!.width).toBeLessThanOrEqual(size.width)
        await page.keyboard.press('Escape')
        await expect(picker).not.toBeVisible()
        await expect(trigger).toBeFocused()
      }
      await page.getByRole('button', { name: '다음 추천 경기', exact: true }).click()
      await trigger.click()
      await expect(page.getByTestId('program-link')).toHaveAttribute('href', '/broadcast-program.html?fixtureId=90001&league=premier-league')
      await page.getByTestId('broadcast-picker-close').click()
    }
    await page.goto('/fixtures/1000001')
    await expect(page.getByTestId('ui-review-fixture-preview-page').locator('.match-hero')).toBeVisible()
    if (role !== 'public') await expect(page.getByRole('button', { name: '로그아웃', exact: true })).toBeVisible()
    await expect(trigger).toHaveCount(role === 'ADMIN' ? 1 : 0)
    if (role === 'ADMIN') {
      await trigger.click()
      await expect(page.getByRole('dialog', { name: '방송 화면 선택' })).toBeVisible()
      await expect(page.getByTestId('program-link')).toHaveAttribute('href', '/broadcast-program.html?fixtureId=1000001&league=premier-league')
    }
  })
}
