import { supabase } from './client'

export function subscribeToModuleData(
  moduleName: string,
  callback: (data: any) => void
) {
  const channel = supabase
    .channel(`module-data:${moduleName}`)
    .on(
      'postgres_changes',
      {
        event: '*',
        schema: 'public',
        table: 'module_data',
        filter: `module_name=eq.${moduleName}`,
      },
      (payload) => {
        callback(payload.new)
      }
    )
    .subscribe()
  return () => { supabase.removeChannel(channel) }
}

export function subscribeToMessages(
  channelId: string,
  callback: (message: any) => void
) {
  const channel = supabase
    .channel(`messages:${channelId}`)
    .on(
      'postgres_changes',
      { event: 'INSERT', schema: 'public', table: 'messages' },
      (payload) => callback(payload.new)
    )
    .subscribe()
  return () => { supabase.removeChannel(channel) }
}
