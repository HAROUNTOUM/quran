import { test, expect } from '@playwright/test'

test.describe('Dashboard (public routes)', () => {
  test('landing page loads', async ({ page }) => {
    await page.goto('/')
    await expect(page).toHaveTitle(/حافظ|quran|hafez/i)
  })
})
