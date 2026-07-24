const { chromium } = require('playwright');
const path = require('path');

// Credentials come from the environment — nothing secret is committed here.
// Run with, e.g.:
//   SUPABASE_URL=... SUPABASE_ANON_KEY=... VERIFY_TEST_EMAIL=... VERIFY_TEST_PASSWORD=... node scripts/verify_hermes_chat.js
// (the *_SUPABASE_* values live in apps/web/.env, which is gitignored).
const SUPABASE_URL = process.env.SUPABASE_URL || process.env.NEXT_PUBLIC_SUPABASE_URL;
const ANON_KEY = process.env.SUPABASE_ANON_KEY || process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;
const TEST_EMAIL = process.env.VERIFY_TEST_EMAIL;
const TEST_PASSWORD = process.env.VERIFY_TEST_PASSWORD;

for (const [name, value] of Object.entries({ SUPABASE_URL, ANON_KEY, TEST_EMAIL, TEST_PASSWORD })) {
  if (!value) {
    console.error(`FATAL: missing required env var for ${name}. See the header comment for usage.`);
    process.exit(1);
  }
}

// Derive the project ref from the Supabase URL (used for the localStorage auth key).
const SUPABASE_PROJECT_REF = new URL(SUPABASE_URL).hostname.split('.')[0];

(async () => {
  // Sign in as a real Supabase user (created + confirmed earlier via the admin
  // API) to get a real session -- this is what a logged-in browser would have,
  // no manual header injection into the orchestrator proxy.
  console.log('Signing in as test user...');
  const signInRes = await fetch(`${SUPABASE_URL}/auth/v1/token?grant_type=password`, {
    method: 'POST',
    headers: { apikey: ANON_KEY, 'Content-Type': 'application/json' },
    body: JSON.stringify({ email: TEST_EMAIL, password: TEST_PASSWORD }),
  });
  const session = await signInRes.json();
  if (!session.access_token) {
    console.error('FATAL: sign-in failed:', JSON.stringify(session));
    process.exit(1);
  }
  console.log('Signed in, got real access token for', session.user.email);

  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({ viewport: { width: 1400, height: 900 } });

  // Seed the Supabase browser SDK's localStorage session before any app JS runs --
  // this is exactly the state a real successful login leaves behind.
  await context.addInitScript(({ key, session }) => {
    window.localStorage.setItem(key, JSON.stringify(session));
  }, { key: `sb-${SUPABASE_PROJECT_REF}-auth-token`, session });

  const page = await context.newPage();
  const errors = [];
  page.on('console', (msg) => { if (msg.type() === 'error') errors.push(msg.text()); });

  console.log('Navigating to dashboard...');
  await page.goto('http://localhost:3000/dashboard', { waitUntil: 'domcontentloaded', timeout: 30000 });
  await page.waitForTimeout(3000);
  await page.screenshot({ path: path.join(__dirname, 'verify_01_dashboard.png') });
  console.log('Title:', await page.title());

  const bodyText = await page.innerText('body');
  if (bodyText.includes('Sign In') || bodyText.includes('Login')) {
    console.log('AUTH WALL DETECTED — cannot proceed without credentials.');
    await browser.close();
    return;
  }

  // Look for a chat toggle button (icon button, likely in header)
  const chatButton = page.locator('button[aria-label*="chat" i], button[title*="chat" i], button:has-text("Chat")').first();
  const chatButtonCount = await chatButton.count();
  console.log('Chat toggle buttons found:', chatButtonCount);

  if (chatButtonCount === 0) {
    console.log('No obvious chat button found by label/title/text. Dumping all button labels for inspection.');
    const buttons = await page.locator('button').allInnerTexts();
    console.log('Buttons on page:', JSON.stringify(buttons.slice(0, 40)));
    const ariaLabels = await page.locator('button[aria-label]').evaluateAll(els => els.map(e => e.getAttribute('aria-label')));
    console.log('Aria-labelled buttons:', JSON.stringify(ariaLabels));
    await browser.close();
    return;
  }

  await chatButton.click();
  await page.waitForTimeout(1000);
  await page.screenshot({ path: path.join(__dirname, 'verify_02_chat_opened.png') });

  // Find the chat input and send a message
  const input = page.locator('textarea, input[placeholder*="Message" i], input:not([type="checkbox"]):not([type="radio"])').last();
  await input.fill('Hello! Just say hi back, no need to look anything up.');
  await page.screenshot({ path: path.join(__dirname, 'verify_03_typed.png') });
  await input.press('Enter');

  console.log('Waiting for response...');
  await page.waitForTimeout(90000);
  await page.screenshot({ path: path.join(__dirname, 'verify_04_response.png') });

  const finalText = await page.innerText('body');
  console.log('--- Console errors ---');
  console.log(errors.length ? errors.join('\n') : '(none)');
  console.log('--- Page text snippet (last 1500 chars) ---');
  console.log(finalText.slice(-1500));

  await browser.close();
})().catch((err) => {
  console.error('FATAL:', err);
  process.exit(1);
});
