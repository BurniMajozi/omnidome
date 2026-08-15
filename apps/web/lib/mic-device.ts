// Shared microphone device resolution for the STT panel and the AG-UI voice
// input. Browsers expose "default"/"communications" pseudo-devices that on
// this hardware silently map to a muted mic array instead of the real input,
// so recording must resolve and request an explicit physical deviceId.

export const MIC_STORAGE_KEY = "omnidome.voiceAiPanel.microphoneDeviceId"
export const DEFAULT_MIC_ID = "default"
export const COMMUNICATIONS_MIC_ID = "communications"
export const PREFERRED_MIC_LABEL = "senary audio"

export function stripMicAliasPrefix(label: string) {
  return label
    .replace(/^(default|communications)\s*-\s*/i, "")
    .replace(/\s+/g, " ")
    .trim()
}

export function normalizeMicLabel(label: string) {
  return stripMicAliasPrefix(label).toLowerCase()
}

export function isBrowserPseudoMic(deviceId: string) {
  return deviceId === DEFAULT_MIC_ID || deviceId === COMMUNICATIONS_MIC_ID
}

export function findPreferredPhysicalMic(inputs: MediaDeviceInfo[]) {
  const physicalInputs = inputs.filter((device) => device.deviceId && !isBrowserPseudoMic(device.deviceId))
  return (
    physicalInputs.find((device) => normalizeMicLabel(device.label).includes(PREFERRED_MIC_LABEL)) ??
    physicalInputs.find((device) => {
      const defaultDevice = inputs.find((input) => input.deviceId === DEFAULT_MIC_ID)
      const defaultLabel = normalizeMicLabel(defaultDevice?.label || "")
      const deviceLabel = normalizeMicLabel(device.label)
      return Boolean(defaultLabel && deviceLabel && (deviceLabel === defaultLabel || defaultLabel.includes(deviceLabel)))
    }) ??
    null
  )
}

export function getSavedMicId(): string {
  try {
    return window.localStorage.getItem(MIC_STORAGE_KEY) || DEFAULT_MIC_ID
  } catch {
    return DEFAULT_MIC_ID
  }
}

export function saveMicId(deviceId: string) {
  try {
    window.localStorage.setItem(MIC_STORAGE_KEY, deviceId)
  } catch {
    // Ignore private browsing / blocked storage.
  }
}

/**
 * Resolves which physical microphone deviceId to request given a preferred
 * id (e.g. the user's saved choice). If that id is a browser pseudo-device
 * and no device labels are known yet, briefly opens the mic to unlock labels
 * so the heuristic can find the real physical input.
 */
export async function resolvePreferredMicId(requestedMicId: string): Promise<string> {
  if (!navigator.mediaDevices?.enumerateDevices) return requestedMicId

  let availableInputs = await navigator.mediaDevices.enumerateDevices()
    .then((devices) => devices.filter((device) => device.kind === "audioinput"))
    .catch(() => [] as MediaDeviceInfo[])
  let preferredMic = findPreferredPhysicalMic(availableInputs)

  if (isBrowserPseudoMic(requestedMicId) && !preferredMic && availableInputs.every((device) => !device.label)) {
    const permissionStream = await navigator.mediaDevices.getUserMedia({ audio: true })
    permissionStream.getTracks().forEach((track) => track.stop())
    availableInputs = await navigator.mediaDevices.enumerateDevices()
      .then((devices) => devices.filter((device) => device.kind === "audioinput"))
      .catch(() => [] as MediaDeviceInfo[])
    preferredMic = findPreferredPhysicalMic(availableInputs)
  }

  return requestedMicId && !isBrowserPseudoMic(requestedMicId)
    ? requestedMicId
    : preferredMic?.deviceId ?? DEFAULT_MIC_ID
}

export function micAudioConstraints(micId: string): MediaTrackConstraints {
  return isBrowserPseudoMic(micId)
    ? { autoGainControl: true, echoCancellation: true, noiseSuppression: true }
    : { autoGainControl: true, deviceId: { exact: micId }, echoCancellation: true, noiseSuppression: true }
}
