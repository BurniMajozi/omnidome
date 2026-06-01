"""
OmniDome — Communication Hub UIX
Unified interface: Email, Chat, Tasks, To-Do, Approvals, Projects — all in one view.

Design principles:
- Single-page tabbed interface (no page navigation)
- Real-time updates via SSE/polling
- OmniDome dark theme (slate/zinc palette)
- Responsive: sidebar collapses on mobile
- Keyboard shortcuts for power users
"""

import os
from fastapi import FastAPI
from fastapi.responses import HTMLResponse

# This is the served HTML for the Communication Hub
# In production, this would be built as a Next.js page
# For now, we serve it as a self-contained SPA

HUB_HTML = """
<!DOCTYPE html>
<html lang="en" class="dark">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>OmniDome — Communication Hub</title>
<style>
:root {
  --bg-primary: #0a0a0f;
  --bg-secondary: #12121a;
  --bg-tertiary: #1a1a26;
  --bg-hover: #22222f;
  --border: #2a2a3a;
  --border-light: #3a3a4a;
  --text-primary: #e4e4ef;
  --text-secondary: #9494a8;
  --text-muted: #646478;
  --accent: #6366f1;
  --accent-hover: #818cf8;
  --accent-subtle: rgba(99,102,241,0.15);
  --success: #22c55e;
  --success-subtle: rgba(34,197,94,0.12);
  --warning: #f59e0b;
  --warning-subtle: rgba(245,158,11,0.12);
  --danger: #ef4444;
  --danger-subtle: rgba(239,68,68,0.12);
  --info: #3b82f6;
}
* { margin:0; padding:0; box-sizing:border-box; }
body {
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
  background: var(--bg-primary);
  color: var(--text-primary);
  height: 100vh;
  overflow: hidden;
  display: flex;
}
button { cursor: pointer; border: none; background: none; color: inherit; font: inherit; }
input, textarea { font: inherit; }

/* ── Layout ── */
.app-shell { display: flex; width: 100vw; height: 100vh; }

/* Sidebar */
.sidebar {
  width: 260px; min-width: 260px;
  background: var(--bg-secondary);
  border-right: 1px solid var(--border);
  display: flex; flex-direction: column;
  transition: transform 0.2s;
}
.sidebar.collapsed { transform: translateX(-260px); width: 0; min-width: 0; }

.logo {
  padding: 20px 20px 16px;
  border-bottom: 1px solid var(--border);
  display: flex; align-items: center; gap: 10px;
}
.logo-icon {
  width: 32px; height: 32px; border-radius: 8px;
  background: var(--accent);
  display: flex; align-items: center; justify-content: center;
  font-weight: 800; font-size: 14px; color: white;
}
.logo-text { font-size: 16px; font-weight: 700; letter-spacing: -0.3px; }
.logo-sub { font-size: 10px; color: var(--text-muted); margin-top: 1px; }

.nav-section { padding: 12px 12px 0; }
.nav-label { font-size: 10px; text-transform: uppercase; letter-spacing: 1.2px; color: var(--text-muted); padding: 8px 8px 6px; font-weight: 600; }

.nav-item {
  display: flex; align-items: center; gap: 10px;
  padding: 8px 10px; border-radius: 8px; cursor: pointer;
  transition: all 0.15s; font-size: 13.5px; font-weight: 500;
  color: var(--text-secondary); position: relative;
}
.nav-item:hover { background: var(--bg-hover); color: var(--text-primary); }
.nav-item.active { background: var(--accent-subtle); color: var(--accent); }
.nav-item .badge {
  margin-left: auto; background: var(--accent); color: white;
  font-size: 10px; padding: 2px 6px; border-radius: 10px; font-weight: 600;
}
.nav-item .badge.danger { background: var(--danger); }
.nav-item .badge.warning { background: var(--warning); color: #000; }
.nav-icon { width: 18px; height: 18px; opacity: 0.7; }
.nav-item.active .nav-icon { opacity: 1; }

.channel-list { flex: 1; overflow-y: auto; padding: 8px 12px; }
.channel-item {
  display: flex; align-items: center; gap: 8px;
  padding: 6px 10px; border-radius: 6px; cursor: pointer;
  font-size: 13px; color: var(--text-secondary);
}
.channel-item:hover { background: var(--bg-hover); color: var(--text-primary); }
.channel-dot { width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; }
.channel-dot.unread { background: var(--accent); }
.channel-dot.muted { background: var(--text-muted); }
.channel-hash { color: var(--text-muted); font-size: 14px; margin-right: 2px; }

.sidebar-footer {
  padding: 12px; border-top: 1px solid var(--border);
  display: flex; align-items: center; gap: 10px;
}
.user-avatar {
  width: 32px; height: 32px; border-radius: 50%;
  background: var(--accent);
  display: flex; align-items: center; justify-content: center;
  font-size: 12px; font-weight: 700; color: white;
}
.user-name { font-size: 13px; font-weight: 500; }
.user-status { font-size: 11px; color: var(--text-muted); }
.status-dot { width: 7px; height: 7px; border-radius: 50%; background: var(--success); display: inline-block; margin-right: 4px; }

/* Main content */
.main-content { flex: 1; display: flex; flex-direction: column; overflow: hidden; }

/* ── Top Bar ── */
.top-bar {
  padding: 12px 24px;
  border-bottom: 1px solid var(--border);
  display: flex; align-items: center; gap: 16px;
  background: var(--bg-secondary);
}
.tab-group { display: flex; gap: 2px; }
.tab-btn {
  padding: 7px 16px; border-radius: 8px;
  font-size: 13px; font-weight: 500;
  color: var(--text-secondary);
  transition: all 0.15s;
  position: relative;
}
.tab-btn:hover { background: var(--bg-hover); color: var(--text-primary); }
.tab-btn.active { background: var(--accent-subtle); color: var(--accent); }
.tab-btn .count {
  position: absolute; top: 2px; right: 4px;
  font-size: 9px; background: var(--danger); color: white;
  border-radius: 8px; padding: 1px 4px; min-width: 14px; text-align: center;
}
.top-bar-right { margin-left: auto; display: flex; align-items: center; gap: 8px; }
.search-input {
  background: var(--bg-tertiary);
  border: 1px solid var(--border);
  border-radius: 8px; padding: 7px 12px 7px 32px;
  font-size: 13px; color: var(--text-primary);
  width: 240px; outline: none;
  transition: border-color 0.15s;
}
.search-input:focus { border-color: var(--accent); }
.btn-icon {
  width: 34px; height: 34px; border-radius: 8px;
  display: flex; align-items: center; justify-content: center;
  color: var(--text-secondary);
}
.btn-icon:hover { background: var(--bg-hover); color: var(--text-primary); }
.btn-primary {
  background: var(--accent); color: white;
  padding: 7px 16px; border-radius: 8px;
  font-size: 13px; font-weight: 600;
  transition: background 0.15s;
}
.btn-primary:hover { background: var(--accent-hover); }

/* Tab content */
.tab-content { flex: 1; overflow-y: auto; padding: 24px; }
.tab-pane { display: none; }
.tab-pane.active { display: block; }

/* ── Chat / Messages ── */
.chat-container { display: flex; flex-direction: column; height: calc(100vh - 120px); }
.messages { flex: 1; overflow-y: auto; padding: 0 8px; }
.message-group {
  display: flex; gap: 12px; padding: 12px 8px;
  border-radius: 8px; transition: background 0.1s;
}
.message-group:hover { background: var(--bg-secondary); }
.msg-avatar {
  width: 36px; height: 36px; border-radius: 50%; flex-shrink: 0;
  display: flex; align-items: center; justify-content: center;
  font-size: 13px; font-weight: 700; color: white;
}
.msg-header { display: flex; align-items: baseline; gap: 8px; margin-bottom: 4px; }
.msg-author { font-size: 13.5px; font-weight: 600; }
.msg-time { font-size: 11px; color: var(--text-muted); }
.msg-content { font-size: 13.5px; line-height: 1.55; color: var(--text-secondary); }
.msg-content a { color: var(--accent); text-decoration: none; }
.msg-content a:hover { text-decoration: underline; }
.msg-reactions { display: flex; gap: 6px; margin-top: 6px; }
.reaction {
  display: flex; align-items: center; gap: 4px;
  padding: 3px 8px; border-radius: 12px;
  font-size: 11px; background: var(--bg-tertiary);
  border: 1px solid var(--border);
}

.message-composer {
  padding: 16px; border-top: 1px solid var(--border);
  background: var(--bg-secondary);
}
.composer-box {
  background: var(--bg-tertiary);
  border: 1px solid var(--border);
  border-radius: 12px; padding: 12px;
}
.composer-box textarea {
  width: 100%; background: none; border: none; outline: none;
  color: var(--text-primary); font-size: 13.5px;
  resize: none; min-height: 60px; max-height: 150px;
}
.composer-actions {
  display: flex; align-items: center; justify-content: space-between;
  margin-top: 8px; padding-top: 8px; border-top: 1px solid var(--border);
}
.composer-tools { display: flex; gap: 4px; }
.composer-tools button {
  width: 30px; height: 30px; border-radius: 6px;
  display: flex; align-items: center; justify-content: center;
  color: var(--text-muted); font-size: 16px;
}
.composer-tools button:hover { background: var(--bg-hover); color: var(--text-secondary); }

/* ── Tasks / Kanban ── */
.kanban { display: flex; gap: 16px; height: calc(100vh - 120px); overflow-x: auto; }
.kanban-col {
  min-width: 280px; max-width: 320px; flex: 1;
  background: var(--bg-secondary); border-radius: 12px;
  border: 1px solid var(--border);
  display: flex; flex-direction: column;
}
.kanban-col-header {
  padding: 14px 16px; border-bottom: 1px solid var(--border);
  display: flex; align-items: center; justify-content: space-between;
}
.kanban-col-title { font-size: 13px; font-weight: 600; display: flex; align-items: center; gap: 8px; }
.col-dot { width: 8px; height: 8px; border-radius: 50%; }
.col-dot.todo { background: var(--text-muted); }
.col-dot.progress { background: var(--warning); }
.col-dot.review { background: var(--info); }
.col-dot.done { background: var(--success); }
.kanban-col-count { font-size: 11px; color: var(--text-muted); background: var(--bg-tertiary); padding: 2px 8px; border-radius: 10px; }
.kanban-items { flex: 1; overflow-y: auto; padding: 10px; display: flex; flex-direction: column; gap: 8px; }

.task-card {
  background: var(--bg-tertiary);
  border: 1px solid var(--border);
  border-radius: 10px; padding: 12px;
  cursor: pointer; transition: all 0.15s;
}
.task-card:hover { border-color: var(--accent); box-shadow: 0 0 0 1px var(--accent-subtle); }
.task-card-title { font-size: 13.5px; font-weight: 500; margin-bottom: 6px; }
.task-card-desc { font-size: 12px; color: var(--text-muted); line-height: 1.4; margin-bottom: 10px; }
.task-card-footer { display: flex; align-items: center; justify-content: space-between; }
.task-priority {
  font-size: 10px; padding: 2px 7px; border-radius: 6px; font-weight: 600; text-transform: uppercase;
}
.task-priority.high { background: var(--danger-subtle); color: var(--danger); }
.task-priority.medium { background: var(--warning-subtle); color: var(--warning); }
.task-priority.low { background: var(--success-subtle); color: var(--success); }
.task-due { font-size: 11px; color: var(--text-muted); }

/* ── Email ── */
.email-layout { display: flex; height: calc(100vh - 120px); }
.email-sidebar { width: 200px; border-right: 1px solid var(--border); padding: 16px; }
.email-folder {
  display: flex; align-items: center; gap: 8px;
  padding: 7px 10px; border-radius: 6px; cursor: pointer;
  font-size: 13px; color: var(--text-secondary);
}
.email-folder:hover, .email-folder.active { background: var(--bg-hover); color: var(--text-primary); }
.email-folder .count { margin-left: auto; font-size: 11px; color: var(--text-muted); }
.email-list { width: 320px; border-right: 1px solid var(--border); overflow-y: auto; }
.email-item {
  padding: 14px 16px; border-bottom: 1px solid var(--border);
  cursor: pointer; transition: background 0.1s;
}
.email-item:hover { background: var(--bg-secondary); }
.email-item.unread { border-left: 3px solid var(--accent); }
.email-from { font-size: 13.5px; font-weight: 600; margin-bottom: 3px; }
.email-subject { font-size: 13px; margin-bottom: 3px; }
.email-preview { font-size: 12px; color: var(--text-muted); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.email-meta { display: flex; justify-content: space-between; margin-top: 6px; }
.email-time { font-size: 11px; color: var(--text-muted); }
.email-body { flex: 1; padding: 24px; overflow-y: auto; }
.email-body-header { margin-bottom: 20px; padding-bottom: 16px; border-bottom: 1px solid var(--border); }
.email-body-title { font-size: 18px; font-weight: 600; margin-bottom: 8px; }
.email-body-meta { font-size: 12px; color: var(--text-muted); }
.email-body-content { font-size: 14px; line-height: 1.7; color: var(--text-secondary); }

/* ── Approvals ── */
.approval-list { display: flex; flex-direction: column; gap: 12px; }
.approval-card {
  background: var(--bg-secondary); border: 1px solid var(--border);
  border-radius: 12px; padding: 18px; transition: all 0.15s;
}
.approval-card:hover { border-color: var(--accent); }
.approval-header { display: flex; justify-content: space-between; align-items: start; margin-bottom: 10px; }
.approval-title { font-size: 15px; font-weight: 600; }
.approval-meta { font-size: 12px; color: var(--text-muted); margin-top: 3px; }
.approval-status {
  font-size: 11px; padding: 3px 10px; border-radius: 8px; font-weight: 600; text-transform: uppercase;
}
.approval-status.pending { background: var(--warning-subtle); color: var(--warning); }
.approval-status.approved { background: var(--success-subtle); color: var(--success); }
.approval-status.rejected { background: var(--danger-subtle); color: var(--danger); }
.approval-desc { font-size: 13px; color: var(--text-secondary); line-height: 1.5; margin-bottom: 14px; }
.approval-actions { display: flex; gap: 8px; }
.btn-approve { background: var(--success-subtle); color: var(--success); padding: 6px 14px; border-radius: 6px; font-size: 12px; font-weight: 600; }
.btn-approve:hover { background: var(--success); color: #000; }
.btn-reject { background: var(--danger-subtle); color: var(--danger); padding: 6px 14px; border-radius: 6px; font-size: 12px; font-weight: 600; }
.btn-reject:hover { background: var(--danger); color: #fff; }

/* ── Projects ── */
.project-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 16px; }
.project-card {
  background: var(--bg-secondary); border: 1px solid var(--border);
  border-radius: 12px; padding: 18px; transition: all 0.15s;
}
.project-card:hover { border-color: var(--accent); transform: translateY(-2px); }
.project-icon { width: 40px; height: 40px; border-radius: 10px; display: flex; align-items: center; justify-content: center; font-size: 18px; margin-bottom: 12px; }
.project-name { font-size: 15px; font-weight: 600; margin-bottom: 6px; }
.project-desc { font-size: 12px; color: var(--text-muted); line-height: 1.4; margin-bottom: 12px; }
.project-progress { height: 4px; background: var(--bg-tertiary); border-radius: 2px; overflow: hidden; margin-bottom: 8px; }
.project-progress-bar { height: 100%; border-radius: 2px; background: var(--accent); }
.project-stats { display: flex; justify-content: space-between; font-size: 11px; color: var(--text-muted); }

/* ── To-Do List ── */
.todo-list { display: flex; flex-direction: column; gap: 4px; max-width: 600px; }
.todo-item {
  display: flex; align-items: center; gap: 12px;
  padding: 10px 14px; border-radius: 8px;
  transition: background 0.1s;
}
.todo-item:hover { background: var(--bg-secondary); }
.todo-check {
  width: 20px; height: 20px; border-radius: 6px;
  border: 2px solid var(--border-light);
  display: flex; align-items: center; justify-content: center;
  flex-shrink: 0; transition: all 0.15s;
}
.todo-check.checked { background: var(--success); border-color: var(--success); color: white; font-size: 11px; }
.todo-text { font-size: 13.5px; flex: 1; }
.todo-text.done { text-decoration: line-through; color: var(--text-muted); }
.todo-tag {
  font-size: 10px; padding: 2px 7px; border-radius: 5px;
  background: var(--bg-tertiary); color: var(--text-secondary);
}
.todo-add { display: flex; gap: 8px; margin-top: 16px; }
.todo-input {
  flex: 1; background: var(--bg-secondary); border: 1px solid var(--border);
  border-radius: 8px; padding: 9px 14px; color: var(--text-primary);
  font-size: 13.5px; outline: none;
}
.todo-input:focus { border-color: var(--accent); }

/* ── Scrollbar ── */
::-webkit-scrollbar { width: 6px; }
::-webkit-scrollbar-track { background: transparent; }
::-webkit-scrollbar-thumb { background: var(--border); border-radius: 3px; }

/* ── Responsive ── */
@media(max-width: 768px) {
  .sidebar { position: absolute; z-index: 100; height: 100vh; }
  .sidebar.collapsed { transform: translateX(-260px); }
  .top-bar { padding: 10px 12px; }
  .tab-content { padding: 16px; }
  .search-input { display: none; }
}
</style>
</head>
<body>
<div class="app-shell">
  <!-- Sidebar -->
  <aside class="sidebar" id="sidebar">
    <div class="logo">
      <div class="logo-icon">O</div>
      <div>
        <div class="logo-text">OmniDome</div>
        <div class="logo-sub">Communication Hub</div>
      </div>
    </div>
    <nav class="nav-section">
      <div class="nav-label">Workspace</div>
      <div class="nav-item active" data-tab="chat">
        <span class="nav-icon">💬</span> Chat
        <span class="badge">3</span>
      </div>
      <div class="nav-item" data-tab="tasks">
        <span class="nav-icon">📋</span> Tasks
        <span class="badge warning">7</span>
      </div>
      <div class="nav-item" data-tab="todo">
        <span class="nav-icon">✅</span> To-Do
      </div>
      <div class="nav-item" data-tab="approvals">
        <span class="nav-icon">🔔</span> Approvals
        <span class="badge danger">2</span>
      </div>
      <div class="nav-item" data-tab="email">
        <span class="nav-icon">📧</span> Email
        <span class="badge">12</span>
      </div>
      <div class="nav-item" data-tab="projects">
        <span class="nav-icon">📁</span> Projects
      </div>
    </nav>
    <div class="nav-section" style="margin-top:8px">
      <div class="nav-label">Channels</div>
      <div class="channel-list">
        <div class="channel-item"><span class="channel-hash">#</span> general</div>
        <div class="channel-item"><span class="channel-hash">#</span> fibre-ops</div>
        <div class="channel-item"><span class="channel-hash">#</span> retention-alerts</div>
        <div class="channel-item"><span class="channel-hash">#</span> noc</div>
        <div class="channel-item"><span class="channel-hash">#</span> sales-team</div>
      </div>
    </div>
    <div class="sidebar-footer">
      <div class="user-avatar">BM</div>
      <div>
        <div class="user-name">Bene Majozi</div>
        <div class="user-status"><span class="status-dot"></span> Online</div>
      </div>
    </div>
  </aside>

  <!-- Main Content -->
  <main class="main-content">
    <!-- Top Bar -->
    <div class="top-bar">
      <button class="btn-icon" onclick="toggleSidebar()">☰</button>
      <div class="tab-group">
        <button class="tab-btn active" data-tab="chat">💬 Chat <span class="count">3</span></button>
        <button class="tab-btn" data-tab="tasks">📋 Tasks <span class="count">7</span></button>
        <button class="tab-btn" data-tab="todo">✅ To-Do</button>
        <button class="tab-btn" data-tab="approvals">🔔 Approvals <span class="count">2</span></button>
        <button class="tab-btn" data-tab="email">📧 Email <span class="count">12</span></button>
        <button class="tab-btn" data-tab="projects">📁 Projects</button>
      </div>
      <div class="top-bar-right">
        <input type="text" class="search-input" placeholder="⌘ K — Search...">
        <button class="btn-icon" onclick="openNewTask()">➕</button>
        <button class="btn-primary" onclick="openNewTask()">New Task</button>
      </div>
    </div>

    <!-- TAB: Chat -->
    <div class="tab-content">
      <div class="tab-pane active" id="tab-chat">
        <div class="chat-container">
          <div class="messages" id="chat-messages">
            <div class="message-group">
              <div class="msg-avatar" style="background:#6366f1">SM</div>
              <div style="flex:1">
                <div class="msg-header"><span class="msg-author">Sipho Mokoena</span><span class="msg-time">10:42 AM</span></div>
                <div class="msg-content">Fibre cut on Vumatel link in JHB North. NOC is on it — ETA 2h. I've escalated to retention for affected customers in the area.</div>
                <div class="msg-reactions"><span class="reaction">👍 3</span><span class="reaction">🚨 1</span></div>
              </div>
            </div>
            <div class="message-group">
              <div class="msg-avatar" style="background:#22c55e">LN</div>
              <div style="flex:1">
                <div class="msg-header"><span class="msg-author">Lerato Ndlovu</span><span class="msg-time">10:45 AM</span></div>
                <div class="msg-content">Retention batch is ready — 47 at-risk customers identified. Sending win-back offers via email campaign now. <a href="#">View campaign →</a></div>
                <div class="msg-reactions"><span class="reaction">✅ 2</span></div>
              </div>
            </div>
            <div class="message-group">
              <div class="msg-avatar" style="background:#f59e0b">JP</div>
              <div style="flex:1">
                <div class="msg-header"><span class="msg-author">Johan Pretorius</span><span class="msg-time">10:51 AM</span></div>
                <div class="msg-content">New deal closed — Enterprise client, R15k/mo, 24mo contract. Provisioning triggered. Can someone from NOC confirm coverage for 12 Sandton Dr?</div>
              </div>
            </div>
            <div class="message-group">
              <div class="msg-avatar" style="background:#ef4444">KM</div>
              <div style="flex:1">
                <div class="msg-header"><span class="msg-author">Khosi Molefe</span><span class="msg-time">10:58 AM</span></div>
                <div class="msg-content">Coverage confirmed for 12 Sandton Dr — Vumatel available, 500Mbps profile. <strong>@Johan</strong> I've created the provisioning ticket.</div>
                <div class="msg-reactions"><span class="reaction">🎉 4</span></div>
              </div>
            </div>
          </div>
          <div class="message-composer">
            <div class="composer-box">
              <textarea placeholder="Message #general... Use @ to mention, / for commands"></textarea>
              <div class="composer-actions">
                <div class="composer-tools">
                  <button title="Attach">📎</button>
                  <button title="Emoji">😊</button>
                  <button title="Mention">@</button>
                  <button title="Code">{ }</button>
                </div>
                <button class="btn-primary" onclick="sendMessage()">Send ↵</button>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- TAB: Tasks (Kanban) -->
      <div class="tab-pane" id="tab-tasks">
        <div class="kanban">
          <div class="kanban-col">
            <div class="kanban-col-header">
              <div class="kanban-col-title"><span class="col-dot todo"></span> To Do</div>
              <span class="kanban-col-count">4</span>
            </div>
            <div class="kanban-items">
              <div class="task-card">
                <div class="task-card-title">Provision Vumatel link — Sandton</div>
                <div class="task-card-desc">New enterprise client, 500Mbps profile. Coverage confirmed.</div>
                <div class="task-card-footer"><span class="task-priority high">High</span><span class="task-due">Due today</span></div>
              </div>
              <div class="task-card">
                <div class="task-card-title">Update churn model Q2 data</div>
                <div class="task-card-desc">Retrain with latest 3-month retention data</div>
                <div class="task-card-footer"><span class="task-priority medium">Medium</span><span class="task-due">Due Fri</span></div>
              </div>
              <div class="task-card">
                <div class="task-card-title">RICA batch verification</div>
                <div class="task-card-desc">47 pending verifications from last week</div>
                <div class="task-card-footer"><span class="task-priority medium">Medium</span><span class="task-due">Due Mon</span></div>
              </div>
            </div>
          </div>
          <div class="kanban-col">
            <div class="kanban-col-header">
              <div class="kanban-col-title"><span class="col-dot progress"></span> In Progress</div>
              <span class="kanban-col-count">2</span>
            </div>
            <div class="kanban-items">
              <div class="task-card">
                <div class="task-card-title">Fibre cut — JHB North restoration</div>
                <div class="task-card-desc">NOC on-site. Vumatel ETA 2h.</div>
                <div class="task-card-footer"><span class="task-priority high">High</span><span class="task-due">Due today</span></div>
              </div>
              <div class="task-card">
                <div class="task-card-title">Win-back email campaign</div>
                <div class="task-card-desc">47 at-risk customers. Sending offers now.</div>
                <div class="task-card-footer"><span class="task-priority high">High</span><span class="task-due">Due today</span></div>
              </div>
            </div>
          </div>
          <div class="kanban-col">
            <div class="kanban-col-header">
              <div class="kanban-col-title"><span class="col-dot review"></span> Review</div>
              <span class="kanban-col-count">1</span>
            </div>
            <div class="kanban-items">
              <div class="task-card">
                <div class="task-card-title">Enterprise deal approval — R15k/mo</div>
                <div class="task-card-desc">24mo contract. Needs manager sign-off.</div>
                <div class="task-card-footer"><span class="task-priority medium">Medium</span><span class="task-due">Due today</span></div>
              </div>
            </div>
          </div>
          <div class="kanban-col">
            <div class="kanban-col-header">
              <div class="kanban-col-title"><span class="col-dot done"></span> Done</div>
              <span class="kanban-col-count">5</span>
            </div>
            <div class="kanban-items">
              <div class="task-card" style="opacity:0.6">
                <div class="task-card-title">✅ Openserve API integration</div>
                <div class="task-card-desc">Adapter tested and deployed</div>
                <div class="task-card-footer"><span class="task-priority low">Low</span><span class="task-due">Completed</span></div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- TAB: To-Do -->
      <div class="tab-pane" id="tab-todo">
        <h2 style="font-size:18px;font-weight:600;margin-bottom:16px">Personal To-Do</h2>
        <div class="todo-list">
          <div class="todo-item"><div class="todo-check checked">✓</div><span class="todo-text done">Review Q2 churn report</span><span class="todo-tag">Analytics</span></div>
          <div class="todo-item"><div class="todo-check"></div><span class="todo-text">Approve enterprise deal — Sandton</span><span class="todo-tag">Sales</span></div>
          <div class="todo-item"><div class="todo-check"></div><span class="todo-text">Sign off on retention campaign budget</span><span class="todo-tag">Finance</span></div>
          <div class="todo-item"><div class="todo-check"></div><span class="todo-text">Update RICA verification SOP</span><span class="todo-tag">Compliance</span></div>
          <div class="todo-item"><div class="todo-check"></div><span class="todo-text">1:1 with NOC team lead</span><span class="todo-tag">HR</span></div>
          <div class="todo-item"><div class="todo-check"></div><span class="todo-text">Review IoT device health dashboard</span><span class="todo-tag">Network</span></div>
        </div>
        <div class="todo-add">
          <input type="text" class="todo-input" placeholder="Add a to-do...">
          <button class="btn-primary" onclick="addTodo()">Add</button>
        </div>
      </div>

      <!-- TAB: Approvals -->
      <div class="tab-pane" id="tab-approvals">
        <h2 style="font-size:18px;font-weight:600;margin-bottom:16px">Pending Approvals</h2>
        <div class="approval-list">
          <div class="approval-card">
            <div class="approval-header">
              <div>
                <div class="approval-title">Enterprise Deal — Sandton Properties</div>
                <div class="approval-meta">Submitted by Johan Pretorius · R15,000/mo · 24 months</div>
              </div>
              <span class="approval-status pending">Pending</span>
            </div>
            <div class="approval-desc">New enterprise fibre installation. Coverage confirmed on Vumatel. Client requires SLA guarantee and static IP allocation. Discount of 15% approved by sales manager.</div>
            <div class="approval-actions">
              <button class="btn-approve" onclick="decideApproval(this,'approved')">✓ Approve</button>
              <button class="btn-reject" onclick="decideApproval(this,'rejected')">✗ Reject</button>
            </div>
          </div>
          <div class="approval-card">
            <div class="approval-header">
              <div>
                <div class="approval-title">Retention Campaign Budget — Q2 Win-Back</div>
                <div class="approval-meta">Submitted by Lerato Ndlovu · R240,000 · 47 customers</div>
              </div>
              <span class="approval-status pending">Pending</span>
            </div>
            <div class="approval-desc">Proposed 20% discount campaign for 47 high-risk customers identified by churn model. Projected ROI: 312%. Revenue at risk: R1.2M over 6 months.</div>
            <div class="approval-actions">
              <button class="btn-approve" onclick="decideApproval(this,'approved')">✓ Approve</button>
              <button class="btn-reject" onclick="decideApproval(this,'rejected')">✗ Reject</button>
            </div>
          </div>
        </div>
      </div>

      <!-- TAB: Email -->
      <div class="tab-pane" id="tab-email">
        <div class="email-layout">
          <div class="email-sidebar">
            <button class="btn-primary" style="width:100%;margin-bottom:12px" onclick="composeEmail()">✉️ Compose</button>
            <div class="email-folder active">📥 Inbox <span class="count">12</span></div>
            <div class="email-folder">📤 Sent</div>
            <div class="email-folder">📝 Drafts <span class="count">3</span></div>
            <div class="email-folder">⭐ Starred</div>
            <div class="email-folder">🗑️ Trash</div>
            <div style="margin-top:16px">
              <div class="nav-label">Labels</div>
              <div class="email-folder" style="color:#ef4444">🔴 Urgent</div>
              <div class="email-folder" style="color:#f59e0b">🟡 Retention</div>
              <div class="email-folder" style="color:#22c55e">🟢 Provisioning</div>
            </div>
          </div>
          <div class="email-list">
            <div class="email-item unread">
              <div class="email-from">Vumatel NOC</div>
              <div class="email-subject">Fibre Cut Alert — JHB North Link Down</div>
              <div class="email-preview">Link ID: VMT-JHB-4472. Estimated restoration: 14:00. Affected: 23 customers...</div>
              <div class="email-meta"><span class="email-time">10:42 AM</span>🔴</div>
            </div>
            <div class="email-item unread">
              <div class="email-from">Retention System</div>
              <div class="email-subject">47 At-Risk Customers Identified — Action Required</div>
              <div class="email-preview">Churn model v2.3 flagged 47 customers with >80% risk score. Campaign ready...</div>
              <div class="email-meta"><span class="email-time">10:38 AM</span>🟡</div>
            </div>
            <div class="email-item">
              <div class="email-from">Johan Pretorius</div>
              <div class="email-subject">New Enterprise Deal — Needs Approval</div>
              <div class="email-preview">Sandton Properties, R15k/mo, 24mo. Coverage confirmed. Please approve...</div>
              <div class="email-meta"><span class="email-time">10:15 AM</span>🟢</div>
            </div>
            <div class="email-item">
              <div class="email-from">Cell C Wholesale</div>
              <div class="email-subject">Bandwidth pricing update — Q3 2026</div>
              <div class="email-preview">New wholesale rates effective 1 July. 15% reduction on 100Mbps+ profiles...</div>
              <div class="email-meta"><span class="email-time">Yesterday</span></div>
            </div>
          </div>
          <div class="email-body">
            <div class="email-body-header">
              <div class="email-body-title">Fibre Cut Alert — JHB North Link Down</div>
              <div class="email-body-meta">From: Vumatel NOC &lt;noc@vumatel.co.za&gt; · 10:42 AM</div>
            </div>
            <div class="email-body-content">
              <p>Dear Operations Team,</p>
              <p>We have detected a fibre cut on link <strong>VMT-JHB-4472</strong> in the Johannesburg North area.</p>
              <p><strong>Impact:</strong> 23 active customers affected<br>
              <strong>Estimated Restoration:</strong> 14:00 today<br>
              <strong>Cause:</strong> Third-party construction damage</p>
              <p>Field technicians have been dispatched. We will provide updates every 30 minutes.</p>
              <p>Regards,<br>Vumatel NOC Team</p>
            </div>
          </div>
        </div>
      </div>

      <!-- TAB: Projects -->
      <div class="tab-pane" id="tab-projects">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:20px">
          <h2 style="font-size:18px;font-weight:600">Projects</h2>
          <button class="btn-primary" onclick="createProject()">+ New Project</button>
        </div>
        <div class="project-grid">
          <div class="project-card">
            <div class="project-icon" style="background:rgba(99,102,241,0.15)">🌐</div>
            <div class="project-name">JHB North Fibre Restoration</div>
            <div class="project-desc">Emergency restoration of Vumatel link. 23 customers affected.</div>
            <div class="project-progress"><div class="project-progress-bar" style="width:35%"></div></div>
            <div class="project-stats"><span>35% complete</span><span>ETA 14:00</span></div>
          </div>
          <div class="project-card">
            <div class="project-icon" style="background:rgba(34,197,94,0.15)">📈</div>
            <div class="project-name">Q2 Retention Campaign</div>
            <div class="project-desc">Win-back campaign for 47 at-risk customers. R240k budget.</div>
            <div class="project-progress"><div class="project-progress-bar" style="width:60%;background:var(--success)"></div></div>
            <div class="project-stats"><span>60% complete</span><span>47 customers</span></div>
          </div>
          <div class="project-card">
            <div class="project-icon" style="background:rgba(245,158,11,0.15)">🏢</div>
            <div class="project-name">Sandton Enterprise Rollout</div>
            <div class="project-desc">New enterprise client onboarding. 500Mbps, 24mo contract.</div>
            <div class="project-progress"><div class="project-progress-bar" style="width:20%;background:var(--warning)"></div></div>
            <div class="project-stats"><span>20% complete</span><span>Coverage ✓</span></div>
          </div>
          <div class="project-card">
            <div class="project-icon" style="background:rgba(59,130,246,0.15)">🤖</div>
            <div class="project-name">Churn Model v2.3 Deployment</div>
            <div class="project-desc">ML model retraining with Q2 data. Accuracy target: 87%+</div>
            <div class="project-progress"><div class="project-progress-bar" style="width:80%;background:var(--info)"></div></div>
            <div class="project-stats"><span>80% complete</span><span>85.2% accuracy</span></div>
          </div>
          <div class="project-card">
            <div class="project-icon" style="background:rgba(239,68,68,0.15)">🔧</div>
            <div class="project-name">Openserve API Integration</div>
            <div class="project-desc">Automated provisioning adapter for Openserve fibre.</div>
            <div class="project-progress"><div class="project-progress-bar" style="width:100%;background:var(--success)"></div></div>
            <div class="project-stats"><span>✓ Complete</span><span>Deployed</span></div>
          </div>
          <div class="project-card" style="border-style:dashed;opacity:0.6;cursor:pointer" onclick="createProject()">
            <div style="display:flex;align-items:center;justify-content:center;height:100px;font-size:28px;color:var(--text-muted)">+</div>
            <div style="text-align:center;font-size:13px;color:var(--text-muted)">Create new project</div>
          </div>
        </div>
      </div>
    </div>
  </main>
</div>

<script>
// Tab switching
document.querySelectorAll('.tab-btn, .nav-item[data-tab]').forEach(el => {
  el.addEventListener('click', () => {
    const tab = el.dataset.tab;
    document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
    document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
    document.querySelectorAll('.tab-pane').forEach(p => p.classList.remove('active'));
    document.querySelector(`.tab-btn[data-tab="${tab}"]`)?.classList.add('active');
    document.querySelector(`.nav-item[data-tab="${tab}"]`)?.classList.add('active');
    document.getElementById(`tab-${tab}`)?.classList.add('active');
  });
});

function toggleSidebar() {
  document.getElementById('sidebar').classList.toggle('collapsed');
}

function sendMessage() {
  const textarea = document.querySelector('.composer-box textarea');
  if (!textarea.value.trim()) return;
  const msgs = document.getElementById('chat-messages');
  const div = document.createElement('div');
  div.className = 'message-group';
  div.innerHTML = `<div class="msg-avatar" style="background:#8b5cf6">BM</div><div style="flex:1"><div class="msg-header"><span class="msg-author">Bene Majozi</span><span class="msg-time">Just now</span></div><div class="msg-content">${textarea.value.replace(/</g,'&lt;')}</div></div>`;
  msgs.appendChild(div);
  msgs.scrollTop = msgs.scrollHeight;
  textarea.value = '';
}

function decideApproval(btn, decision) {
  const card = btn.closest('.approval-card');
  const status = card.querySelector('.approval-status');
  status.textContent = decision === 'approved' ? 'Approved' : 'Rejected';
  status.className = 'approval-status ' + decision;
  card.querySelector('.approval-actions').innerHTML = `<span style="font-size:12px;color:var(--text-muted)">${decision === 'approved' ? '✓ Approved' : '✗ Rejected'} by you</span>`;
}

function addTodo() {
  const input = document.querySelector('.todo-input');
  if (!input.value.trim()) return;
  const list = document.querySelector('.todo-list');
  const div = document.createElement('div');
  div.className = 'todo-item';
  div.innerHTML = `<div class="todo-check"></div><span class="todo-text">${input.value.replace(/</g,'&lt;')}</span>`;
  list.insertBefore(div, list.querySelector('.todo-add'));
  input.value = '';
}

function openNewTask() { document.querySelector('[data-tab="tasks"]').click(); }
function composeEmail() { document.querySelector('[data-tab="email"]').click(); }
function createProject() { alert('Create project modal — to be implemented'); }

// Keyboard shortcut
document.addEventListener('keydown', e => {
  if (e.metaKey && e.key === 'k') {
    e.preventDefault();
    document.querySelector('.search-input')?.focus();
  }
});
</script>
</body>
</html>
"""


@app.get("/hub", response_class=HTMLResponse)
async def communication_hub():
    """Serve the unified Communication Hub SPA."""
    return HUB_HTML


@app.get("/hub/health")
async def hub_health():
    return {"status": "ok", "component": "communication-hub-ux"}
