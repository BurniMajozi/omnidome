const { chromium } = require('playwright');
const path = require('path');

(async () => {
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({
    viewport: { width: 1280, height: 800 }
  });
  const page = await context.newPage();

  console.log('Navigating to dashboard...');
  await page.goto('http://localhost:3000/dashboard', { waitUntil: 'load' });
  await page.waitForTimeout(1000);

  // Print all visible links/buttons to debug layout
  const links = await page.locator('a, button').allInnerTexts();
  console.log('Available links & buttons on dashboard:', links);

  await browser.close();
})();
