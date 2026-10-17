import { test } from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { createRequire } from 'node:module'
const require = createRequire(new URL('../package.json', import.meta.url))
const ts = require('typescript')

function load(relative) {
  const source = readFileSync(new URL(relative, import.meta.url), 'utf8')
  const output = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 } }).outputText
  const module = { exports: {} }
  new Function('require', 'module', 'exports', output)(id => { throw new Error(`Unexpected dependency: ${id}`) }, module, module.exports)
  return module.exports
}

const d = load('./support-derive.ts')
const NOW = Date.parse('2026-10-16T12:00:00Z')

test('age labels are compact', () => {
  assert.equal(d.ageLabel('2026-10-16T11:59:40Z', NOW), 'now')
  assert.equal(d.ageLabel('2026-10-16T11:25:00Z', NOW), '35m')
  assert.equal(d.ageLabel('2026-10-16T05:00:00Z', NOW), '7h')
  assert.equal(d.ageLabel('2026-10-10T12:00:00Z', NOW), '6d')
  assert.equal(d.ageLabel(null, NOW), '—')
})

test('SLA badge reflects server state and due time', () => {
  assert.deepEqual(d.slaView('breached', '2026-10-16T09:00:00Z', NOW), { label: 'Overdue 3h', tone: 'bad' })
  assert.deepEqual(d.slaView('due_soon', '2026-10-16T13:00:00Z', NOW), { label: 'Due in 1h', tone: 'warn' })
  assert.deepEqual(d.slaView('ok', '2026-10-17T12:00:00Z', NOW), { label: 'Due in 24h', tone: 'ok' })
  assert.equal(d.slaView('met', '2026-10-17T12:00:00Z', NOW).label, 'SLA met')
  assert.equal(d.slaView('missed', '2026-10-15T12:00:00Z', NOW).tone, 'bad')
  assert.equal(d.slaView(null, null, NOW).label, 'No SLA')
})

test('quick views map to server filters', () => {
  assert.deepEqual(d.viewFilters('open'), { open_only: true })
  assert.deepEqual(d.viewFilters('mine'), { open_only: true, assigned: 'me' })
  assert.deepEqual(d.viewFilters('unassigned'), { open_only: true, assigned: 'unassigned' })
  assert.deepEqual(d.viewFilters('breached'), { sla: 'breached' })
  assert.deepEqual(d.viewFilters('closed'), { status: 'RESOLVED,CLOSED' })
  assert.deepEqual(d.viewFilters('all'), {})
})

test('only in-app deep links are followed', () => {
  assert.equal(d.safeInternalLink('/dashboard?section=billing'), '/dashboard?section=billing')
  assert.equal(d.safeInternalLink('/dashboard/home-dome'), '/dashboard/home-dome')
  assert.equal(d.safeInternalLink('https://evil.example/x'), null)
  assert.equal(d.safeInternalLink('//evil.example'), null)
  assert.equal(d.safeInternalLink('/dashboard/../admin'), null)
  assert.equal(d.safeInternalLink(null), null)
})

test('status actions: closed tickets can only be reopened, open ones can be resolved or closed', () => {
  assert.deepEqual(d.nextActions('CLOSED').map(a => a.status), ['OPEN'])
  assert.deepEqual(d.nextActions('RESOLVED').map(a => a.status), ['OPEN'])
  assert.deepEqual(d.nextActions('OPEN').map(a => a.status), ['IN_PROGRESS', 'ON_HOLD', 'RESOLVED', 'CLOSED'])
  assert.deepEqual(d.nextActions('IN_PROGRESS').map(a => a.status), ['ON_HOLD', 'RESOLVED', 'CLOSED'])
  assert.deepEqual(d.nextActions('ON_HOLD').map(a => a.status), ['IN_PROGRESS', 'RESOLVED', 'CLOSED'])
})

test('labels fall back to a readable form', () => {
  assert.equal(d.labelOf(d.SOURCE_LABELS, 'iot'), 'HomeDome')
  assert.equal(d.labelOf(d.SOURCE_LABELS, 'some_new_source'), 'Some new source')
  assert.equal(d.labelOf({}, null), '—')
})

