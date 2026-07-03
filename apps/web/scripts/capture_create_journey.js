const { chromium } = require('playwright');
const path = require('path');

(async () => {
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({
    viewport: { width: 1280, height: 800 }
  });
  const page = await context.newPage();

  console.log('Navigating to Journeys...');
  await page.goto('http://localhost:3000/dashboard', { waitUntil: 'load' });
  await page.waitForTimeout(1000);
  await page.click('text=Journeys');
  await page.waitForTimeout(1000);

  // Click on "Create First Journey"
  console.log('Clicking "Create First Journey"...');
  await page.click('text=Create First Journey');
  await page.waitForTimeout(2000);

  const screenshotPath = path.join(__dirname, 'create_journey_modal.png');
  await page.screenshot({ path: screenshotPath });
  console.log(`Saved screenshot to ${screenshotPath}`);

  await browser.close();
})();
