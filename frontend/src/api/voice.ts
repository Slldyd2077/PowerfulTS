import axios from 'axios'
import apiClient from './client'

export interface VoiceDownlinkSession {
  ok: boolean
  sessionId: string
  streamPath: string
  expiresIn: number
}

/** 把 axios 的 "Request failed with status code 404" 换成能照着做的提示。 */
function describeFailure(error: unknown, fallback: string): string {
  if (!axios.isAxiosError(error)) {
    return error instanceof Error ? error.message : fallback
  }
  const status = error.response?.status
  const detail = (error.response?.data as { detail?: string } | undefined)?.detail
  if (status === 404) {
    // 前端有这些接口、后端没有 —— 后端进程/镜像停在加频道语音之前。
    return '后端没有网页通话接口（返回 404），请重启或重新部署 PowerfulTS 后端后再试'
  }
  if (status === 401) return '登录态已失效，请重新登录'
  if (detail) return detail
  if (!error.response) return '连不上 PowerfulTS 后端，请确认后端已启动'
  return `${fallback}（HTTP ${status}）`
}

export interface VoiceSession {
  ok: boolean
  botId: string
  /** 频道里其他人看到的名字：就是你自己的 TS 昵称。 */
  nickname: string
}

/** 开通本账号的通话身份（按需建号 + 进服务器），已在线时是幂等的。 */
export async function openVoiceSession(): Promise<VoiceSession> {
  try {
    const { data } = await apiClient.post('/music/voice/session')
    return data
  } catch (error) {
    throw new Error(describeFailure(error, '无法加入通话'))
  }
}

/** 挂断：让自己的通话身份立刻离开服务器。 */
export async function closeVoiceSession(): Promise<void> {
  await apiClient.post('/music/voice/session/stop')
}

export interface VoiceMicSession {
  ok: boolean
  sessionId: string
  uploadPath: string
}

/**
 * 麦克风上行。
 *
 * 不走音乐的 /live/start：那条路按音乐 bot 归属鉴权，而通话 bot 不在那张表里，
 * 会被判 403「无权操作该 Bot」。
 */
export async function startVoiceMicrophone(mimeType: string): Promise<VoiceMicSession> {
  try {
    const { data } = await apiClient.post('/music/voice/mic/start', { mimeType })
    return data
  } catch (error) {
    throw new Error(describeFailure(error, '无法开启麦克风'))
  }
}

export async function startVoiceDownlink(): Promise<VoiceDownlinkSession> {
  try {
    const { data } = await apiClient.post('/music/voice/start')
    return data
  } catch (error) {
    throw new Error(describeFailure(error, '开启频道语音失败'))
  }
}

export interface VoiceChannelClient {
  /** TS client id：下行语音包用它标记说话人，是「谁在说话」和音频流的连接点。 */
  clid: number
  nickname: string
  isBot: boolean
}

export interface VoiceChannel {
  cid: number
  pid: number
  depth: number
  name: string
  hasPassword: boolean
  clients: VoiceChannelClient[]
}

export interface VoiceChannelOverview {
  channels: VoiceChannel[]
  /** 你所在的频道；没加入通话时为 null。 */
  botCid: number | null
  botOnline: boolean
  monitorRunning: boolean
}

/** `fresh` 让后端先催一轮 TS 轮询再返回，用于用户主动刷新（后台轮询不必带）。 */
export async function getVoiceChannels(fresh = false): Promise<VoiceChannelOverview> {
  const { data } = await apiClient.get('/music/voice/channels', {
    params: fresh ? { fresh: 1 } : undefined,
  })
  return data
}

/** 换频道。`password` 只有加锁频道才需要。 */
export async function moveVoiceChannel(cid: number, password = ''): Promise<void> {
  await apiClient.post('/music/voice/channel', { cid, password })
}