// ── time dimension ──────────────────────────────────────────────────────────

const nameOf = (id) => ({ u1: 'Sipho', u2: 'Thandi' })[id] ?? 'Teammate'
const ev = (event_type, at, extra = {}) => ({
  id: `${event_type}-${at}`, event_type, actor_name: 'Sipho', actor_type: 'agent', from_value: null, to_value: null, note: null,
  visibility: 'internal', channel: null, data: {}, created_at: at, ...extra,
})

test('durations are compact and honest about missing data', () => {
  assert.equal(d.formatHours(null), '—')
  assert.equal(d.formatHours(0.25), '15m')
  assert.equal(d.formatHours(0.001), '1m')
  assert.equal(d.formatHours(3), '3h')
  assert.equal(d.formatHours(3.46), '3.5h')
  assert.equal(d.formatHours(72), '3d')
  assert.equal(d.formatPct(66.7), '67%')
  assert.equal(d.formatPct(null), '—')
})

test('each lifecycle event reads as a plain sentence with who, from and to', () => {
  assert.equal(d.describeEvent(ev('assigned', 'a', { to_value: 'u1' }), nameOf).title, 'Assigned to Sipho')
  assert.equal(d.describeEvent(ev('reassigned', 'a', { from_value: 'u1', to_value: 'u2' }), nameOf).title, 'Reassigned from Sipho to Thandi')
  assert.equal(d.describeEvent(ev('transferred', 'a', { from_value: 'support', to_value: 'technical' }), nameOf).title, 'Moved from the Support queue to Technical')
  const m = d.describeEvent(ev('modified', 'a', { from_value: 'NORMAL', to_value: 'HIGH', data: { field: 'priority' }, note: 'Home worker' }), nameOf)
  assert.equal(m.title, 'Priority changed from Normal to High')
  assert.equal(m.body, 'Home worker')
  assert.equal(d.describeEvent(ev('status_changed', 'a', { from_value: 'OPEN', to_value: 'IN_PROGRESS' }), nameOf).title, 'Status changed from Open to In progress')
  const note = d.describeEvent(ev('note_added', 'a', { note: 'Called the customer' }), nameOf)
  assert.deepEqual([note.title, note.body, note.internal, note.tone], ['Internal note', 'Called the customer', true, 'note'])
  assert.equal(d.describeEvent(ev('reply_sent', 'a', { note: 'On it' }), nameOf).tone, 'reply')
  assert.equal(d.describeEvent(ev('sla_breached', 'a', { actor_type: 'system' }), nameOf).who, 'System')
  assert.equal(d.describeEvent(ev('jev_applied', 'a', { actor_type: 'jev', to_value: 'queue' }), nameOf).who, 'Jev')
  assert.equal(d.describeEvent(ev('mystery', 'a'), nameOf).title, 'Mystery')
})

test('the requester notification says what happened and whether it could be sent', () => {
  const sent = d.describeEvent(ev('customer_notified', 'a', { actor_type: 'system', channel: 'email', data: { delivery: 'queued', trigger: 'assigned' } }), nameOf)
  assert.equal(sent.title, 'Requester told by email that it was picked up')
  const stuck = d.describeEvent(ev('customer_notified', 'a', { actor_type: 'system', channel: 'call', data: { delivery: 'no_outbound_path', trigger: 'resolved' } }), nameOf)
  assert.match(stuck.title, /not told .*phone has no way to send/)
})

test('a logged ticket is shown from its events, newest first, with repeats folded into one line', () => {
  const events = [
    ev('created', '2026-10-16T08:00:00Z', { actor_type: 'system', to_value: 'OPEN' }),
    ev('repeated', '2026-10-16T08:05:00Z', { actor_type: 'system' }), ev('repeated', '2026-10-16T08:06:00Z', { actor_type: 'system' }),
    ev('repeated', '2026-10-16T08:07:00Z', { actor_type: 'system' }),
    ev('assigned', '2026-10-16T09:00:00Z', { to_value: 'u1' }),
    ev('repeated', '2026-10-16T09:30:00Z', { actor_type: 'system' }),
  ]
  const timeline = [{ id: 't1', kind: 'event', author_type: 'system', message: 'Ticket opened from email.', is_private: true, created_at: '2026-10-16T08:00:00Z' }]
  const items = d.buildActivity(timeline, events, nameOf)
  assert.deepEqual(items.map((i) => i.title), [
    'The same problem happened again', 'Assigned to Sipho', 'The same problem happened again (3 times)', 'Ticket opened',
  ])
  assert.ok(items.every((i, n) => n === 0 || (items[n - 1].at ?? '') >= (i.at ?? '')))
})

