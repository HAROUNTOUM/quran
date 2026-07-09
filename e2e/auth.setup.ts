import { test as setup, expect } from '@playwright/test'
import { existsSync, mkdirSync, writeFileSync } from 'fs'

const AUTH_DIR = 'e2e/.auth'
const AUTH_FILE = `${AUTH_DIR}/admin.json`

setup('authenticate as admin', async ({ page }) => {
  if (!existsSync(AUTH_DIR)) {
    mkdirSync(AUTH_DIR, { recursive: true })
  }

  const email = process.env.ECC_ADMIN_EMAIL
  const password = process.env.ECC_ADMIN_PASSWORD

  if (!email || !password) {
    writeFileSync(AUTH_FILE, JSON.stringify({ cookies: [], origins: [] }), 'utf-8')
    console.warn('⚠  ECC_ADMIN_EMAIL and ECC_ADMIN_PASSWORD not set — empty auth state created')
    return
  }

  await page.goto('/login/')
  await page.locator('#id_email').fill(email)
  await page.locator('#id_password').fill(password)
  await page.locator('button[type="submit"]').click()
  await page.waitForURL(/\/dashboard\//)
  await expect(page.locator('#sidebar')).toBeVisible()
  await page.context().storageState({ path: AUTH_FILE })
})
