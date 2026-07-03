const { chromium } = require('playwright');
(async () => {
  const browser = await chromium.launch({ headless: true, args: ['--no-sandbox'] });
  const page = await (await browser.newContext({ viewport: { width: 700, height: 900 } })).newPage();
  page.on('console', (msg) => { if (msg.type() === 'error') console.log('[error]', msg.text()); });
  await page.goto('http://localhost:3000/dashboard', { waitUntil: 'domcontentloaded', timeout: 30000 });
  await page.waitForTimeout(2000);
  // Try to find and open the agent chat UI
  const chatButton = page.locator('button:has-text("DomeBot"), [aria-label*="chat" i], button:has-text("Agent")').first();
  try {
    await chatButton.click({ timeout: 5000 });
  } catch (e) {
    console.log('Could not find a chat trigger button:', e.message);
  }
  await page.waitForTimeout(1500);
  const input = page.locator('input[placeholder*="Message" i], textarea[placeholder*="Message" i]').first();
  try {
    await input.fill('Hola', { timeout: 5000 });
    await input.press('Enter');
  } catch (e) {
    console.log('Could not find chat input:', e.message);
  }
  await page.waitForTimeout(6000);
  await page.screenshot({ path: 'scripts/final_agent_chat.png', fullPage: true });
  const text = await page.innerText('body');
  console.log('Contains "unreachable":', text.includes('unreachable'));
  console.log('Contains "AG-UI run failed":', text.includes('AG-UI run failed'));
  await browser.close();
})();
