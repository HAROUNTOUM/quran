import { test, expect } from '@playwright/test'

test.describe('Admin Communication', () => {
  test('announcements list loads', async ({ page }) => {
    const resp = await page.goto('/dashboard/announcements/')
    expect(resp?.status()).toBeLessThan(500)
  })

  test('announcement create page loads', async ({ page }) => {
    const resp = await page.goto('/dashboard/announcements/create/')
    expect(resp?.status()).toBeLessThan(500)
  })

  test('requests list loads', async ({ page }) => {
    const resp = await page.goto('/dashboard/requests/')
    expect(resp?.status()).toBeLessThan(500)
  })

  test('notifications list loads', async ({ page }) => {
    const resp = await page.goto('/dashboard/notifications/')
    expect(resp?.status()).toBeLessThan(500)
  })

  test('admin notifications loads', async ({ page }) => {
    const resp = await page.goto('/dashboard/admin/notifications/')
    expect(resp?.status()).toBeLessThan(500)
  })

  test('admin notification create loads', async ({ page }) => {
    const resp = await page.goto('/dashboard/admin/notifications/create/')
    expect(resp?.status()).toBeLessThan(500)
  })

  test('messages inbox loads', async ({ page }) => {
    const resp = await page.goto('/dashboard/messages/')
    expect(resp?.status()).toBeLessThan(500)
  })

  test('private sessions loads', async ({ page }) => {
    const resp = await page.goto('/dashboard/admin/private-sessions/')
    expect(resp?.status()).toBeLessThan(500)
  })

  test('webinars list loads', async ({ page }) => {
    const resp = await page.goto('/dashboard/webinars/')
    expect(resp?.status()).toBeLessThan(500)
  })

  test('webinar manage list loads', async ({ page }) => {
    const resp = await page.goto('/dashboard/webinars/manage/')
    expect(resp?.status()).toBeLessThan(500)
  })

  test('webinar create loads', async ({ page }) => {
    const resp = await page.goto('/dashboard/webinars/manage/create/')
    expect(resp?.status()).toBeLessThan(500)
  })
})
