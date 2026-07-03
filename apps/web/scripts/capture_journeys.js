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

  // Directly locate by matching elements within the sidebar navigation tree structure.
  // Click target with text 'Journeys' that has tag <a> or <span>
  console.log('Attempting selector click...');
  await page.click('text=Journeys');
  
  await page.waitForTimeout(2000); // Wait for page transition

  const screenshotPath = path.join(__dirname, 'retention_journeys.png');
  await page.screenshot({ path: screenshotPath });
  console.log(`Saved screenshot to ${screenshotPath}`);

  await browser.close();
})();
