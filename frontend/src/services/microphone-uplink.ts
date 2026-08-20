export type MicrophoneUplinkState =
  | 'idle'
  | 'requesting'
  | 'connecting'
  | 'verifying'
  | 'live'
  | 'reconnecting'

export interface MicrophoneSocket {
  readonly readyState: number
  onopen: (() => void) | null
  onclose: ((event: CloseEvent) => void) | null
  onerror: (() => void) | null
  send(data: Blob): void
  close(code?: number, reason?: string): void
}

export interface MicrophoneRecorder {
  readonly state: RecordingState
  ondataavailable: ((event: BlobEvent) => void) | null
  onerror: (() => void) | null
  start(timeslice?: number): void
  stop(): void
}

export interface MicrophoneSession {
  sessionId: string
  uploadPath: string
}

type TimerHandle = number

export interface MicrophoneUplinkDependencies {
  acquireStream(): Promise<MediaStream>
  prepareStream(stream: MediaStream): Promise<MediaStream>
  releasePreparedStream?(): Promise<void> | void
  chooseMimeType(): string
  startSession(mimeType: string): Promise<MicrophoneSession>
  stopSession(sessionId: string): Promise<void>
  createSocket(path: string): MicrophoneSocket
  createRecorder(stream: MediaStream, mimeType: string): MicrophoneRecorder
  isRecoveryAllowed(): boolean
  setTimer(callback: () => void, delayMs: number): TimerHandle
  clearTimer(timer: TimerHandle): void
  onStateChange(state: MicrophoneUplinkState): void
  onWarning(message: string): void
  onError(message: string): void
}

const SOCKET_OPEN = 1
const SOCKET_OPEN_TIMEOUT_MS = 10000
const FIRST_CHUNK_TIMEOUT_MS = 5000
const MAX_RECONNECT_ATTEMPTS = 5

export const MICROPHONE_MIME_TYPES = [
  'audio/webm;codecs=opus',
  'audio/webm',
  'audio/mp4',
] as const

export function chooseSupportedMicrophoneMimeType(
  isTypeSupported: (mimeType: string) => boolean,
): string {
  return MICROPHONE_MIME_TYPES.find(isTypeSupported) ?? ''
}

function reconnectDelay(attempt: number): number {
  return Math.min(1000 * 2 ** attempt, 10000)
}

function errorMessage(error: unknown, fallback: string): string {
  return error instanceof Error && error.message ? error.message : fallback
}

/**
 * Owns the microphone capture and upload lifecycle independently from playback.
 * A granted permission is not considered live until a non-empty encoded chunk
 * has actually crossed an open WebSocket.
 */
export class MicrophoneUplink {
  private readonly dependencies: MicrophoneUplinkDependencies
  private desired = false
  private generation = 0
  private stream: MediaStream | null = null
  private socket: MicrophoneSocket | null = null
  private recorder: MicrophoneRecorder | null = null
  private sessionId = ''
  private preparedStreamActive = false
  private reconnectAttempt = 0
  private reconnectTimer: TimerHandle | null = null
  private firstChunkTimer: TimerHandle | null = null
  private connecting: Promise<void> | null = null
  private currentState: MicrophoneUplinkState = 'idle'

  constructor(dependencies: MicrophoneUplinkDependencies) {
    this.dependencies = dependencies
  }

  get state(): MicrophoneUplinkState {
    return this.currentState
  }

  async start(): Promise<void> {
    if (this.desired) return this.connecting ?? Promise.resolve()
    this.desired = true
    const generation = ++this.generation
    this.setState('requesting')
    try {
      const stream = await this.dependencies.acquireStream()
      if (!this.desired || generation !== this.generation) {
        this.stopTracks(stream)
        return
      }
      const track = stream.getAudioTracks()[0]
      if (!track || track.readyState !== 'live') {
        this.stopTracks(stream)
        throw new Error('浏览器已授权，但没有可用的麦克风音轨')
      }
      this.stream = stream
      track.addEventListener?.('ended', () => {
        if (this.desired) void this.failPermanently('麦克风已被系统停用，请点击重新开启')
      }, { once: true })
      await this.connect(generation, false)
    } catch (error) {
      await this.failPermanently(errorMessage(error, '无法开启麦克风'))
      throw error
    }
  }

