import type { AxiosProgressEvent } from 'axios'
import apiClient from './client'

export interface EntrySoundMetadata {
  configured: boolean
  originalName?: string
  mimeType?: string
  sizeBytes?: number
  durationMs?: number
}

interface EntrySoundResponse {
  enabled: boolean
  filename?: string
  mimeType?: string
  sizeBytes?: number
  durationMs?: number
}

const ENTRY_SOUND_PATH = '/music/voice/entry-sound'

function toEntrySoundMetadata(data: EntrySoundResponse): EntrySoundMetadata {
  return {
    configured: data.enabled,
    originalName: data.filename,
    mimeType: data.mimeType,
    sizeBytes: data.sizeBytes,
    durationMs: data.durationMs,
  }
}

export async function getEntrySound(signal?: AbortSignal): Promise<EntrySoundMetadata> {
  const { data } = await apiClient.get<EntrySoundResponse>(ENTRY_SOUND_PATH, { signal })
  return toEntrySoundMetadata(data)
}

export async function uploadEntrySound(
  file: File,
  onProgress: (progress: number) => void,
  signal?: AbortSignal,
): Promise<EntrySoundMetadata> {
  const path = `${ENTRY_SOUND_PATH}?filename=${encodeURIComponent(file.name)}`
  const { data } = await apiClient.put<EntrySoundResponse>(path, file, {
    headers: {
      'Content-Type': file.type || 'application/octet-stream',
    },
    onUploadProgress: (event: AxiosProgressEvent) => {
      const total = event.total || file.size
      if (total > 0) onProgress(Math.min(100, Math.round((event.loaded / total) * 100)))
    },
    signal,
    timeout: 60_000,
  })
  return toEntrySoundMetadata(data)
}

export async function deleteEntrySound(signal?: AbortSignal): Promise<void> {
  await apiClient.delete(ENTRY_SOUND_PATH, { signal })
}
