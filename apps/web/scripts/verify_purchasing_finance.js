const { chromium } = require('playwright');
const path = require('path');

(async () => {
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
  const page = await context.newPage();

  page.on('console', (msg) => {
    if (msg.type() === 'error' || msg.type() === 'warning') console.log(`PAGE ${msg.type().toUpperCase()}:`, msg.text());
  });
  page.on('requestfinished', (req) => {
    if (req.url().includes('/svc/inventory') || req.url().includes('/svc/finance')) {
      console.log('REQUEST:', req.url(), '->', req.response()?.then?.(r => r?.status()));
    }
  });
  page.on('response', (res) => {
    if (res.url().includes('/svc/inventory') || res.url().includes('/svc/finance')) {
      console.log('RESPONSE:', res.status(), res.url());
    }
  });
  page.on('pageerror', (err) => console.log('PAGE EXCEPTION:', err.message));

  console.log('Navigating to dashboard...');
  await page.goto('http://localhost:3000/dashboard', { waitUntil: 'networkidle', timeout: 30000 });
  await page.waitForTimeout(1500);

  const title = await page.title();
  console.log('Page title:', title);
  const bodyText = await page.innerText('body');
  if (bodyText.includes('Sign In') || bodyText.includes('Sign in') || bodyText.includes('Login')) {
    console.log('AUTH WALL detected — cannot verify dashboard sections without a session.');
    await page.screenshot({ path: path.join(__dirname, 'verify_authwall.png') });
    await browser.close();
    return;
  }

  console.log('No auth wall — looking for Inventory nav link...');
  const invLink = page.locator('text=Inventory').first();
  if (await invLink.count() > 0) {
    await invLink.click();
    await page.waitForTimeout(6000);
    await page.screenshot({ path: path.join(__dirname, 'verify_inventory_module.png'), fullPage: true, timeout: 60000 });
    console.log('Saved verify_inventory_module.png');

    const poText = await page.innerText('body');
    console.log('Found "Purchase Orders" heading:', poText.includes('Purchase Orders'));

    const poSection = page.locator('h4:has-text("Purchase Orders")').first();
    if (await poSection.count() > 0) {
      await poSection.scrollIntoViewIfNeeded();
      await page.waitForTimeout(1000);
      const card = poSection.locator('xpath=ancestor::div[contains(@class,"surface-card")]').first();
      await (await card.count() > 0 ? card : poSection).screenshot({ path: path.join(__dirname, 'verify_purchasing_closeup.png'), timeout: 60000 });
      console.log('Saved verify_purchasing_closeup.png');

      // Open the "New Purchase Order" dialog to verify the form renders
      const newPoBtn = page.locator('button:has-text("New Purchase Order")').first();
      if (await newPoBtn.count() > 0) {
        await newPoBtn.click();
        await page.waitForTimeout(800);
        await page.screenshot({ path: path.join(__dirname, 'verify_purchasing_dialog.png'), timeout: 60000 });
        console.log('Saved verify_purchasing_dialog.png');
        await page.keyboard.press('Escape');
        await page.waitForTimeout(500);
      }
    }
  } else {
    console.log('Could not find Inventory nav link');
  }

  console.log('Looking for Finance nav link...');
  const finLink = page.locator('text=Finance').first();
  if (await finLink.count() > 0) {
    await finLink.click();
    await page.waitForTimeout(1500);
    // Click the Journals tab if present
    const journalsTab = page.locator('text=Journals').first();
    if (await journalsTab.count() > 0) {
      await journalsTab.click();
      await page.waitForTimeout(2000);
    }
    await page.screenshot({ path: path.join(__dirname, 'verify_finance_module.png'), fullPage: true, timeout: 60000 });
    console.log('Saved verify_finance_module.png');

    const jeText = await page.innerText('body');
    console.log('Found "Journal Entries (live)" heading:', jeText.includes('Journal Entries (live)'));

    const jeSection = page.locator('h4:has-text("Journal Entries (live)")').first();
    if (await jeSection.count() > 0) {
      await jeSection.scrollIntoViewIfNeeded();
      await page.waitForTimeout(1000);
      const card = jeSection.locator('xpath=ancestor::div[contains(@class,"surface-card")]').first();
      await (await card.count() > 0 ? card : jeSection).screenshot({ path: path.join(__dirname, 'verify_journal_closeup.png'), timeout: 60000 });
      console.log('Saved verify_journal_closeup.png');
    }
  } else {
    console.log('Could not find Finance nav link');
  }

  await browser.close();
})();
