import { test, expect } from '@playwright/test'

test.describe('Admin Overview', () => {
  test('dashboard home loads', async ({ page }) => {
    const resp = await page.goto('/dashboard/')
    expect(resp?.status()).toBeLessThan(500)
  })

  test('admin dashboard loads', async ({ page }) => {
    const resp = await page.goto('/dashboard/admin/')
    expect(resp?.status()).toBeLessThan(500)
  })

  test('profile page loads', async ({ page }) => {
    const resp = await page.goto('/dashboard/profile/')
    expect(resp?.status()).toBeLessThan(500)
  })

  test('profile edit page loads', async ({ page }) => {
    const resp = await page.goto('/dashboard/profile/edit/')
    expect(resp?.status()).toBeLessThan(500)
  })

  test('settings page loads', async ({ page }) => {
    const resp = await page.goto('/dashboard/settings/')
    expect(resp?.status()).toBeLessThan(500)
  })
})
