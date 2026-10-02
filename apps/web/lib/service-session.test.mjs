import test from 'node:test'
import assert from 'node:assert/strict'
import { describeLoadable, tileLabel } from './service-state.ts'

test('401 offers session retry rather than claiming missing permissions', () => {
  const state = { state: 'denied', status: 401 }
  assert.equal(describeLoadable(state).title, 'Session not verified')
  assert.match(describeLoadable(state).detail, /Retry/)
  assert.equal(tileLabel(state), 'Session not verified')
})
test('403 continues to describe a permission denial', () => {
  assert.equal(describeLoadable({ state: 'denied', status: 403 }).title, 'Not permitted')
})
