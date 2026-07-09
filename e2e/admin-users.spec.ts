import { test, expect } from '@playwright/test'

test.describe('Admin User Management', () => {
  test('students list loads', async ({ page }) => {
    const resp = await page.goto('/dashboard/students/')
    expect(resp?.status()).toBeLessThan(500)
  })

  test('student create page loads', async ({ page }) => {
    const resp = await page.goto('/dashboard/students/create/')
    expect(resp?.status()).toBeLessThan(500)
  })

  test('teachers list loads', async ({ page }) => {
    const resp = await page.goto('/dashboard/teachers/')
    expect(resp?.status()).toBeLessThan(500)
  })

  test('teacher create page loads', async ({ page }) => {
    const resp = await page.goto('/dashboard/teachers/create/')
    expect(resp?.status()).toBeLessThan(500)
  })

  test('supervisors list loads', async ({ page }) => {
    const resp = await page.goto('/dashboard/supervisors/')
    expect(resp?.status()).toBeLessThan(500)
  })

  test('supervisor create page loads', async ({ page }) => {
    const resp = await page.goto('/dashboard/supervisors/create/')
    expect(resp?.status()).toBeLessThan(500)
  })

  test('pending users table loads', async ({ page }) => {
    const resp = await page.goto('/dashboard/users/table/')
    expect(resp?.status()).toBeLessThan(500)
  })

  test('supervisor groups loads', async ({ page }) => {
    const resp = await page.goto('/dashboard/supervisor/groups/')
    expect(resp?.status()).toBeLessThan(500)
  })
})
