import { test, expect } from '@playwright/test'

test.describe('Admin Reports', () => {
  test('reports page loads', async ({ page }) => {
    const resp = await page.goto('/dashboard/reports/')
    expect(resp?.status()).toBeLessThan(500)
  })

  test('exam results report loads', async ({ page }) => {
    const resp = await page.goto('/dashboard/reports/exam-results/')
    expect(resp?.status()).toBeLessThan(500)
  })

  test('progress page loads', async ({ page }) => {
    const resp = await page.goto('/dashboard/progress/')
    expect(resp?.status()).toBeLessThan(500)
  })
})