  async recover(): Promise<void> {
    if (!this.desired || !this.dependencies.isRecoveryAllowed()) return
    if (this.isHealthy() || this.connecting || this.reconnectTimer) return
    await this.connect(this.generation, true).catch((error) => {
      this.scheduleReconnect(errorMessage(error, '麦克风重连失败'))
    })
  }

  async restartTransport(): Promise<void> {
    if (!this.desired || !this.stream) return
    const pendingConnection = this.connecting
    if (pendingConnection) await pendingConnection.catch(() => {})
    if (!this.desired || !this.stream) return
    this.clearReconnectTimer()
    await this.disposeConnection()
    await this.connect(this.generation, true).catch((error) => {
      this.scheduleReconnect(errorMessage(error, '麦克风重连失败'))
    })
  }

  async stop(): Promise<void> {
    this.desired = false
    this.generation++
    this.clearReconnectTimer()
    await this.disposeConnection()
    if (this.stream) this.stopTracks(this.stream)
    this.stream = null
    this.reconnectAttempt = 0
    this.setState('idle')
  }

  private async connect(generation: number, reconnecting: boolean): Promise<void> {
    if (!this.desired || generation !== this.generation || !this.stream) return
    if (!this.dependencies.isRecoveryAllowed()) {
      this.setState('reconnecting')
      return
    }
    if (this.connecting) return this.connecting
    const operation = this.openConnection(generation, reconnecting)
    this.connecting = operation
    try {
      await operation
    } catch (error) {
      if (this.desired && generation === this.generation) {
        await this.disposeConnection()
      }
      throw error
    } finally {
      if (this.connecting === operation) this.connecting = null
    }
  }

  private async openConnection(generation: number, reconnecting: boolean): Promise<void> {
    this.setState(reconnecting ? 'reconnecting' : 'connecting')
    const mimeType = this.dependencies.chooseMimeType()
    if (!mimeType) throw new Error('浏览器没有可用的实时音频编码器')
    const preparedStream = await this.dependencies.prepareStream(this.stream!)
    this.preparedStreamActive = true
    if (!this.desired || generation !== this.generation) {
      await this.disposeConnection()
      return
    }
    const session = await this.dependencies.startSession(mimeType)
    this.sessionId = session.sessionId
    if (!this.desired || generation !== this.generation) {
      await this.disposeConnection()
      return
    }
    const socket = this.dependencies.createSocket(session.uploadPath)
    this.socket = socket

    await new Promise<void>((resolve, reject) => {
      let opened = false
      const openTimer = this.dependencies.setTimer(() => {
        if (opened) return
        reject(new Error('麦克风连接超时'))
        socket.close()
      }, SOCKET_OPEN_TIMEOUT_MS)
      socket.onopen = () => {
        this.dependencies.clearTimer(openTimer)
        if (!this.desired || generation !== this.generation || this.socket !== socket) {
          socket.close(1000, 'microphone superseded')
          resolve()
          return
        }
        opened = true
        try {
          const recorder = this.dependencies.createRecorder(preparedStream, mimeType)
          this.recorder = recorder
          recorder.ondataavailable = (event) => this.handleChunk(event, socket, generation)
          recorder.onerror = () => {
            if (this.desired && generation === this.generation) {
              void this.handleDisconnect('麦克风编码器已停止')
            }
          }
          recorder.start(100)
          this.setState('verifying')
          this.firstChunkTimer = this.dependencies.setTimer(() => {
            if (this.desired && generation === this.generation && this.currentState === 'verifying') {
              void this.handleDisconnect('麦克风没有产生音频数据，正在重连')
            }
          }, FIRST_CHUNK_TIMEOUT_MS)
          resolve()
        } catch (error) {
          reject(error)
        }
      }
      socket.onerror = () => {
        if (!opened) {
          this.dependencies.clearTimer(openTimer)
          reject(new Error('麦克风连接失败'))
        }
        socket.close()
      }
      socket.onclose = (event) => {
        if (!opened) {
          this.dependencies.clearTimer(openTimer)
          reject(new Error(event.reason || '麦克风连接在建立前已关闭'))
          return
        }
        if (this.desired && generation === this.generation && this.socket === socket) {
          void this.handleDisconnect(event.reason || '麦克风连接已中断')
        }
      }
    })
  }

