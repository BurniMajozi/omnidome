# OmniDome — Communication Hub UIX

> The unified communication interface. Everything in one tabbed view.

## Design Philosophy

The Communication Hub is the heart of OmniDome's internal operations. It combines 6 tools into a single seamless interface:

1. **Chat** — Slack-style real-time messaging with channels, threads, reactions
2. **Tasks** — Kanban board (To Do → In Progress → Review → Done)
3. **To-Do** — Personal quick-check list
4. **Approvals** — Pending approval requests with approve/reject actions
5. **Email** — Inbox with folders, labels, and reading pane
6. **Projects** — Card grid with progress bars and status

## Key UX Decisions

- **No page navigation** — everything is tabs within one view
- **Dark theme** — OmniDome slate/zinc palette (#0a0a0f bg)
- **Sidebar** — Quick nav for all modules + channel list
- **Keyboard shortcuts** — ⌘K for search
- **Real-time ready** — wired for SSE/polling integration
- **Responsive** — sidebar collapses on mobile

## Integrations to Add

| Integration | Where | Value |
|------------|-------|-------|
| AI Chat Assistant | Chat tab | Summarize threads, draft replies, extract tasks |
| Retention Alerts | Chat tab | Auto-post churn risk notifications |
| Provisioning Status | Tasks tab | Auto-create tasks from sales deals |
| Email ↔ Tasks | Email tab | Convert email to task with one click |
| Approval Workflows | Approvals tab | Delegate, escalate, audit trail |
| IoT Alerts | Chat tab | Device health notifications in NOC channel |
| Calendar/Schedule | Projects tab | Sprint planning, deadlines |
| CRM Context | All tabs | Customer 360 popup on @mentions |

## File Location

`services/communication/hub_ux.py` — self-contained SPA served at `GET /hub`

## Related Notes
- [[OmniDome — Communication Service]]
- [[OmniDome — Implementation Status]]
- [[OmniDome — Project Index]]
