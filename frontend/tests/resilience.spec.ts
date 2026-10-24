import { expect, test } from '@playwright/test'
import path from 'node:path'
import {
  checkGeneratedCustomerFit,
  generatedFixtures,
  modelA,
  modelL,
  uploadGeneratedModels,
} from './support/resilience'

test('API fixture workbooks reach both audience views through the real API', async ({ page }) => {
  const directory = path.resolve(import.meta.dirname, 'fixtures/generated')
  await page.goto('/')
  await page
    .getByLabel('Choose Excel workbooks')
    .setInputFiles([
      path.join(directory, 'Model A profile 1.xlsx'),
      path.join(directory, 'Model L profile 1.xlsx'),
    ])
  const comparison = page.getByRole('table', { name: 'Customer model comparison' })
  await expect(
    comparison.getByRole('row', { name: 'Model A 1,000 40 100', exact: true }),
  ).toBeVisible()
  await expect(
    comparison.getByRole('row', { name: 'Model L 1,500 60 150', exact: true }),
  ).toBeVisible()
  await page.getByLabel('Inspect one sweep and test customer targets').selectOption('1')
  await page.getByLabel('Projected workload').selectOption({ index: 1 })
  await page.getByLabel('Minimum total capacity').fill('2000')
  await page.getByLabel('Minimum response speed').fill('50')
  await page.getByLabel('Maximum time until response starts').fill('250')
  await page.getByRole('button', { name: 'Check customer fit' }).click()
  const decisions = page.getByRole('table', { name: 'Customer decision comparison' })
  await expect(decisions.getByRole('row', { name: /Model A NO GO/ })).toBeVisible()
  await expect(decisions.getByRole('row', { name: /Model L GO Batch 2/ })).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Go for this projected workload' })).toBeVisible()
  await page.getByLabel('Engineering sweep').selectOption('1')
  await page
    .getByRole('table', { name: 'Engineering configurations' })
    .getByRole('button', { name: 'Row 2', exact: true })
    .click()
  const detail = page.locator('#engineering-detail')
  await expect(detail.getByRole('heading')).toHaveText('Model L · Profile 1 · normalized row 2')
  await expect(
    detail
      .locator('dl > div')
      .filter({ has: page.getByText('Aggregate throughput', { exact: true }) }),
  ).toContainText('2,700 t/s')
  await expect(
    detail
      .locator('dl > div')
      .filter({ has: page.getByText('Per-box throughput', { exact: true }) }),
  ).toContainText('675 t/s/hardware')
})

test('fresh Model L drives comparison, customer evidence and engineering inspection', async ({
  page,
}) => {
  await uploadGeneratedModels(page)
  const table = page.getByRole('table', { name: 'Customer model comparison' })
  await expect(
    table.getByRole('row', { name: 'Model A 260 1,350 12.5', exact: true }),
  ).toBeVisible()
  await expect(table.getByRole('row', { name: 'Model L 520 2,700 6.3', exact: true })).toBeVisible()
  await page.getByLabel('Projected configuration').selectOption('1')
  await expect(
    table.getByRole('row', { name: 'Model L 800 2,440 12.5', exact: true }),
  ).toBeVisible()
  await checkGeneratedCustomerFit(page)
  await expect(page.getByLabel('Assumptions and limitations')).toContainText('projections')
  await page.getByRole('link', { name: 'Engineering inspection' }).click()
  await page.getByLabel('Engineering sweep').selectOption('1')
  const engineering = page.getByRole('table', { name: 'Engineering configurations' })
  await expect(engineering.getByRole('row')).toHaveCount(3)
  await engineering.getByRole('button', { name: 'Row 2', exact: true }).click()
  const detail = page.locator('#engineering-detail')
  await expect(detail.getByRole('heading')).toHaveText('Model L · Profile 1 · normalized row 2')
  await expect(
    detail
      .locator('dl > div')
      .filter({ has: page.getByText('Aggregate throughput', { exact: true }) }),
  ).toContainText('800 t/s')
  await expect(
    detail
      .locator('dl > div')
      .filter({ has: page.getByText('Per-box throughput', { exact: true }) }),
  ).toContainText('80 t/s/hardware')
  await expect(page.getByLabel('Engineering trends')).toContainText('Batch size 10 to 20')
})

