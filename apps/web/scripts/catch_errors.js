const { chromium } = require('playwright');

(async () => {
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext();
  const page = await context.newPage();

  // Listen to browser console errors
  page.on('console', msg => {
    if (msg.type() === 'error') {
      console.log('BROWSER ERROR:', msg.text());
    }
  });

  page.on('pageerror', exception => {
    console.log('UNCAUGHT EXCEPTION:', exception.message);
  });

  console.log('Navigating to Journeys...');
  await page.goto('http://localhost:3000/dashboard', { waitUntil: 'load' });
  await page.waitForTimeout(1000);
  await page.click('text=Journeys');
  await page.waitForTimeout(1000);

  console.log('Clicking "Create First Journey"...');
  await page.click('text=Create First Journey');
  await page.waitForTimeout(2000);

  await browser.close();
})();
