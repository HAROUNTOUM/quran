import { test, expect } from '@playwright/test'

test.describe('Signup wizard', () => {
  test('full journey shows success feedback', async ({ page }) => {
    const email = `e2e-signup-${Date.now()}@test.local`
    await page.goto('/signup/')
    await page.fill('#id_full_name_ar', 'طالب تجريبي آلي')
    await page.selectOption('#id_gender', 'male')
    await page.fill('#id_email', email)
    await page.fill('#id_phone', '0555000111')
    await page.selectOption('#id_state', 'قسنطينة')
    await page.click('text=التالي')
    await page.selectOption('#id_specialization', 'طب عام')
    await page.selectOption('#id_level', 'مبتدئ')
    await page.selectOption('#id_memorization_amount', { index: 1 })
    await page.locator('.auth-fields:visible button:has-text("التالي")').click()
    await page.fill('#id_password1', 'Test-Pass-2026!')
    await page.fill('#id_password2', 'Test-Pass-2026!')
    // clicking without the pledge must give visible feedback, not a dead button
    await page.locator('button:has-text("سجل")').click()
    await expect(page.locator('#signup-form-container')).toContainText('يجب الموافقة على التعهد')
    await page.locator('input[type="checkbox"]').check()
    await page.locator('button:has-text("سجل")').click()
    // the signup response must come back promptly with visible feedback
    await expect(page.locator('#signup-form-container')).toContainText('تم بنجاح', { timeout: 15000 })
  })
})
