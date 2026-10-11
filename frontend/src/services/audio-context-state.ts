/** resume() may stay pending when Android blocks autoplay or the OS interrupts audio. */
export async function voiceAudioTimeout<T>(operation: Promise<T>, message: string, timeoutMs = 8000): Promise<T> {
  let timer: ReturnType<typeof setTimeout> | undefined
  try {
    return await Promise.race([
      operation,
      new Promise<never>((_, reject) => {
        timer = setTimeout(() => reject(new Error(message)), timeoutMs)
      }),
    ])
  } finally { clearTimeout(timer) }
}

export async function resumeVoiceAudio(context: AudioContext, timeoutMs = 3000): Promise<void> {
  await voiceAudioTimeout(context.resume(), '音频被浏览器暂停，请点击恢复声音', timeoutMs)
  if (context.state !== 'running') throw new Error('音频被系统中断，请点击恢复声音')
}
