const { chromium } = require('playwright');
const path = require('path');

const modules = [
  { key: 'crm', label: 'CRM', shot: 'final_crm.png' },
  { key: 'marketing', label: 'Marketing', shot: 'final_marketing.png' },
  { key: 'finance', label: 'Finance', shot: 'final_finance.png' },
  { key: 'products', label: 'Product Management', shot: 'final_products.png' },
];

(async () => {
  const browser = await chromium.launch({ headless: true, args: ['--no-sandbox'] });
  const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
  const page = await context.newPage();

  const consoleErrors = [];
  page.on('console', (msg) => {
    if (msg.type() === 'error') consoleErrors.push(msg.text());
  });
  page.on('pageerror', (err) => consoleErrors.push(`pageerror: ${err.message}`));

  console.log('Navigating to dashboard...');
  await page.goto('http://localhost:3000/dashboard', { waitUntil: 'domcontentloaded', timeout: 30000 });
  await page.waitForTimeout(2000);

  const bodyText = await page.innerText('body');
  if (bodyText.includes('Sign In') || bodyText.includes('Sign in') || bodyText.includes('Log in')) {
    console.log('AUTH SCREEN DETECTED');
    await page.screenshot({ path: path.join(__dirname, 'final_auth.png') });
    await browser.close();
    return;
  }

  for (const mod of modules) {
    console.log(`\n--- ${mod.label} ---`);
    consoleErrors.length = 0;
    try {
      await page.click(`text=${mod.label}`, { timeout: 5000 });
      await page.waitForTimeout(10000);
      await page.screenshot({ path: path.join(__dirname, mod.shot), fullPage: true });
      console.log(`Screenshot saved: ${mod.shot}`);
      const text = await page.innerText('body');
      console.log('Snippet:', text.slice(0, 400).replace(/\s+/g, ' '));
      console.log('Console errors:', consoleErrors.length ? consoleErrors.join(' | ') : '(none)');
    } catch (e) {
      console.log(`FAILED on ${mod.label}:`, e.message);
    }
  }

  await browser.close();
})();