for (const [filename, message] of [
  ['missing-column.xlsx', 'Batch Size'],
  ['invalid-number.xlsx', 'Row 3'],
  ['empty-table.xlsx', 'no performance data rows'],
  ['corrupt.xlsx', 'Invalid Excel workbook'],
]) {
  test(`recovers after ${filename} without reloading or keeping stale data`, async ({ page }) => {
    await page.goto('/')
    await page.getByLabel('Choose Excel workbooks').setInputFiles(modelA)
    await expect(page.getByRole('heading', { name: 'Model A', exact: true })).toBeVisible()
    await page
      .getByLabel('Choose Excel workbooks')
      .setInputFiles(path.join(generatedFixtures, filename))
    await expect(page.getByRole('alert')).toContainText(filename)
    await expect(page.getByRole('alert')).toContainText(message)
    await expect(page.getByRole('heading', { name: 'Model A', exact: true })).toHaveCount(0)
    await expect(page.getByRole('table', { name: 'Customer model comparison' })).toHaveCount(0)
    await expect(page.getByRole('button', { name: 'Load sample workbook' })).toBeEnabled()
    await page.getByLabel('Choose Excel workbooks').setInputFiles(modelL)
    await expect(page.getByRole('heading', { name: 'Model L', exact: true })).toBeVisible()
    await expect(page.getByRole('alert')).toHaveCount(0)
    await expect(
      page
        .getByRole('table', { name: 'Customer model comparison' })
        .getByRole('row', { name: /Model L 520/ }),
    ).toBeVisible()
  })
}

test('a mixed batch keeps valid Model L and names the rejected workbook', async ({ page }) => {
  await page.goto('/')
  await page
    .getByLabel('Choose Excel workbooks')
    .setInputFiles([modelL, path.join(generatedFixtures, 'missing-column.xlsx')])
  await expect(page.getByRole('heading', { name: 'Model L', exact: true })).toBeVisible()
  const diagnostics = page.getByRole('region', { name: 'Upload diagnostics' })
  await expect(diagnostics).toContainText('missing-column.xlsx')
  await expect(diagnostics).toContainText('Batch Size')
  await expect(
    page
      .getByRole('table', { name: 'Customer model comparison' })
      .getByRole('row', { name: /Model L 520/ }),
  ).toBeVisible()
  await expect(page.getByRole('alert')).toHaveCount(0)
})

test('an upload connection failure allows another attempt', async ({ page }) => {
  await page.route('**/api/v1/comparisons/workbooks', (route) => route.abort('connectionfailed'), {
    times: 1,
  })
  await page.goto('/')
  await page.getByLabel('Choose Excel workbooks').setInputFiles(modelL)
  await expect(page.getByRole('alert')).toContainText('Could not reach the comparison API')
  await expect(page.getByLabel('Choose Excel workbooks')).toBeEnabled()
  await page.getByLabel('Choose Excel workbooks').setInputFiles(modelL)
  await expect(page.getByRole('heading', { name: 'Model L', exact: true })).toBeVisible()
  await expect(page.getByRole('alert')).toHaveCount(0)
})

