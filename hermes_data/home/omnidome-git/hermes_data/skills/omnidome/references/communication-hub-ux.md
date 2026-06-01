# Communication Hub UIX — Design Notes

> The unified communication interface. Everything in one tabbed view. 2026-06-01.

## Design Philosophy

User rejected the first communication hub design. Feedback: "I don't like the communications dome UIX. The idea was everything in one tab. Email, chat, task, to-do, approvals, projects. This is where this system should shine."

## What Was Built

Single-page tabbed SPA with 6 tabs:

1. **Chat** — Slack-style messages, channels, threads, reactions, @mentions, composer
2. **Tasks** — Kanban board (To Do → In Progress → Review → Done), priority, due dates
3. **To-Do** — Personal quick-check list
4. **Approvals** — Pending requests with approve/reject actions
5. **Email** — Inbox with folders, labels, reading pane
6. **Projects** — Card grid with progress bars

## Key UX Decisions

- No page navigation — everything is tabs within one view
- Dark theme — OmniDome slate/zinc palette (#0a0a0f bg)
- Sidebar — Quick nav + channel list + user status
- Keyboard shortcuts — ⌘K for search
- Responsive — sidebar collapses on mobile

## Integrations Planned

- AI Chat Assistant in Chat tab (summarize, draft, extract tasks)
- Retention alerts auto-posting to chat
- Provisioning tasks from sales deals
- Email → Task conversion
- IoT alerts in NOC channel
- Calendar/schedule from chat

## File

`services/communication/hub_ux.py` — self-contained SPA at `GET /hub`
