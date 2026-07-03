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

  // Directly navigate to the URL since we know the routing prefix is /dashboard/... or /retention/...
  // Let's print out all hrefs from anchors to find the exact target URL
  const hrefs = await page.locator('a').evaluateAll(links => links.map(l => ({ text: l.innerText, href: l.href })));
  console.log('Available links & hrefs:', hrefs);

  await browser.close();
})();
