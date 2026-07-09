import { test, expect } from '@playwright/test'

test.describe('Admin Email Center', () => {
  test('email campaigns list loads', async ({ page }) => {
    const resp = await page.goto('/dashboard/email/')
    expect(resp?.status()).toBeLessThan(500)
  })

  test('email compose loads', async ({ page }) => {
    const resp = await page.goto('/dashboard/email/compose/')
    expect(resp?.status()).toBeLessThan(500)
  })

  test('email log loads', async ({ page }) => {
    const resp = await page.goto('/dashboard/email/log/')
    expect(resp?.status()).toBeLessThan(500)
  })

  test('automail controls loads', async ({ page }) => {
    const resp = await page.goto('/dashboard/email/controls/')
    expect(resp?.status()).toBeLessThan(500)
  })
})
