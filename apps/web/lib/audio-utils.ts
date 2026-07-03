/**
 * Convert a Blob (e.g. audio/webm from MediaRecorder) to a 16kHz mono WAV Blob.
 * Uses the browser's AudioContext to decode the codec-specific format, then
 * re-encodes as raw PCM WAV that every server-side audio library can read
 * without codec-specific fallbacks.
 *
 * Voicebox engine's librosa/soundfile can't read opus-in-webm directly
 * (PySoundFile fails, falls back to deprecated audioread, producing degraded
 * audio that causes Whisper to hallucinate instead of transcribing real speech).
 */
export async function toWav(blob: Blob, targetSampleRate = 16_000): Promise<Blob> {
  return (await toWavWithStats(blob, targetSampleRate)).wav
}

/**
 * Like toWav, but also reports signal stats so callers can detect a silent
 * recording (OS delivering a muted/wrong microphone) BEFORE uploading —
 * Whisper transcribes silence as hallucinated filler like "you".
 * rms is 0..1; anything below ~0.001 is effectively silence.
 */
export async function toWavWithStats(
  blob: Blob,
  targetSampleRate = 16_000,
): Promise<{ wav: Blob; rms: number; durationSeconds: number }> {
  const arrayBuffer = await blob.arrayBuffer()
  const audioCtx = new AudioContext({ sampleRate: targetSampleRate })

  let decoded: AudioBuffer
  try {
    decoded = await audioCtx.decodeAudioData(arrayBuffer)
  } finally {
    await audioCtx.close()
  }

  // Mix down to mono at the target sample rate (already resampled by AudioContext)
  const numSamples = decoded.length
  const pcm = new Float32Array(numSamples)
  for (let ch = 0; ch < decoded.numberOfChannels; ch++) {
    const data = decoded.getChannelData(ch)
    for (let i = 0; i < numSamples; i++) {
      pcm[i] += data[i] / decoded.numberOfChannels
    }
  }

  let sumSquares = 0
  for (let i = 0; i < numSamples; i++) sumSquares += pcm[i] * pcm[i]
  const rms = numSamples > 0 ? Math.sqrt(sumSquares / numSamples) : 0

  return { wav: encodeWav(pcm, targetSampleRate), rms, durationSeconds: decoded.duration }
}

/** Threshold below which a recording is treated as silent (no usable speech). */
export const SILENCE_RMS_THRESHOLD = 0.001

function encodeWav(samples: Float32Array, sampleRate: number): Blob {
  const numSamples = samples.length
  const bytesPerSample = 2 // 16-bit PCM
  const dataBytes = numSamples * bytesPerSample
  const buffer = new ArrayBuffer(44 + dataBytes)
  const view = new DataView(buffer)

  const write = (offset: number, value: number, size: 4 | 2) =>
    size === 4 ? view.setUint32(offset, value, true) : view.setUint16(offset, value, true)

  // RIFF header
  "RIFF".split("").forEach((c, i) => view.setUint8(i, c.charCodeAt(0)))
  write(4, 36 + dataBytes, 4)
  "WAVE".split("").forEach((c, i) => view.setUint8(8 + i, c.charCodeAt(0)))
  "fmt ".split("").forEach((c, i) => view.setUint8(12 + i, c.charCodeAt(0)))
  write(16, 16, 4)               // chunk size
  write(20, 1, 2)                // PCM format
  write(22, 1, 2)                // mono
  write(24, sampleRate, 4)
  write(28, sampleRate * bytesPerSample, 4)  // byte rate
  write(32, bytesPerSample, 2)   // block align
  write(34, 16, 2)               // bits per sample
  "data".split("").forEach((c, i) => view.setUint8(36 + i, c.charCodeAt(0)))
  write(40, dataBytes, 4)

  // Convert float32 [-1,1] → int16
  let offset = 44
  for (const s of samples) {
    const clamped = Math.max(-1, Math.min(1, s))
    view.setInt16(offset, clamped < 0 ? clamped * 0x8000 : clamped * 0x7fff, true)
    offset += 2
  }

  return new Blob([buffer], { type: "audio/wav" })
}
