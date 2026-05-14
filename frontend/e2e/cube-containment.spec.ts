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
    expect(data.cubeRight - data.leftCubeRight).toBeLessThanOrEqual(1)
  })

  test(`face 가 1:1 로 렌더 (perspective scale 보정) @ ${v.name}`, async ({
    page,
  }) => {
    await page.setViewportSize({ width: v.w, height: v.h })
    await page.goto('/')
    await page.waitForSelector('[data-testid="cube"]', { state: 'visible' })
    const m = await page.evaluate(() => {
      const cube = document.querySelector(
        '[data-testid="cube"]',
      ) as HTMLElement
      const face = document.querySelector(
        '[data-testid="cube-face-0"]',
      ) as HTMLElement
      const cubeBox = cube.getBoundingClientRect()
      const faceBox = face.getBoundingClientRect()
      return {
        cubeW: Math.round(cubeBox.width),
        cubeH: Math.round(cubeBox.height),
        faceW: Math.round(faceBox.width),
        faceH: Math.round(faceBox.height),
      }
    })
    // scale 보정 후 face 의 시각 크기 = cube 크기 (±1px 반올림)
    expect(Math.abs(m.faceW - m.cubeW)).toBeLessThanOrEqual(1)
    expect(Math.abs(m.faceH - m.cubeH)).toBeLessThanOrEqual(1)
  })

  test(`faceZ = cube_width/2 (큐브 모서리 일치) @ ${v.name}`, async ({ page }) => {
    await page.setViewportSize({ width: v.w, height: v.h })
    await page.goto('/')
    await page.waitForSelector('[data-testid="cube"]', { state: 'visible' })
    const m = await page.evaluate(() => {
      const stage = document.querySelector('.cube-stage') as HTMLElement
      const cube = document.querySelector(
        '[data-testid="cube"]',
      ) as HTMLElement
      const styleVal = getComputedStyle(stage).getPropertyValue('--face-z').trim()
      const faceZ = parseFloat(styleVal)
      const cubeW = cube.getBoundingClientRect().width
      return { faceZ, cubeW }
    })
    // 큐브 4면이 모서리에서 만나려면 faceZ = cube_width/2. ±2px tolerance.
    expect(Math.abs(m.faceZ - m.cubeW / 2)).toBeLessThanOrEqual(2)
  })
}