test('an older ticket keeps its timeline rows and gains only the events the timeline never had', () => {
  const timeline = [
    { id: 't1', kind: 'comment', author_type: 'agent', message: 'Please reboot', is_private: false, created_at: '2026-10-10T10:00:00Z' },
    { id: 't2', kind: 'comment', author_type: 'agent', message: 'refund?', is_private: true, created_at: '2026-10-10T11:00:00Z' },
    { id: 't3', kind: 'assignment', author_type: 'agent', message: 'Assigned to a teammate.', is_private: true, created_at: '2026-10-10T12:00:00Z' },
  ]
  const events = [
    ev('created', '2026-10-10T09:00:00Z', { actor_type: 'system', data: { backfilled: true } }),
    ev('sla_breached', '2026-10-11T09:00:00Z', { actor_type: 'system' }),
    ev('assigned', '2026-10-10T12:00:00Z', { to_value: 'u1' }),
  ]
  const items = d.buildActivity(timeline, events, nameOf)
  assert.deepEqual(items.map((i) => i.title), ['Passed its deadline while still open', 'Assigned to a teammate.', 'Internal note', 'Reply'])
  assert.equal(items[2].internal, true)
  assert.equal(d.buildActivity(undefined, undefined, nameOf).length, 0)
})

test('handling facts show the time dimension and flag trouble', () => {
  const base = { hours_to_first_response: 1.5, assignment_count: 2, modification_count: 3, transfer_count: 1, reopen_count: 0, hours_to_resolve: null, overdue: false, stale: false }
  assert.deepEqual(d.handlingFacts(base), [
    { label: 'First response', value: '1.5h', tone: undefined }, { label: 'Assigned', value: '2×' }, { label: 'Modified', value: '3×' },
    { label: 'Transferred', value: '1×' },
  ])
  const late = d.handlingFacts({ ...base, hours_to_first_response: null, reopen_count: 1, hours_to_resolve: 30, overdue: true })
  assert.deepEqual(late.map((f) => f.label), ['First response', 'Assigned', 'Modified', 'Transferred', 'Reopened', 'Time to resolve', 'Deadline'])
  assert.equal(late[0].value, 'Not yet')
  assert.equal(late.at(-1).tone, 'bad')
  assert.equal(d.handlingFacts({ ...base, stale: true }).at(-1).value, 'Gone quiet')
})

test('Jev proposals are summarised for a person to accept', () => {
  assert.equal(d.proposalLabel({ queue: 'technical', priority: 'URGENT', category: 'BILLING' }, nameOf), 'Queue → Technical, Priority → Urgent, Category → Billing')
  assert.equal(d.proposalLabel({ status: 'ESCALATED' }, nameOf), 'Status → Escalated')
  assert.equal(d.proposalLabel({ assignee: 'u2', outcome: 'task' }, nameOf), 'Assign to Thandi, Also create: ticket and a task')
  assert.equal(d.proposalLabel({ flagged: true }, nameOf), '')
})

test('outcome and Jev-mode vocabularies match what the server accepts', () => {
  assert.deepEqual(Object.keys(d.OUTCOME_LABELS), ['ticket', 'task', 'escalation', 'schedule'])
  assert.deepEqual(Object.keys(d.JEV_MODE_LABELS), ['off', 'suggest', 'auto'])
  assert.deepEqual(d.NOTIFY_TRIGGERS.map((t) => t.key), ['notify_on_assigned', 'notify_on_modified', 'notify_on_note', 'notify_on_resolved'])
})
