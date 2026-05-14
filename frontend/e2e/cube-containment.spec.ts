import { test, expect } from '@playwright/test'

/**
 * CubeCarousel 3D 큐브 침범 회귀.
 * - perspective + translateZ 에 의한 face 시각 확대로 인해 cube 가 LeftPanel
 *   바깥(CenterPanel 영역)을 침범하는 문제 회귀 방지.
 * - .left / .cube-stage / .cube-wrap 모두 overflow:hidden 으로 clip.
 */

const VIEWPORTS = [
  { name: '1280', w: 1280, h: 720 },
  { name: '1440', w: 1440, h: 900 },
  { name: '1920', w: 1920, h: 1080 },
] as const

for (const v of VIEWPORTS) {
  test(`cube clipping @ ${v.name} — left-cube overflow:hidden, cube right edge ≤ left-panel right`, async ({
    page,
  }) => {
    await page.setViewportSize({ width: v.w, height: v.h })
    await page.goto('/')
    await page.waitForSelector('[data-testid="cube"]', { state: 'visible' })
    const data = await page.evaluate(() => {
      const leftCube = document.querySelector(
        '[data-testid="left-cube"]',
      ) as HTMLElement
      const cube = document.querySelector(
        '[data-testid="cube"]',
      ) as HTMLElement
      const cs = getComputedStyle(leftCube)
      return {
        leftCubeOverflow: cs.overflow,
        leftCubeRight: Math.round(leftCube.getBoundingClientRect().right),
        cubeRight: Math.round(cube.getBoundingClientRect().right),
      }
    })
    expect(data.leftCubeOverflow).toBe('hidden')
    // cube 의 우측 시각 경계가 left-cube container 의 우측 경계를 넘지 않아야 함
    // (perspective 로 인한 +α 가 있더라도 clipping 되므로 ≤ 0)
    expect(data.cubeRight - data.leftCubeRight).toBeLessThanOrEqual(1)
  })
}
