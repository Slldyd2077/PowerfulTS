import { computed, onBeforeUnmount, ref, shallowRef } from 'vue'
import apiClient from '@/api/client'
import { isAxiosError } from 'axios'
import type { PlaybackState } from '@/services/watch-playback'

export interface WatchShare extends PlaybackState {
  id: string
  owner: string
  kind: 'sync' | 'screen'
  source: 'direct' | 'site' | null
  url: string
  requestedPaused: boolean
  waiting: { nickname: string; reason: 'loading' | 'offline' }[]
  waitForMembers: boolean
  allowMemberPause: boolean
  live: boolean
}
interface Peer { id: string; nickname: string }
interface RoomState { peers: Peer[]; share: WatchShare | null; host: string | null }
type RoomMessage =
  | { type: 'welcome'; peerId: string }
  | { type: 'pong'; sentAt: number; serverTime: number }
  | { type: 'error'; message: string }
  | ({ type: 'room' } & RoomState)
  | { type: 'signal'; from: string; shareId: string; description: RTCSessionDescriptionInit | null; candidate: RTCIceCandidateInit | null }

export function useWatchRoom() {
  const connected = ref(false)
  const joining = ref(false)
  const error = ref('')
  const peerId = ref('')
  const room = ref<RoomState>({ peers: [], share: null, host: null })
  const localStream = shallowRef<MediaStream | null>(null)
  const remoteStream = shallowRef<MediaStream | null>(null)
  const serverOffset = ref(0)
  const sharingPending = ref(false)
  const isOwner = computed(() => !!room.value.share && room.value.share.owner === peerId.value)
  const isHost = computed(() => room.value.host === peerId.value)
  let socket: WebSocket | null = null
  let iceServers: RTCIceServer[] = []
  let timer: number | undefined
  let generation = 0
  let captureGeneration = 0
  let reconnectTimer: number | undefined
  let reconnectAttempts = 0
  const peers = new Map<string, RTCPeerConnection>()
  const candidates = new Map<string, RTCIceCandidateInit[]>()
  let messageChain = Promise.resolve()

  function send(message: object): void {
    if (socket?.readyState === WebSocket.OPEN) socket.send(JSON.stringify(message))
  }
  function stopMedia(): void {
    captureGeneration++
    for (const pc of peers.values()) pc.close()
    peers.clear()
    candidates.clear()
    localStream.value?.getTracks().forEach(track => track.stop())
    localStream.value = null
    remoteStream.value = null
    sharingPending.value = false
  }
  function leave(): void {
    generation++
    window.clearTimeout(reconnectTimer)
    send({ type: 'leave' })
    socket?.close()
    socket = null
    window.clearInterval(timer)
    connected.value = false
    joining.value = false
    peerId.value = ''
    room.value = { peers: [], share: null, host: null }
    stopMedia()
  }
  function fail(cause: unknown): void {
    error.value = cause instanceof Error ? cause.message : '共享操作失败'
  }

  function connection(id: string, shareId: string): RTCPeerConnection {
    const existing = peers.get(id)
    if (existing) return existing
    const pc = new RTCPeerConnection({ iceServers })
    peers.set(id, pc)
    pc.onicecandidate = event => {
      if (event.candidate) send({ type: 'signal', target: id, shareId, candidate: event.candidate.toJSON() })
    }
    pc.ontrack = event => {
      const stream = remoteStream.value ?? new MediaStream()
      if (!stream.getTracks().some(track => track.id === event.track.id)) stream.addTrack(event.track)
      remoteStream.value = stream
    }
    pc.onconnectionstatechange = () => {
      if (pc.connectionState === 'failed') error.value = '画面连接失败，请重新加入共享；跨网络可能需要配置 TURN 中继'
    }
    return pc
  }
  async function offer(id: string, share: WatchShare): Promise<void> {
    if (!localStream.value || peers.has(id)) return
    const pc = connection(id, share.id)
    for (const track of localStream.value.getTracks()) pc.addTrack(track, localStream.value)
    await pc.setLocalDescription(await pc.createOffer())
    if (room.value.share?.id !== share.id || pc.signalingState === 'closed') return
    send({ type: 'signal', target: id, shareId: share.id, description: pc.localDescription?.toJSON() })
  }
  async function receive(message: RoomMessage): Promise<void> {
    if (message.type === 'welcome') peerId.value = message.peerId
    if (message.type === 'pong') {
      serverOffset.value = message.serverTime - (message.sentAt + Date.now()) / 2
    }
    if (message.type === 'error') {
      error.value = message.message
      if (sharingPending.value) stopMedia()
    }
    if (message.type === 'room') {
      const previous = room.value.share
      const next = message.share
      if (previous?.id !== next?.id) {
        // Preserve an explicitly captured stream while the server acknowledges start.
        if (!(sharingPending.value && next?.owner === peerId.value && next.kind === 'screen')) stopMedia()
        else sharingPending.value = false
      }
      room.value = { peers: message.peers, share: next, host: message.host }
      if (next?.kind === 'screen') {
        const activeIds = new Set(room.value.peers.map(peer => peer.id))
        for (const [id, pc] of peers) {
          if (!activeIds.has(id)) { pc.close(); peers.delete(id); candidates.delete(id) }
        }
        if (next.owner === peerId.value) {
          for (const peer of room.value.peers) if (peer.id !== peerId.value) await offer(peer.id, next)
        }
      }
    }
    if (message.type === 'signal') {
      const share = room.value.share
      if (!share || share.id !== message.shareId || share.kind !== 'screen') return
      const pc = connection(message.from, share.id)
      if (message.description) {
        await pc.setRemoteDescription(message.description)
        for (const candidate of candidates.get(message.from) ?? []) await pc.addIceCandidate(candidate)
        candidates.delete(message.from)
        if (message.description.type === 'offer') {
          await pc.setLocalDescription(await pc.createAnswer())
          send({ type: 'signal', target: message.from, shareId: share.id, description: pc.localDescription?.toJSON() })
        }
      } else if (message.candidate) {
        if (pc.remoteDescription) await pc.addIceCandidate(message.candidate)
        else candidates.set(message.from, [...(candidates.get(message.from) ?? []), message.candidate])
      }
    }
  }
  async function join(reconnecting = false): Promise<void> {
    leave()
    if (!reconnecting) reconnectAttempts = 0
    error.value = ''
    joining.value = true
    const epoch = generation
    try {
      const { data } = await apiClient.post<{ path: string; iceServers: RTCIceServer[] }>('/music/voice/watch/ticket')
      if (epoch !== generation) return
      iceServers = data.iceServers
      const url = new URL(data.path, window.location.href)
      url.protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
      const ws = new WebSocket(url)
      socket = ws
      ws.onopen = () => {
        if (epoch !== generation) return
        connected.value = true
        joining.value = false
        send({ type: 'ping', sentAt: Date.now() })
        timer = window.setInterval(() => send({ type: 'ping', sentAt: Date.now() }), 10000)
      }
      messageChain = Promise.resolve()
      ws.onmessage = event => {
        messageChain = messageChain.then(async () => {
          if (epoch === generation) await receive(JSON.parse(event.data) as RoomMessage)
        }).catch(fail)
      }
      ws.onerror = () => { if (epoch === generation) error.value = '无法连接共享房间，请检查网络和后端' }
      ws.onclose = event => {
        if (epoch !== generation) return
        leave()
        error.value = event.reason || '共享连接已断开，请重新加入'
        if ([1006, 1011].includes(event.code) && reconnectAttempts < 5) {
          reconnectAttempts++
          error.value = '网络中断，正在重新连接共享房间…'
          reconnectTimer = window.setTimeout(() => void join(true), 2000)
        }
      }
    } catch (cause) {
      if (epoch !== generation) return
      joining.value = false
      error.value = isAxiosError<{ detail?: string }>(cause)
        ? cause.response?.data?.detail || '无法加入共享房间' : '无法加入共享房间'
    }
  }
  function startSync(url: string, source: 'direct' | 'site', options: { waitForMembers: boolean; allowMemberPause: boolean; live: boolean }): void {
    error.value = ''
    try {
      const parsed = new URL(url)
      if (!['http:', 'https:'].includes(parsed.protocol) || parsed.username || parsed.password) throw new Error('请输入有效的 HTTP(S) 视频地址')
      send({ type: 'start', kind: 'sync', url: parsed.href, source, ...options })
    } catch (cause) { fail(cause) }
  }
  async function startScreen(): Promise<void> {
    error.value = ''
    if (!connected.value || room.value.share || sharingPending.value) return
    if (!navigator.mediaDevices?.getDisplayMedia) {
      error.value = '当前浏览器不支持屏幕共享，请使用 HTTPS 下的桌面 Chrome / Edge'
      return
    }
    const epoch = ++captureGeneration
    sharingPending.value = true
    try {
      const stream = await navigator.mediaDevices.getDisplayMedia({
        video: { width: { ideal: 1280 }, height: { ideal: 720 }, frameRate: { ideal: 15, max: 30 } }, audio: true,
      })
      if (epoch !== captureGeneration || !connected.value || room.value.share) {
        stream.getTracks().forEach(track => track.stop())
        return
      }
      localStream.value = stream
      const video = stream.getVideoTracks()[0]
      if (!video) throw new Error('没有捕获到画面')
      video.contentHint = 'detail'
      video.onended = stopShare
      send({ type: 'start', kind: 'screen' })
    } catch (cause) {
      if (epoch !== captureGeneration) return
      stopMedia()
      if (!(cause instanceof DOMException && cause.name === 'NotAllowedError')) fail(cause)
    }
  }
  function stopShare(): void {
    const share = room.value.share
    if (isOwner.value && share) send({ type: 'stop', shareId: share.id })
    stopMedia()
  }
  function publish(position: number, paused: boolean, rate: number): void {
    if (!isOwner.value || room.value.share?.kind !== 'sync') return
    send({ type: 'playback', shareId: room.value.share.id, position, paused, rate })
  }
  function transferHost(target: string): void { send({ type: 'transfer', target }) }
  function setReady(ready: boolean): void {
    const share = room.value.share
    if (share?.kind === 'sync') send({ type: 'ready', shareId: share.id, ready })
  }
  function pauseRoom(paused = true): void {
    const share = room.value.share
    if (share?.kind === 'sync') send({ type: 'pause', shareId: share.id, paused })
  }
  function setOptions(waitForMembers: boolean, allowMemberPause: boolean): void {
    const share = room.value.share
    if (isHost.value && share?.kind === 'sync') send({ type: 'settings', shareId: share.id, waitForMembers, allowMemberPause })
  }
  onBeforeUnmount(leave)
  return { connected, joining, error, peerId, room, isOwner, isHost, localStream, remoteStream,
    sharingPending, serverOffset, join, leave, startSync, startScreen, stopShare, publish, transferHost, setReady, pauseRoom, setOptions }
}
