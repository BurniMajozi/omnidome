// Browser-level notifications for finished agent runs ("where permitted"). The in-app toast and the header bell
// are the primary channels; this only adds an OS notification when the tab is not in front.

export function browserNotificationsSupported(): boolean {
  return typeof window !== "undefined" && "Notification" in window
}

/** Ask once, from a user gesture (sending a message). A denied or dismissed prompt is never repeated. */
export async function requestBrowserNotifications(): Promise<void> {
  if (!browserNotificationsSupported() || Notification.permission !== "default") return
  try { await Notification.requestPermission() } catch { /* some browsers throw outside a gesture */ }
}

export function showBrowserNotification(title: string, body: string, tag: string, onClick: () => void): void {
  if (!browserNotificationsSupported() || Notification.permission !== "granted") return
  try {
    const n = new Notification(title, { body, tag, icon: "/favicon.ico" })
    n.onclick = () => { window.focus(); onClick(); n.close() }
  } catch { /* e.g. insecure context: toast + bell still cover it */ }
}
