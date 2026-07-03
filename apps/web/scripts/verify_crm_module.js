const { chromium } = require('playwright');
const path = require('path');

(async () => {
  console.log('Launching chromium...');
  const browser = await chromium.launch({ headless: true, args: ['--no-sandbox'] });
  console.log('Chromium launched.');
  const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
  const page = await context.newPage();
  console.log('Page created. Testing basic nav to about:blank...');
  await page.goto('about:blank');
  console.log('about:blank OK.');
  try {
    console.log('Testing nav to example.com...');
    await page.goto('http://example.com', { timeout: 10000 });
    console.log('example.com OK:', await page.title());
  } catch (e) {
    console.log('example.com FAILED:', e.message);
  }

  const consoleErrors = [];
  page.on('console', (msg) => {
    if (msg.type() === 'error') consoleErrors.push(msg.text());
  });
  page.on('pageerror', (err) => consoleErrors.push(`pageerror: ${err.message}`));

  console.log('Navigating to dashboard...');
  await page.goto('http://127.0.0.1:3000/dashboard', { waitUntil: 'domcontentloaded', timeout: 30000 });
  await page.waitForTimeout(3000);

  const bodyText = await page.innerText('body');
  console.log('Title:', await page.title());
  if (bodyText.includes('Sign In') || bodyText.includes('Sign in') || bodyText.includes('Log in')) {
    console.log('AUTH SCREEN DETECTED');
    await page.screenshot({ path: path.join(__dirname, 'shot_auth.png') });
  } else {
    console.log('Clicking CRM nav item...');
    await page.click('text=CRM');
    await page.waitForTimeout(2000);
    await page.screenshot({ path: path.join(__dirname, 'shot_crm.png'), fullPage: true });
    console.log('Screenshot saved.');
    const text = await page.innerText('body');
    console.log('--- BODY TEXT SNIPPET ---');
    console.log(text.slice(0, 3000));
  }

  console.log('--- CONSOLE ERRORS ---');
  console.log(consoleErrors.length ? consoleErrors.join('\n') : '(none)');

  await browser.close();
})();