  private handleChunk(event: BlobEvent, socket: MicrophoneSocket, generation: number): void {
    if (!this.desired || generation !== this.generation || !event.data.size) return
    if (this.socket !== socket || socket.readyState !== SOCKET_OPEN) return
    try {
      socket.send(event.data)
    } catch {
      void this.handleDisconnect('麦克风连接已中断，正在重连')
      return
    }
    if (this.currentState !== 'live') {
      this.clearFirstChunkTimer()
      this.reconnectAttempt = 0
      this.setState('live')
    }
  }

  private async handleDisconnect(reason: string): Promise<void> {
    if (!this.desired) return
    await this.disposeConnection()
    if (!this.desired) return
    this.dependencies.onWarning(reason)
    this.scheduleReconnect(reason)
  }

  private scheduleReconnect(reason: string): void {
    if (!this.desired) return
    this.setState('reconnecting')
    if (!this.dependencies.isRecoveryAllowed()) return
    if (this.reconnectAttempt >= MAX_RECONNECT_ATTEMPTS) {
      void this.failPermanently(`${reason}，自动重连失败，请点击重新开启`)
      return
    }
    if (this.reconnectTimer) return
    const delay = reconnectDelay(this.reconnectAttempt++)
    this.reconnectTimer = this.dependencies.setTimer(() => {
      this.reconnectTimer = null
      void this.connect(this.generation, true).catch((error) => {
        this.scheduleReconnect(errorMessage(error, '麦克风重连失败'))
      })
    }, delay)
  }

  private async failPermanently(message: string): Promise<void> {
    await this.stop()
    this.dependencies.onError(message)
  }

  private async disposeConnection(): Promise<void> {
    this.clearFirstChunkTimer()
    const recorder = this.recorder
    const socket = this.socket
    const sessionId = this.sessionId
    this.recorder = null
    this.socket = null
    this.sessionId = ''
    if (recorder) {
      recorder.ondataavailable = null
      recorder.onerror = null
      if (recorder.state !== 'inactive') recorder.stop()
    }
    if (socket) {
      socket.onopen = null
      socket.onclose = null
      socket.onerror = null
      socket.close(1000, 'microphone reconnecting')
    }
    if (this.preparedStreamActive) {
      this.preparedStreamActive = false
      await this.dependencies.releasePreparedStream?.()
    }
    if (sessionId) await this.dependencies.stopSession(sessionId).catch(() => {})
  }

  private isHealthy(): boolean {
    const track = this.stream?.getAudioTracks()[0]
    return this.currentState === 'live'
      && track?.readyState === 'live'
      && this.socket?.readyState === SOCKET_OPEN
      && this.recorder?.state === 'recording'
  }

  private stopTracks(stream: MediaStream): void {
    for (const track of stream.getTracks()) track.stop()
  }

  private setState(state: MicrophoneUplinkState): void {
    if (this.currentState === state) return
    this.currentState = state
    this.dependencies.onStateChange(state)
  }

  private clearReconnectTimer(): void {
    if (!this.reconnectTimer) return
    this.dependencies.clearTimer(this.reconnectTimer)
    this.reconnectTimer = null
  }

  private clearFirstChunkTimer(): void {
    if (!this.firstChunkTimer) return
    this.dependencies.clearTimer(this.firstChunkTimer)
    this.firstChunkTimer = null
  }
}
