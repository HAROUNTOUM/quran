import { test, expect } from '@playwright/test'

test.describe('Admin Circles & Academics', () => {
  test('circles list loads', async ({ page }) => {
    const resp = await page.goto('/dashboard/circles/')
    expect(resp?.status()).toBeLessThan(500)
  })

  test('circle create page loads', async ({ page }) => {
    const resp = await page.goto('/dashboard/circles/create/')
    expect(resp?.status()).toBeLessThan(500)
  })

  test('inscriptions list loads', async ({ page }) => {
    const resp = await page.goto('/dashboard/inscriptions/')
    expect(resp?.status()).toBeLessThan(500)
  })

  test('exams list loads', async ({ page }) => {
    const resp = await page.goto('/dashboard/exams/')
    expect(resp?.status()).toBeLessThan(500)
  })

  test('exam create page loads', async ({ page }) => {
    const resp = await page.goto('/dashboard/exams/create/')
    expect(resp?.status()).toBeLessThan(500)
  })

  test('absences list loads', async ({ page }) => {
    const resp = await page.goto('/dashboard/absences/')
    expect(resp?.status()).toBeLessThan(500)
  })

  test('active substitutions loads', async ({ page }) => {
    const resp = await page.goto('/dashboard/absences/active/')
    expect(resp?.status()).toBeLessThan(500)
  })

  test('classrooms loads', async ({ page }) => {
    const resp = await page.goto('/dashboard/classrooms/')
    expect(resp?.status()).toBeLessThan(500)
  })
})
