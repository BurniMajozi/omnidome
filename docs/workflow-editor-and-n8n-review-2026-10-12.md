# Workflow editor fixes and n8n reference review

## Result

The native workflow editor now has visible **Delete selected**, **Delete step** and **Disconnect** actions. Delete / Backspace also removes selected items. Removing a step removes its incident connections. Edges can be reconnected by dragging their handles; dropping a handle without reconnecting removes the connection. Undo and redo restore graph edits. Nodes can be duplicated, arranged, dragged and selected in groups. Zoom controls and a pannable minimap remain available.

A step settings panel edits names, agent instructions, the real `draft_only` mode, owner notifications, conditions, internal API methods/paths and transform values. True/false branches have editable labels. Advanced JSON remains optional, and the full JSON editor has an explicit Apply JSON to graph action. Unsupported loops, duplicate connections, extra trigger nodes and parallel paths are prevented during connection editing. The graph remains a sequential runner with condition branches, not a full n8n execution engine.

## Backend corrections

The designer previously knew portal and billing events but excluded Sales events that are now published by the Sales service. The editor also lacked billing events in its static picker. Both now use the backend capability catalogue containing 19 verified source-published event types and seven runner step types. Sales, billing and other existing specialist agents are available to the draft designer.

An unimplemented event is retained in an inactive draft with an explicit publisher warning. It is no longer silently discarded. Activation refuses an unknown publisher, missing steps, dangling or duplicate connections, disconnected nodes, cycles, unsupported node types, incomplete conditions and agent steps without instructions. To use manual execution for an event without a publisher, clear the event and activate the valid graph. Publishers for payroll, VAT and ISP invoice lifecycle events have not been invented or added in this change.

Workflow designer conversations are now saved privately per tenant and user in PostgreSQL. The Saved design chats menu reopens the history and latest draft. Follow-ups use stored history rather than trusting a supplied replacement history. Reopening produces an unsaved draft; nothing is automatically activated. Other users and tenants receive 404 when trying to read or continue the conversation. Earlier designer history lived only in React state and cannot be reconstructed retroactively. The scoped owner workflow-conversation check returned no historical exchange to diagnose.

## What the repository provides

[Zie619/n8n-workflows](https://github.com/Zie619/n8n-workflows) is a searchable workflow-template collection and documentation/browser application. Its [Python API](https://github.com/Zie619/n8n-workflows/blob/main/api_server.py) uses FastAPI, with workflow search backed by SQLite. It is useful for discovering automation patterns, trigger categories and integration examples. It is not the n8n visual editor or a Python replacement for the n8n runner.

The collection has an [MIT licence](https://github.com/Zie619/n8n-workflows/blob/main/LICENSE). The actual [n8n code has a different licence](https://github.com/n8n-io/n8n/blob/master/LICENSE.md); copying its editor or embedding its runtime would be a separate decision. No external repository code or templates were copied in this release.

No extra hosting is needed for these fixes. Keep the current React Flow frontend and Python engine. A future template importer should identify supported node types, translate expressions and credentials, and report unsupported integrations before creating an inactive draft. Downloading thousands of n8n JSON workflows would not make their integrations executable in OmniDome.

The reconnect/delete behaviour follows the [official React Flow example](https://reactflow.dev/examples/edges/delete-edge-on-drop) and uses the [documented React Flow controls](https://reactflow.dev/api-reference/react-flow).

## Validation

Source TypeScript check passed. 47 PostgreSQL and Python checks passed covering the event catalogue, activation validation, designer graph validation, private conversation persistence, forbidden cross-user access and workflow continuation. Existing workflow execution and human approval behaviour remain covered by continuation tests. No real customer messages, payments or production workflows were created during checks.

Local web and orchestrator deployment completed. Rollback tags are `omnidome-chat-web:before-20261012184724` and `omnidome-chat-agent-orchestrator:before-20261012184724`. Live signed checks confirmed 19 capability events, seven node types, the private design-chat list endpoint and editor HTTP 200. Existing workflow attachment/approval checks, old agent conversations, budgets and billing-wallet reads passed after activation. Browser interaction verification remains unavailable after the earlier browser automation rejection, so drag/delete/reconnect interactions have not been exercised in a real browser.

The separately requested Platform Owner model console is deployed; its [release record](platform-model-console-2026-10-12.md) describes three slots and staged plan routing.

Final checks confirmed the deployed JavaScript bundle contains the delete controls, the platform watchdog is active, and live RAG recall still returns three company-memory entries and three knowledge results without an error note. No Ubuntu restart was needed. Changes remain in the shared working tree; no broad commit or push was made while other platform work is present.