for (const width of [390, 640]) {
  test(`all audience tables and controls remain usable at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 844 })
    await uploadGeneratedModels(page)
    await checkGeneratedCustomerFit(page)
    await page.getByLabel('Engineering sweep').selectOption('1')
    await expect(
      page
        .getByRole('table', { name: 'Engineering configurations' })
        .getByRole('button', { name: 'Row 2', exact: true }),
    ).toBeEnabled()
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(
      width,
    )
    for (const name of [
      'Customer model comparison',
      'Engineering model comparison',
      'Customer decision comparison',
      'Engineering configurations',
      'Normalized configurations',
    ]) {
      const region = page.getByRole('region', { name: `${name} scroll area` })
      await expect(region).toHaveAttribute('tabindex', '0')
      await region.focus()
      await expect(region).toBeFocused()
      await page.keyboard.press('ArrowRight')
      await expect.poll(() => region.evaluate((element) => element.scrollLeft)).toBeGreaterThan(0)
      const bounds = await region.boundingBox()
      expect(bounds?.width).toBeLessThanOrEqual(width)
    }
  })
}

test('keyboard tab order reaches upload controls with visible focus', async ({ page }) => {
  await page.goto('/')
  await page.keyboard.press('Tab')
  await expect(page.getByRole('link', { name: 'Performance Studio home' })).toBeFocused()
  await page.keyboard.press('Tab')
  await expect(page.getByLabel('Choose Excel workbooks')).toBeFocused()
  await expect(page.locator('.file-picker')).toHaveCSS('outline-style', 'solid')
  await page.keyboard.press('Tab')
  await expect(page.getByRole('button', { name: 'Load sample workbook' })).toBeFocused()
  await page.keyboard.press('Shift+Tab')
  await expect(page.getByLabel('Choose Excel workbooks')).toBeFocused()
  await page.keyboard.press('Tab')
  await page.keyboard.press('Enter')
  await expect(page.getByRole('heading', { name: 'Model A', exact: true })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Load sample workbook' })).toBeFocused()
  await page.keyboard.press('Tab')
  await expect(page.getByRole('link', { name: 'Customer decision', exact: true })).toBeFocused()
  await page.keyboard.press('Tab')
  await expect(
    page.getByRole('link', { name: 'Engineering inspection', exact: true }),
  ).toBeFocused()
  await page.keyboard.press('Enter')
  await expect(page.getByRole('heading', { name: 'Inspect the projection' })).toBeInViewport()
})

test('engineering shortcut works while diagnostics are loading', async ({ page }) => {
  let releaseRequest!: () => void
  const pending = new Promise<void>((resolve) => {
    releaseRequest = resolve
  })
  await page.route('**/api/v1/engineering/analyze', async (route) => {
    await pending
    await route.continue()
  })

  try {
    await page.goto('/')
    await page.getByRole('button', { name: 'Load sample workbook' }).press('Enter')
    await expect(page.getByRole('heading', { name: 'Model A', exact: true })).toBeVisible()
    const loading = page.getByRole('status', { name: 'Engineering analysis' })
    await expect(loading).toBeVisible()
    const shortcut = page.getByRole('link', { name: 'Engineering inspection', exact: true })
    await shortcut.focus()
    await shortcut.press('Enter')
    await expect(loading).toBeInViewport()
    releaseRequest()
    await expect(page.getByRole('heading', { name: 'Inspect the projection' })).toBeInViewport()
  } finally {
    releaseRequest()
  }
})

test('upload focus returns after success and failure', async ({ page }) => {
  await page.goto('/')
  const upload = page.getByLabel('Choose Excel workbooks')
  await upload.focus()
  await upload.setInputFiles(modelL)
  await expect(page.getByRole('heading', { name: 'Model L', exact: true })).toBeVisible()
  await expect(upload).toBeFocused()
  await upload.setInputFiles(path.join(generatedFixtures, 'corrupt.xlsx'))
  await expect(page.getByRole('alert')).toBeVisible()
  await expect(upload).toBeFocused()
})

test('customer submit focus returns after success and failure', async ({ page }) => {
  await uploadGeneratedModels(page)
  await page.getByLabel('Projected workload').selectOption({ index: 1 })
  await page.getByLabel('Minimum total capacity').fill('450')
  const submit = page.getByRole('button', { name: 'Check customer fit' })
  await submit.press('Enter')
  await expect(page.getByRole('table', { name: 'Customer decision comparison' })).toBeVisible()
  await expect(submit).toBeFocused()
  await page.route('**/api/v1/decisions/evaluate', (route) => route.abort('connectionfailed'))
  await submit.press('Enter')
  await expect(page.getByRole('alert')).toBeVisible()
  await expect(submit).toBeFocused()
})

test('request completion does not steal focus when the user navigates away', async ({ page }) => {
  let release!: () => void
  const pending = new Promise<void>((resolve) => {
    release = resolve
  })
  await page.route('**/api/v1/comparisons/workbooks', async (route) => {
    await pending
    await route.continue()
  })
  await page.goto('/')
  const sample = page.getByRole('button', { name: 'Load sample workbook' })
  await sample.press('Enter')
  await expect(sample).toBeDisabled()
  await page.keyboard.press('Tab')
  const home = page.getByRole('link', { name: 'Performance Studio home' })
  await expect(home).toBeFocused()
  release()
  await expect(page.getByRole('heading', { name: 'Model A', exact: true })).toBeVisible()
  await expect(home).toBeFocused()
})
