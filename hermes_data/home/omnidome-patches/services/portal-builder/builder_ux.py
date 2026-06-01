"""
Portal Builder UIX — Served at /builder
Drag-and-drop landing page builder, campaign push, and SEO management.
"""

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter()


BUILDER_HTML = """
<!DOCTYPE html>
<html lang="en" class="dark">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>OmniDome — Portal Builder</title>
<style>
:root {
  --bg: #09090b; --bg2: #18181b; --bg3: #27272a; --bg4: #3f3f46;
  --border: #27272a; --border2: #3f3f46;
  --text: #fafafa; --text2: #a1a1aa; --text3: #71717a;
  --accent: #8b5cf6; --accent2: #a78bfa; --accent-bg: rgba(139,92,246,0.12);
  --green: #22c55e; --green-bg: rgba(34,197,94,0.1);
  --blue: #3b82f6; --blue-bg: rgba(59,130,246,0.1);
  --amber: #f59e0b; --amber-bg: rgba(245,158,11,0.1);
  --red: #ef4444; --red-bg: rgba(239,68,68,0.1);
  --radius: 10px;
}
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;background:var(--bg);color:var(--text);height:100vh;overflow:hidden;display:flex;flex-direction:column}
button{cursor:pointer;border:none;background:none;color:inherit;font:inherit}
input,textarea,select{font:inherit;outline:none;color:var(--text)}

/* ── Top Bar ── */
.topbar{height:52px;background:var(--bg2);border-bottom:1px solid var(--border);display:flex;align-items:center;padding:0 16px;gap:12px;flex-shrink:0}
.topbar-logo{font-size:15px;font-weight:700;display:flex;align-items:center;gap:8px}
.topbar-logo span{background:var(--accent);color:#fff;padding:4px 8px;border-radius:6px;font-size:11px;font-weight:800}
.topbar-tabs{display:flex;gap:2px;margin-left:8px}
.topbar-tab{padding:6px 14px;border-radius:7px;font-size:13px;font-weight:500;color:var(--text2);transition:all .15s}
.topbar-tab:hover{color:var(--text);background:var(--bg3)}
.topbar-tab.active{color:var(--accent);background:var(--accent-bg)}
.topbar-actions{margin-left:auto;display:flex;align-items:center;gap:8px}
.btn{padding:7px 14px;border-radius:7px;font-size:13px;font-weight:600;transition:all .15s;display:flex;align-items:center;gap:6px}
.btn-ghost{color:var(--text2)}.btn-ghost:hover{color:var(--text);background:var(--bg3)}
.btn-primary{background:var(--accent);color:#fff}.btn-primary:hover{background:var(--accent2)}
.btn-success{background:var(--green);color:#000}.btn-success:hover{opacity:.9}
.btn-amber{background:var(--amber);color:#000}
.select{background:var(--bg3);border:1px solid var(--border);border-radius:7px;padding:6px 10px;font-size:13px;color:var(--text)}

/* ── Layout ── */
.builder-layout{display:flex;flex:1;overflow:hidden}

/* Left Panel — Block Palette */
.left-panel{width:240px;background:var(--bg2);border-right:1px solid var(--border);display:flex;flex-direction:column;flex-shrink:0}
.panel-section{padding:12px;border-bottom:1px solid var(--border)}
.panel-title{font-size:10px;text-transform:uppercase;letter-spacing:1.2px;color:var(--text3);font-weight:600;margin-bottom:8px;padding:0 4px}
.block-grid{display:grid;grid-template-columns:1fr 1fr;gap:6px}
.block-item{background:var(--bg3);border:1px solid var(--border);border-radius:8px;padding:10px 8px;text-align:center;cursor:grab;transition:all .15s}
.block-item:hover{border-color:var(--accent);background:var(--accent-bg)}
.block-item-icon{font-size:18px;margin-bottom:4px}
.block-item-label{font-size:11px;color:var(--text2);font-weight:500}

/* Canvas */
.canvas-area{flex:1;display:flex;flex-direction:column;overflow:hidden;background:var(--bg)}
.canvas-toolbar{height:40px;background:var(--bg2);border-bottom:1px solid var(--border);display:flex;align-items:center;padding:0 12px;gap:8px}
.device-btn{width:28px;height:28px;border-radius:5px;display:flex;align-items:center;justify-content:center;color:var(--text3);font-size:14px}
.device-btn:hover,.device-btn.active{background:var(--bg3);color:var(--text)}
.canvas-scroll{flex:1;overflow:auto;display:flex;justify-content:center;padding:24px}
.page-canvas{width:100%;max-width:800px;min-height:600px;background:#fff;border-radius:12px;overflow:hidden;box-shadow:0 0 0 1px rgba(0,0,0,0.1),0 20px 60px rgba(0,0,0,0.3);position:relative}
.page-block{position:relative;cursor:pointer;transition:box-shadow .15s}
.page-block:hover{outline:2px solid var(--accent);outline-offset:-2px}
.page-block.selected{outline:2px solid var(--accent2);outline-offset:-2px}
.page-block-controls{position:absolute;top:-32px;right:0;display:none;gap:4px;z-index:10}
.page-block:hover .page-block-controls,.page-block.selected .page-block-controls{display:flex}
.block-ctrl{width:26px;height:26px;border-radius:5px;background:var(--accent);color:#fff;font-size:11px;display:flex;align-items:center;justify-content:center}
.block-ctrl:hover{background:var(--accent2)}
.block-ctrl.delete{background:var(--red)}.block-ctrl.delete:hover{opacity:.8}

/* Right Panel — Properties */
.right-panel{width:280px;background:var(--bg2);border-left:1px solid var(--border);overflow-y:auto;flex-shrink:0}
.prop-group{padding:14px;border-bottom:1px solid var(--border)}
.prop-label{font-size:11px;color:var(--text3);font-weight:600;margin-bottom:6px}
.prop-input{width:100%;background:var(--bg3);border:1px solid var(--border);border-radius:7px;padding:7px 10px;font-size:13px;color:var(--text)}
.prop-input:focus{border-color:var(--accent)}
.prop-textarea{width:100%;min-height:80px;background:var(--bg3);border:1px solid var(--border);border-radius:7px;padding:7px 10px;font-size:13px;resize:vertical}
.prop-row{display:flex;gap:8px}
.prop-row>*{flex:1}

/* SEO Panel */
.seo-score{display:flex;align-items:center;gap:12px;padding:12px;background:var(--bg3);border-radius:var(--radius);margin-bottom:10px}
.seo-score-circle{width:48px;height:48px;border-radius:50%;background:conic-gradient(var(--green) 0% 78%, var(--bg4) 78% 100%);display:flex;align-items:center;justify-content:center;font-size:13px;font-weight:700}
.seo-score-inner{width:38px;height:38px;border-radius:50%;background:var(--bg3);display:flex;align-items:center;justify-content:center;color:var(--green)}
.seo-check{font-size:12px;padding:4px 0;display:flex;align-items:center;gap:6px;color:var(--text2)}
.seo-check .icon{color:var(--green);font-size:13px}
.seo-check .icon.warn{color:var(--amber)}
.seo-check .icon.fail{color:var(--red)}

/* Pages list */
.pages-list{max-height:200px;overflow-y:auto}
.page-list-item{display:flex;align-items:center;gap:8px;padding:8px 10px;border-radius:7px;cursor:pointer;font-size:13px;color:var(--text2);transition:all .1s}
.page-list-item:hover{background:var(--bg3);color:var(--text)}
.page-list-item.active{background:var(--accent-bg);color:var(--accent)}
.page-status{width:7px;height:7px;border-radius:50%;flex-shrink:0}
.page-status.published{background:var(--green)}.page-status.draft{background:var(--amber)}.page-status.archived{background:var(--text3)}

/* Block content rendering */
.block-hero{padding:60px 40px;text-align:center;background:linear-gradient(135deg,#1e1b4b,#312e81);color:#fff}
.block-hero h2{font-size:28px;font-weight:700;margin-bottom:12px}
.block-hero p{font-size:15px;color:rgba(255,255,255,0.7);max-width:500px;margin:0 auto 20px}
.block-hero .cta{display:inline-block;background:var(--accent);color:#fff;padding:10px 24px;border-radius:8px;font-size:14px;font-weight:600}
.block-features{padding:40px;display:grid;grid-template-columns:repeat(3,1fr);gap:20px}
.feature-card{padding:24px;background:var(--bg2);border:1px solid var(--border);border-radius:var(--radius);text-align:center}
.feature-icon{font-size:28px;margin-bottom:10px}
.feature-title{font-size:15px;font-weight:600;color:var(--text);margin-bottom:6px}
.feature-desc{font-size:12px;color:var(--text3);line-height:1.5}
.block-form{padding:40px;max-width:500px;margin:0 auto}
.block-form h3{font-size:20px;font-weight:700;color:var(--text);margin-bottom:20px;text-align:center}
.form-group{margin-bottom:14px}
.form-group label{display:block;font-size:12px;color:var(--text3);margin-bottom:4px;font-weight:500}
.form-group input,.form-group select,.form-group textarea{width:100%;background:var(--bg2);border:1px solid var(--border);border-radius:7px;padding:9px 12px;font-size:13px;color:(--text)}
.form-group input:focus{border-color:var(--accent)}
.block-cta{padding:40px;text-align:center;background:var(--bg2)}
.block-cta h3{font-size:22px;font-weight:700;color:var(--text);margin-bottom:8px}
.block-cta p{font-size:14px;color:var(--text3);margin-bottom:16px}
.block-testimonial{padding:40px;background:var(--bg2)}
.testimonial-card{padding:24px;border-left:3px solid var(--accent);background:var(--bg);border-radius:0 var(--radius) var(--radius) 0}
.testimonial-text{font-size:14px;color:var(--text2);line-height:1.6;font-style:italic;margin-bottom:10px}
.testimonial-author{font-size:13px;font-weight:600;color:var(--text)}.testimonial-role{font-size:11px;color:var(--text3)}
.block-pricing{padding:40px;display:flex;gap:16px;justify-content:center}
.pricing-card{padding:28px;background:var(--bg2);border:1px solid var(--border);border-radius:var(--radius);text-align:center;min-width:180px}
.pricing-card.highlighted{border-color:var(--accent);box-shadow:0 0 0 1px var(--accent)}
.pricing-card h4{font-size:16px;font-weight:700;color:var(--text);margin-bottom:8px}
.pricing-card .price{font-size:32px;font-weight:800;color:var(--accent);margin-bottom:4px}
.pricing-card .period{font-size:12px;color:var(--text3);margin-bottom:16px}
.pricing-features{text-align:left;font-size:12px;color:var(--text2);margin-bottom:16px}
.pricing-features li{padding:3px 0}
.block-text{padding:30px 40px}
.block-text h3{font-size:20px;font-weight:700;color:var(--text);margin-bottom:10px}
.block-text p{font-size:14px;color:var(--text2);line-height:1.7}
.block-html{padding:20px 40px}

/* Empty state */
.empty-canvas{display:flex;flex-direction:column;align-items:center;justify-content:center;height:400px;color:var(--text3);gap:8px}
.empty-canvas .icon{font-size:32px;opacity:.4}
.empty-canvas p{font-size:14px}
</style>
</head>
<body>

<!-- Top Bar -->
<div class="topbar">
  <div class="topbar-logo"><span>O</span> OmniDome</div>
  <div class="topbar-tabs">
    <button class="tab-builder" onclick="showBuilder()">📝 Builder</button>
    <button class="tab-campaigns" onclick="showCampaigns()">📣 Campaigns</button>
    <button class="tab-pages" onclick="showPages()">📄 Pages</button>
    <button class="tab-integrations sb-level-pro" onclick="showIntegrations()">🔗 Integrations</button>
  </div>
  <div class="topbar-actions">
    <select class="select" id="pageSelect" onchange="loadPage(this.value)">
      <option value="">— Select Page —</option>
    </select>
    <button class="btn btn-ghost" onclick="newPage()">+ New</button>
    <button class="btn btn-ghost" onclick="previewPage()">👁 Preview</button>
    <button class="btn btn-amber" onclick="savePage()">Save</button>
    <button class="btn btn-success" onclick="publishPage()">Publish</button>
  </div>
</div>

<!-- Builder Layout -->
<div class="builder-layout">
  <!-- Left: Block Palette -->
  <div class="left-panel" id="leftPanel">
    <div class="panel-section">
      <div class="panel-title">Blocks</div>
      <div class="block-grid">
        <div class="block-item" draggable="true" data-block="hero" ondragstart="dragStart(event)">
          <div class="block-item-icon">🦸</div><div class="block-item-label">Hero</div>
        </div>
        <div class="block-item" draggable="true" data-block="features" ondragstart="dragStart(event)">
          <div class="block-item-icon">✨</div><div class="block-item-label">Features</div>
        </div>
        <div class="block-item" draggable="true" data-block="text" ondragstart="dragStart(event)">
          <div class="block-item-icon">📝</div><div class="block-item-label">Text</div>
        </div>
        <div class="block-item" draggable="true" data-block="form" ondragstart="dragStart(event)">
          <div class="block-item-icon">📋</div><div class="block-item-label">Form</div>
        </div>
        <div class="block-item" draggable="true" data-block="cta" ondragstart="dragStart(event)">
          <div class="block-item-icon">🎯</div><div class="block-item-label">CTA</div>
        </div>
        <div class="block-item" draggable="true" data-block="pricing" ondragstart="dragStart(event)">
          <div class="block-item-icon">💰</div><div class="block-item-label">Pricing</div>
        </div>
        <div class="block-item" draggable="true" data-block="testimonial" ondragstart="dragStart(event)">
          <div class="block-item-icon">💬</div><div class="block-item-label">Testimonial</div>
        </div>
        <div class="block-item" draggable="true" data-block="html" ondragstart="dragStart(event)">
          <div class="block-item-icon">⚡</div><div class="block-item-label">Custom HTML</div>
        </div>
      </div>
    </div>
    <div class="panel-section">
      <div class="panel-title">My Pages</div>
      <div class="pages-list" id="pagesList"></div>
    </div>
  </div>

  <!-- Canvas -->
  <div class="canvas-area">
    <div class="canvas-toolbar">
      <button class="device-btn active" onclick="setDevice('desktop')" title="Desktop">🖥</button>
      <button class="device-btn" onclick="setDevice('tablet')" title="Tablet">📱</button>
      <button class="device-btn" onclick="setDevice('mobile')" title="Mobile">📲</button>
      <div style="flex:1"></div>
      <span style="font-size:11px;color:var(--text3)" id="canvasInfo">Untitled Page</span>
    </div>
    <div class="canvas-scroll">
      <div class="page-canvas" id="pageCanvas" ondrop="dropBlock(event)" ondragover="allowDrop(event)">
        <div class="empty-canvas" id="emptyState">
          <div class="icon">📄</div>
          <p>Drag blocks here to start building</p>
        </div>
      </div>
    </div>
  </div>

  <!-- Right: Properties -->
  <div class="right-panel" id="rightPanel">
    <div class="prop-group">
      <div class="prop-label">Page Settings</div>
      <input class="prop-input" id="propTitle" placeholder="Page Title" style="margin-bottom:8px" oninput="updatePageMeta()">
      <input class="prop-input" id="propSlug" placeholder="URL Slug (e.g. fibre-promo)">
    </div>
    <div class="prop-group">
      <div class="prop-label">SEO — Meta Tags</div>
      <input class="prop-input" id="propSeoTitle" placeholder="SEO Title (60 chars)" maxlength="60" style="margin-bottom:8px">
      <textarea class="prop-textarea" id="propSeoDesc" placeholder="Meta Description (160 chars)" maxlength="160" rows="3" style="margin-bottom:8px"></textarea>
      <input class="prop-input" id="propSeoKeywords" placeholder="Keywords (comma separated)">
    </div>
    <div class="prop-group">
      <div class="prop-label">SEO Score</div>
      <div class="seo-score">
        <div class="seo-score-circle"><div class="seo-score-inner" id="seoScore">0</div></div>
        <div>
          <div style="font-size:14px;font-weight:600;color:var(--text)" id="seoLabel">Not analysed</div>
          <div style="font-size:11px;color:var(--text3)">Add title, description & content</div>
        </div>
      </div>
      <div class="seo-check"><span class="icon" id="seoCheckTitle">○</span> Title set (60 chars)</div>
      <div class="seo-check"><span class="icon" id="seoCheckDesc">○</span> Description set (160 chars)</div>
      <div class="seo-check"><span class="icon" id="seoCheckKeywords">○</span> Keywords defined</div>
      <div class="seo-check"><span class="icon" id="seoCheckH1">○</span> Has H1 heading</div>
      <div class="seo-check"><span class="icon" id="seoCheckImg">○</span> Images with alt text</div>
      <div class="seo-check"><span class="icon" id="seoCheckSlug">○</span> Clean URL slug</div>
    </div>
    <div class="prop-group">
      <div class="prop-label">Open Graph</div>
      <input class="prop-input" id="propOgImage" placeholder="OG Image URL" style="margin-bottom:8px">
      <textarea class="prop-textarea" id="propOgDesc" placeholder="OG Description" rows="2"></textarea>
    </div>
    <div class="prop-group">
      <div class="prop-label">JSON-LD Structured Data</div>
      <textarea class="prop-textarea" id="propJsonLd" placeholder='{"@type":"Product",...}' rows="4" style="font-family:monospace;font-size:11px"></textarea>
    </div>
  </div>
</div>

<script>
let currentBlocks = [];
let selectedBlock = null;
let pageId = null;

// ── Drag & Drop ──
function dragStart(e) { e.dataTransfer.setData('blockType', e.target.dataset.block); }
function allowDrop(e) { e.preventDefault(); }
function dropBlock(e) {
  e.preventDefault();
  const type = e.dataTransfer.getData('blockType');
  if (type) addBlock(type);
}

// ── Block Templates ──
const blockTemplates = {
  hero: { html: `<div class="block-hero"><h2>Welcome to OmniDome</h2><p>The complete ISP operating system. Built for South African fibre providers.</p><div class="cta">Get Started</div></div>`, data: { title: 'Welcome to OmniDome', subtitle: 'The complete ISP operating system.', cta: 'Get Started' }},
  features: { html: `<div class="block-features"><div class="feature-card"><div class="feature-icon">📡</div><div class="feature-title">Network Ops</div><div class="feature-desc">Real-time monitoring</div></div><div class="feature-card"><div class="feature-icon">📊</div><div class="feature-title">Analytics</div><div class="feature-desc">AI-powered insights</div></div><div class="feature-card"><div class="feature-icon">🤝</div><div class="feature-title">CRM</div><div class="feature-desc">Customer 360</div></div></div>`, data: {}},
  text: { html: `<div class="block-text"><h3>Your Heading Here</h3><p>Lorem ipsum dolor sit amet, consectetur adipiscing elit. Praesent commodo cursus magna, vel scelerisque nisl consectetur et.</p></div>`, data: { heading: 'Your Heading Here', body: 'Lorem ipsum dolor sit amet...' }},
  form: { html: `<div class="block-form"><h3>Get In Touch</h3><div class="form-group"><label>Name</label><input placeholder="Your name"></div><div class="form-group"><label>Email</label><input placeholder="you@example.com"></div><div class="form-group"><label>Package</label><select><option>Select package<option>Basic — R200/mo<option>Standard — R350/mo<option>Premium — R500/mo</select></div><div style="text-align:center"><div class="cta">Submit</div></div></div>`, data: { title: 'Get In Touch' }},
  cta: { html: `<div class="block-cta"><h3>Ready to upgrade your ISP?</h3><p>Join 50+ South African fibre providers using OmniDome.</p><div style="display:inline-block;background:var(--accent);color:#fff;padding:10px 24px;border-radius:8px;font-size:14px;font-weight:600">Request a Demo</div></div>`, data: {}},
  pricing: { html: `<div class="block-pricing"><div class="pricing-card"><h4>Starter</h4><div class="price">R299</div><div class="period">/month</div><ul class="pricing-features"><li>✓ 5 users</li><li>✓ CRM + Billing</li><li>✓ Email support</li></ul></div><div class="pricing-card highlighted"><h4>Professional</h4><div class="price">R799</div><div class="period">/month</div><ul class="pricing-features"><li>✓ Unlimited users</li><li>✓ All modules</li><li>✓ Network + IoT</li><li>✓ Priority support</li></ul></div><div class="pricing-card"><h4>Enterprise</h4><div class="price">Custom</div><div class="period">&nbsp;</div><ul class="pricing-features"><li>✓ Everything in Pro</li><li>✓ AI Agents</li><li>✓ Dedicated success</li><li>✓ Custom integrations</li></ul></div></div>`, data: {}},
  testimonial: { html: `<div class="block-testimonial"><div class="testimonial-card"><div class="testimonial-text">"OmniDome reduced our churn by 23% in the first quarter. The AI predictions are incredibly accurate."</div><div class="testimonial-author">— Thabo Mokoena, CFO</div><div class="testimonial-role">FibreConnect SA</div></div></div>`, data: { quote: '""', author: '', role: '' }},
  html: { html: `<div class="block-html"><p style="text-align:center;color:#999;font-size:13px">Custom HTML — edit in properties</p></div>`, data: { code: '<!-- Your HTML here -->' }},
};

function addBlock(type) {
  const tpl = blockTemplates[type];
  if (!tpl) return;
  const block = { id: crypto.randomUUID(), type, html: tpl.html, data: {...tpl.data} };
  currentBlocks.push(block);
  renderCanvas();
  selectBlock(block.id);
  document.getElementById('emptyState').style.display = 'none';
}

function renderCanvas() {
  const canvas = document.getElementById('pageCanvas');
  const empty = document.getElementById('emptyState');
  canvas.innerHTML = '';
  if (currentBlocks.length === 0) {
    canvas.appendChild(empty);
    empty.style.display = 'flex';
    return;
  }
  empty.style.display = 'none';
  currentBlocks.forEach(block => {
    const wrapper = document.createElement('div');
    wrapper.className = 'page-block' + (selectedBlock === block.id ? ' selected' : '');
    wrapper.dataset.blockId = block.id;
    wrapper.onclick = (e) => { e.stopPropagation(); selectBlock(block.id); };
    wrapper.innerHTML = `
      <div class="page-block-controls">
        <div class="block-ctrl" onclick="moveBlock('${block.id}', -1)" title="Move up">↑</div>
        <div class="block-ctrl" onclick="moveBlock('${block.id}', 1)" title="Move down">↓</div>
        <div class="block-ctrl" onclick="duplicateBlock('${block.id}')" title="Duplicate">⧉</div>
        <div class="block-ctrl delete" onclick="deleteBlock('${block.id}')" title="Delete">✕</div>
      </div>
      ${block.html}
    `;
    canvas.appendChild(wrapper);
  });
}

function selectBlock(id) {
  selectedBlock = id;
  renderCanvas();
  const block = currentBlocks.find(b => b.id === id);
  if (block && block.type === 'html') {
    document.getElementById('propJsonLd').value = block.data.code || '';
  }
}

function moveBlock(id, dir) {
  const idx = currentBlocks.findIndex(b => b.id === id);
  if (idx < 0) return;
  const newIdx = idx + dir;
  if (newIdx < 0 || newIdx >= currentBlocks.length) return;
  [currentBlocks[idx], currentBlocks[newIdx]] = [currentBlocks[newIdx], currentBlocks[idx]];
  renderCanvas();
}

function duplicateBlock(id) {
  const block = currentBlocks.find(b => b.id === id);
  if (!block) return;
  const clone = {...block, id: crypto.randomUUID(), data: {...block.data}};
  const idx = currentBlocks.findIndex(b => b.id === id);
  currentBlocks.splice(idx + 1, 0, clone);
  renderCanvas();
}

function deleteBlock(id) {
  currentBlocks = currentBlocks.filter(b => b.id !== id);
  if (selectedBlock === id) selectedBlock = null;
  renderCanvas();
}

// ── SEO Scoring ──
function updateSeoScore() {
  const title = document.getElementById('propTitle').value;
  const slug = document.getElementById('propSlug').value;
  const seoTitle = document.getElementById('propSeoTitle').value;
  const seoDesc = document.getElementById('propSeoDesc').value;
  const keywords = document.getElementById('propSeoKeywords').value;

  let score = 0;
  const checks = { title: !!title, desc: !!seoDesc, keywords: !!keywords, h1: !!title, img: currentBlocks.some(b => b.html.includes('alt=')), slug: !!slug };

  Object.values(checks).forEach(v => { if (v) score += Math.round(100 / 6); });
  document.getElementById('seoScore').textContent = score;
  document.getElementById('seoLabel').textContent = score >= 80 ? 'Excellent' : score >= 50 ? 'Good' : score >= 20 ? 'Needs work' : 'Poor';
  document.getElementById('seoLabel').style.color = score >= 80 ? 'var(--green)' : score >= 50 ? 'var(--amber)' : 'var(--red)';
  Object.entries(checks).forEach(([k, v]) => {
    const el = document.getElementById('seoCheck' + k.charAt(0).toUpperCase() + k.slice(1));
    if (el) el.textContent = v ? '✓' : '○';
    if (el) el.style.color = v ? 'var(--green)' : 'var(--text3)';
  });
}

// Attach SEO listeners
['propTitle','propSlug','propSeoTitle','propSeoDesc','propSeoKeywords'].forEach(id => {
  document.getElementById(id).addEventListener('input', updateSeoScore);
});

// ── Page CRUD ──
async function savePage() {
  const payload = {
    title: document.getElementById('propTitle').value || 'Untitled',
    slug: document.getElementById('propSlug').value,
    content: { blocks: currentBlocks },
    seo_meta: {
      title: document.getElementById('propSeoTitle').value,
      description: document.getElementById('propSeoDesc').value,
      keywords: document.getElementById('propSeoKeywords').value.split(',').map(s => s.trim()),
      og_image: document.getElementById('propOgImage').value,
    }
  };
  if (!payload.slug) { alert('Please set a URL slug'); return; }
  try {
    const res = pageId
      ? await fetch(`/api/v1/portal/pages/${pageId}`, { method: 'PUT', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(payload) })
      : await fetch('/api/v1/portal/pages', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({...payload, page_type: 'landing'}) });
    const data = await res.json();
    pageId = data.id;
    document.getElementById('canvasInfo').textContent = `Saved: ${payload.title}`;
    if (!pageId) alert('Page saved!');
  } catch (e) { alert('Failed to save: ' + e.message); }
}

async function publishPage() {
  if (!pageId) { await savePage(); }
  if (!pageId) return;
  await fetch(`/api/v1/portal/pages/${pageId}/publish`, { method: 'POST' });
  alert('Published! URL: /portal/' + document.getElementById('propSlug').value);
}

function previewPage() { if (pageId) window.open('/portal/' + document.getElementById('propSlug').value, '_blank'); }
function newPage() { pageId = null; currentBlocks = []; selectedBlock = null; renderCanvas(); document.getElementById('propTitle').value = ''; updateSeoScore(); }
function setDevice(d) { document.querySelectorAll('.device-btn').forEach(b => b.classList.remove('active')); event.target.classList.add('active'); }
function loadPage(id) { if (id) { pageId = id; /* fetch & render */ } }
function updatePageMeta() { updateSeoScore(); }

// Init
renderCanvas();
</script>
</body>
</html>
"""


@router.get("/builder", response_class=HTMLResponse)
async def builder_ux():
    """Serve the Portal Builder SPA."""
    return BUILDER_HTML


@router.get("/builder/health")
async def builder_health():
    return {"status": "ok", "component": "portal-builder-ux"}
