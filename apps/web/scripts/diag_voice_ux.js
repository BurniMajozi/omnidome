const { chromium } = require('playwright');

(async () => {
  const browser = await chromium.launch({ headless: true, args: ['--no-sandbox', '--use-fake-ui-for-media-stream', '--use-fake-device-for-media-stream'] });
  const context = await browser.newContext({ viewport: { width: 1400, height: 1000 }, permissions: ['microphone'] });
  await context.grantPermissions(['microphone']);
  const page = await context.newPage();

  const logs = [];
  page.on('console', (msg) => logs.push(`[console:${msg.type()}] ${msg.text()}`));
  page.on('pageerror', (err) => logs.push(`[pageerror] ${err.message}`));
  page.on('requestfailed', (req) => logs.push(`[requestfailed] ${req.method()} ${req.url()} -- ${req.failure()?.errorText}`));
  page.on('response', (res) => {
    if (res.url().includes('/svc/voicebox') || res.url().includes('/svc/call-center') || res.url().includes('/api/orchestrator')) {
      logs.push(`[response] ${res.status()} ${res.url()}`);
    }
  });

  // --- Login ---
  await page.goto('http://localhost:3000/auth', { waitUntil: 'domcontentloaded', timeout: 30000 });
  await page.waitForTimeout(1500);
  try {
    const passwordTab = page.getByText('Password', { exact: true }).first();
    await passwordTab.click({ timeout: 8000 });
    await page.waitForTimeout(300);
    const emailInput = page.locator('input[type="email"]').first();
    await emailInput.fill('test@omnidome.local', { timeout: 8000 });
    const pwInput = page.locator('input[type="password"]').first();
    await pwInput.fill('OmniDomeTest2026!', { timeout: 8000 });
    const signInBtn = page.locator('button:has-text("Sign in"), button:has-text("Log in"), button[type="submit"]').first();
    await signInBtn.click({ timeout: 8000 });
  } catch (e) {
    logs.push(`[login-error] ${e.message}`);
  }
  await page.waitForTimeout(3000);
  await page.screenshot({ path: 'scripts/diag_01_post_login.png', fullPage: true });

  // Ensure we're on dashboard
  if (!page.url().includes('/dashboard')) {
    await page.goto('http://localhost:3000/dashboard', { waitUntil: 'domcontentloaded', timeout: 30000 });
    await page.waitForTimeout(2000);
  }

  // --- 1. Agent chat mic test ---
  logs.push('=== AGENT CHAT MIC TEST ===');
  try {
    const fab = page.locator('button[aria-label*="chat" i], button:has(svg)').last();
    // Try a more targeted selector first
    const chatTrigger = page.locator('button:has-text("Bot"), [class*="fixed"][class*="bottom"]').first();
    await page.locator('body').click({ position: { x: 1, y: 1 } }).catch(() => {});
    const fabButtons = await page.locator('button').all();
    let clicked = false;
    for (const btn of fabButtons) {
      const box = await btn.boundingBox().catch(() => null);
      if (box && box.x > 1300 && box.y > 850) {
        await btn.click({ timeout: 5000 });
        clicked = true;
        break;
      }
    }
    logs.push(`FAB clicked: ${clicked}`);
  } catch (e) {
    logs.push(`[agent-fab-error] ${e.message}`);
  }
  await page.waitForTimeout(1500);
  await page.screenshot({ path: 'scripts/diag_02_agent_chat_open.png', fullPage: true });

  try {
    const micBtn = page.locator('button[title="Voice input"], button[title="Stop recording"]').first();
    await micBtn.click({ timeout: 5000 });
    logs.push('Agent chat mic clicked (start)');
    await page.waitForTimeout(2000);
    await page.screenshot({ path: 'scripts/diag_03_agent_recording.png', fullPage: true });
    await micBtn.click({ timeout: 5000 });
    logs.push('Agent chat mic clicked (stop)');
    await page.waitForTimeout(3000);
    await page.screenshot({ path: 'scripts/diag_04_agent_after_stop.png', fullPage: true });
  } catch (e) {
    logs.push(`[agent-mic-error] ${e.message}`);
  }

  // --- 2. Call Center Whisper AI STT test ---
  logs.push('=== CALL CENTER WHISPER AI STT TEST ===');
  try {
    await page.goto('http://localhost:3000/dashboard?module=call-center', { waitUntil: 'domcontentloaded', timeout: 30000 }).catch(() => {});
    await page.waitForTimeout(2000);
    // Try clicking a Call Center nav item if module query param doesn't work
    const ccNav = page.locator('text=Call Center').first();
    if (await ccNav.isVisible().catch(() => false)) {
      await ccNav.click({ timeout: 5000 });
      await page.waitForTimeout(1500);
    }
    const whisperTab = page.locator('text=Whisper AI').first();
    await whisperTab.click({ timeout: 8000 });
    await page.waitForTimeout(1500);
    const sttSubtab = page.locator('text=Speech to Text').first();
    await sttSubtab.click({ timeout: 8000 });
    await page.waitForTimeout(1000);
    await page.screenshot({ path: 'scripts/diag_05_stt_panel.png', fullPage: true });

    const recordBtn = page.locator('button:has-text("Speak"), button[class*="rounded-full"]').first();
    await recordBtn.click({ timeout: 5000 });
    logs.push('STT record clicked (start)');
    await page.waitForTimeout(2500);
    await page.screenshot({ path: 'scripts/diag_06_stt_recording.png', fullPage: true });
    await recordBtn.click({ timeout: 5000 });
    logs.push('STT record clicked (stop)');
    await page.waitForTimeout(3000);
    await page.screenshot({ path: 'scripts/diag_07_stt_after_stop.png', fullPage: true });
  } catch (e) {
    logs.push(`[stt-error] ${e.message}`);
  }

  // --- 3. Call Center TTS test ---
  logs.push('=== CALL CENTER TTS TEST ===');
  try {
    const ttsSubtab = page.locator('text=Text to Speech').first();
    await ttsSubtab.click({ timeout: 8000 });
    await page.waitForTimeout(1000);
    const textarea = page.locator('textarea').first();
    await textarea.fill('Hello world testing testing', { timeout: 5000 });
    await page.screenshot({ path: 'scripts/diag_08_tts_before_generate.png', fullPage: true });
    const genBtn = page.locator('button:has-text("Generate Speech")').first();
    const isDisabled = await genBtn.isDisabled().catch(() => null);
    logs.push(`Generate Speech button disabled: ${isDisabled}`);
    await genBtn.click({ timeout: 5000, force: true });
    logs.push('Generate Speech clicked');
    await page.waitForTimeout(3000);
    await page.screenshot({ path: 'scripts/diag_09_tts_after_generate.png', fullPage: true });
  } catch (e) {
    logs.push(`[tts-error] ${e.message}`);
  }

  console.log('\n\n========== DIAGNOSTIC LOG ==========');
  console.log(logs.join('\n'));
  console.log('=====================================\n');

  await browser.close();
})();
