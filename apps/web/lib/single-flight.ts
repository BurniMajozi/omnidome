/** Share concurrent work only; settled results are never cached here. */
export function singleFlight<K, V>() {
  const pending = new Map<K, Promise<V>>()
  return (key: K, work: () => Promise<V>): Promise<V> => {
    const existing = pending.get(key)
    if (existing) return existing
    const result = Promise.resolve().then(work)
    pending.set(key, result)
    const clear = () => { if (pending.get(key) === result) pending.delete(key) }
    result.then(clear, clear)
    return result
  }
}
