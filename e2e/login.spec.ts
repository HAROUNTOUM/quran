import { test, expect } from '@playwright/test'

const isAuthenticatedRun = Boolean(process.env.ECC_ADMIN_EMAIL && process.env.ECC_ADMIN_PASSWORD)

test.describe('Authentication', () => {
  test('shows login page', async ({ page }) => {
    await page.goto('/login/')
    if (isAuthenticatedRun) {
      await expect(page).toHaveURL(/\/dashboard/)
    } else {
      await expect(page.locator('#id_email')).toBeVisible()
      await expect(page.locator('#id_password')).toBeVisible()
    }
  })

  test('fails with invalid credentials', async ({ page, context }) => {
    test.skip(isAuthenticatedRun, 'already authenticated — cannot test invalid login flow')
    await page.goto('/login/')
    await page.locator('#id_email').fill('wrong@test.com')
    await page.locator('#id_password').fill('wrongpassword')
    await page.locator('button[type="submit"]').click()
    await expect(page.locator('.text-red-500, .text-red-700, [class*="error"]').first()).toBeVisible()
  })

  test('authenticated users reach dashboard', async ({ page }) => {
    test.skip(!isAuthenticatedRun, 'requires authenticated session')
    await page.goto('/dashboard/')
    await expect(page).toHaveURL(/\/dashboard/)
    await expect(page.locator('#sidebar')).toBeVisible()
  })
})
