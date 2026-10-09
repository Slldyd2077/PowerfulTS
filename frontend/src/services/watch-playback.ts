export interface PlaybackState {
  position: number
  paused: boolean
  rate: number
  updatedAt: number
}

/** Server timestamps plus a ping-derived clock offset avoid clock skew between viewers. */
export function playbackPosition(state: PlaybackState, serverNow: number): number {
  const elapsed = state.paused ? 0 : Math.max(0, serverNow - state.updatedAt) / 1000
  return Math.max(0, state.position + elapsed * state.rate)
}

export async function applyPlayback(video: HTMLVideoElement, state: PlaybackState, serverNow: number): Promise<void> {
  const desired = playbackPosition(state, serverNow)
  const target = Number.isFinite(video.duration) ? Math.min(desired, video.duration) : desired
  if (Math.abs(video.currentTime - target) > 0.8) video.currentTime = target
  if (video.playbackRate !== state.rate) video.playbackRate = state.rate
  if (state.paused) video.pause()
  else if (video.paused) await video.play()
}
