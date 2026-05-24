import { expect, test } from '@playwright/test'

test.describe('broadcast formation design lab', () => {
  test('renders the selected formation identity matrix', async ({ page }) => {
    await page.setViewportSize({ width: 1920, height: 1080 })
    await page.goto('/broadcast-formation-lab.html')

    await expect(page.getByTestId('formation-lab-page')).toBeVisible()
    await expect(page.getByTestId('identity-layer-guide').locator('article')).toHaveCount(6)
    await expect(page.getByTestId('formation-matrix-row')).toHaveCount(7)
    await expect(page.getByTestId('formation-matrix-cell')).toHaveCount(42)
    await expect(page.getByTestId('dual-board-section')).toBeVisible()
    await expect(page.getByTestId('dual-board-tile')).toHaveCount(6)

    const formations = await page
      .getByTestId('formation-matrix-row')
      .evaluateAll((nodes) => nodes.map((node) => node.getAttribute('data-formation')))
    expect(new Set(formations).size).toBe(7)

    const layers = await page
      .getByTestId('formation-matrix-cell')
      .evaluateAll((nodes) => nodes.map((node) => node.getAttribute('data-layer')))
    expect(new Set(layers).size).toBe(6)
    await expect(
      page
        .getByTestId('formation-matrix-cell')
        .filter({ has: page.getByText('채택') }),
    ).toHaveAttribute('data-selected', 'true')

    const dualBoards = await page
      .getByTestId('dual-board-tile')
      .evaluateAll((nodes) => nodes.map((node) => node.getAttribute('data-board')))
    expect(new Set(dualBoards).size).toBe(6)

    const matrix = page.getByTestId('formation-identity-matrix')
    await expect(matrix.getByText('Classic Pitch')).toBeVisible()
    await expect(matrix.getByText('Tactical Board')).toBeVisible()
    await expect(matrix.getByText('Zone Grid')).toBeVisible()
    await expect(matrix.getByText('Half-Space Map')).toBeVisible()
    await expect(matrix.getByText('Radar Rings')).toBeVisible()
    await expect(matrix.getByText('Stadium Perspective')).toBeVisible()
    await expect(matrix.getByText('Compact Pitch')).toBeVisible()
    const layerGuide = page.getByTestId('identity-layer-guide')
    await expect(layerGuide.getByText('L1. Top Ribbon')).toBeVisible()
    await expect(layerGuide.getByText('L2. Crest Tab')).toBeVisible()
    await expect(layerGuide.getByText('L3. Side Rail')).toBeVisible()
    await expect(layerGuide.getByText('L4. Corner Motif')).toBeVisible()
    await expect(layerGuide.getByText('L5. Tournament Plate')).toBeVisible()
    await expect(layerGuide.getByText('L6. Pattern Band')).toBeVisible()
    await expect(page.getByText('Mirror Lineups')).toBeVisible()
    await expect(page.getByText('Phase Split Board')).toBeVisible()
    await expect(page.getByText('Matchup Channels')).toBeVisible()
    await expect(page.getByText('Overload Map')).toBeVisible()
    await expect(page.getByText('Compact Dual Board')).toBeVisible()
    await expect(page.getByText('Camera Dual View')).toBeVisible()
    await expect(page.getByText('League Ribbon Pitch')).toHaveCount(0)
    await expect(page.getByText('Crest Frame Pitch')).toHaveCount(0)
    await expect(page.getByText('Tournament Frame Pitch')).toHaveCount(0)
    await expect(page.getByText('Press Map')).toHaveCount(0)
    await expect(page.getByText('Run Arrows')).toHaveCount(0)
    await expect(page.getByText('Set Piece Board')).toHaveCount(0)
    await expect(page.getByText('Jersey Grid')).toHaveCount(0)
    await expect(page.getByText('Lineup Tape')).toHaveCount(0)
  })
})
