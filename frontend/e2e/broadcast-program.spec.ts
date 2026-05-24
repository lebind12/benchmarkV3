import { expect, test } from '@playwright/test'

function closeTo(actual: number, expected: number, tolerance = 2) {
  expect(Math.abs(actual - expected)).toBeLessThanOrEqual(tolerance)
}

test.describe('broadcast match program (mock)', () => {
  test('BMP-E-01 renders 1920x1080 78/22 program layout', async ({ page }) => {
    await page.setViewportSize({ width: 1920, height: 1080 })
    await page.goto('/broadcast-program.html?fixture=260506')

    await expect(page.getByTestId('program-stage')).toHaveAttribute(
      'data-league',
      'world-cup-2026',
    )
    await expect(page.getByTestId('program-bottom-carousel')).toBeVisible()
    await expect(page.getByTestId('program-bottom-carousel')).toHaveAttribute(
      'data-carousel-interval-ms',
      '7000',
    )
    await expect(page.getByTestId('program-bottom-carousel')).toHaveAttribute(
      'data-event-insert-index',
      '1',
    )
    await expect(page.getByTestId('program-chat-slot')).toBeVisible()
    await expect(page.getByTestId('program-character-slot')).toBeVisible()
    await expect(page.getByTestId('program-scorebug')).toHaveCount(0)
    await expect(page.getByTestId('program-lower-third')).toHaveCount(0)
    await expect(page.getByTestId('program-info-card-clone')).toHaveCount(1)

    const stage = await page.getByTestId('program-stage').boundingBox()
    const left = await page.getByTestId('program-left').boundingBox()
    const right = await page.getByTestId('program-right').boundingBox()
    const feed = await page.getByTestId('program-feed-surface').boundingBox()
    const bottom = await page.getByTestId('program-bottom-carousel').boundingBox()
    const chat = await page.getByTestId('program-chat-slot').boundingBox()
    const character = await page.getByTestId('program-character-slot').boundingBox()

    expect(stage).not.toBeNull()
    expect(left).not.toBeNull()
    expect(right).not.toBeNull()
    expect(feed).not.toBeNull()
    expect(bottom).not.toBeNull()
    expect(chat).not.toBeNull()
    expect(character).not.toBeNull()

    closeTo(left!.width, 1920 * 0.78)
    closeTo(right!.width, 1920 * 0.22)
    closeTo(feed!.height, 1080 * 0.78)
    closeTo(bottom!.height, 1080 * 0.22)
    closeTo(chat!.height, 1080 * 0.78)
    closeTo(character!.height, 1080 * 0.22)
    closeTo(feed!.width / feed!.height, 16 / 9, 0.02)

    const chatBackground = await page
      .getByTestId('program-chat-slot')
      .evaluate((node) => getComputedStyle(node).backgroundColor)
    const characterBackground = await page
      .getByTestId('program-character-slot')
      .evaluate((node) => getComputedStyle(node).backgroundColor)
    expect(chatBackground).toBe('rgb(0, 177, 64)')
    expect(characterBackground).toBe('rgb(0, 177, 64)')

    const cardIds = await page
      .getByTestId('program-info-card')
      .evaluateAll((nodes) => nodes.map((node) => node.getAttribute('data-card-id')))
    expect(cardIds).toEqual([
      'worldcup-banner',
      'offside',
      'foul',
      'booking',
      'equalizer',
      'possession',
      'shots',
      'player',
      'tactic',
    ])

    const eventTypes = await page
      .getByTestId('program-info-card')
      .evaluateAll((nodes) =>
        nodes
          .map((node) => node.getAttribute('data-event-type'))
          .filter((eventType): eventType is string => eventType !== null),
      )
    expect(eventTypes).toEqual(['offside', 'foul', 'card', 'goal'])
  })

  test('BMP-E-02 fixture route bridges to broadcast program entry', async ({ page }) => {
    await page.goto('/broadcast/program/fixtures/1000001?league=champions-league')
    await page.waitForURL('**/broadcast-program.html?fixture=1000001&league=champions-league')

    await expect(page.getByTestId('program-stage')).toHaveAttribute(
      'data-league',
      'champions-league',
    )
    await expect(page.getByTestId('program-bottom-carousel')).toContainText('PSG')
  })
})
