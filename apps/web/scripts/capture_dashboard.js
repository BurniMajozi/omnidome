const { chromium } = require('playwright');
const path = require('path');

(async () => {
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({
    viewport: { width: 1280, height: 800 }
  });
  const page = await context.newPage();

  console.log('Navigating to dashboard...');
  await page.goto('http://localhost:3000/dashboard', { waitUntil: 'networkidle' });

  // Let animations complete
  await page.waitForTimeout(2000);

  const screenshotPath = path.join(__dirname, 'dashboard_initial.png');
  await page.screenshot({ path: screenshotPath });
  console.log(`Saved screenshot to ${screenshotPath}`);

  // Let's print out text content to verify if page loaded or if it's on a login/auth page
  const title = await page.title();
  console.log(`Page Title: ${title}`);

  // Check if we need to log in or bypass
  const bodyText = await page.innerText('body');
  if (bodyText.includes('Sign In') || bodyText.includes('Login')) {
    console.log('Detected auth/login screen.');
  }

  await browser.close();
})();
