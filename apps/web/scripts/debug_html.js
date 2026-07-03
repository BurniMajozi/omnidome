const { chromium } = require('playwright');

(async () => {
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage();
  console.log('Navigating to dashboard...');
  await page.goto('http://localhost:3000/dashboard', { waitUntil: 'load' });
  await page.waitForTimeout(2000);
  
  const content = await page.content();
  console.log('HTML content length:', content.length);
  // Log first 1000 characters
  console.log(content.substring(0, 1000));
  
  await browser.close();
})();
