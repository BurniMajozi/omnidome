import test from 'node:test'
import assert from 'node:assert/strict'
import { singleFlight } from './single-flight.ts'

test('concurrent identity requests share one lookup without retaining results', async () => {
  const run = singleFlight()
  let calls = 0
  const work = async () => { calls++; await new Promise(r => setTimeout(r, 5)); return calls }
  assert.deepEqual(await Promise.all(Array.from({length: 16}, () => run('same-token', work))), Array(16).fill(1))
  assert.equal(await run('same-token', work), 2)
})

test('tokens remain isolated and a failed lookup is retried', async () => {
  const run = singleFlight()
  assert.deepEqual(await Promise.all([run('a', async () => 'A'), run('b', async () => 'B')]), ['A', 'B'])
  await assert.rejects(run('a', async () => { throw new Error('offline') }), /offline/)
  assert.equal(await run('a', async () => 'recovered'), 'recovered')
})
