import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import {
  searchMusic as apiSearch,
  playMusic as apiPlay,
  pauseMusic as apiPause,
  resumeMusic as apiResume,
  nextMusic as apiNext,
  stopMusic as apiStop,
  seekMusic as apiSeek,
  setVolume as apiSetVolume,
  setMode as apiSetMode,
  clearQueue as apiClear,
  getNowplaying as apiGetNowplaying,
  getQueue as apiGetQueue,
  removeQueueItem as apiRemoveQueueItem,
  playQueueAt as apiPlayQueueAt,
  moveQueueItem as apiMoveQueueItem,
  getAuthStatus as apiGetAuthStatus,
  getMyPlaylists as apiGetMyPlaylists,
  getPlaylistSongs as apiGetPlaylistSongs,
  getRecommendSongs as apiGetRecommendSongs,
  getPersonalFm as apiGetPersonalFm,
  getBilibiliPopular as apiGetBilibiliPopular,
  enqueueSongs as apiEnqueueSongs,
  getBots as apiGetBots,
  createBot as apiCreateBot,
  startBot as apiStartBot,
  stopBot as apiStopBot,
  deleteBot as apiDeleteBot,
  getFollowSetting as apiGetFollowSetting,
  setFollowSetting as apiSetFollowSetting,
  getBotSettings as apiGetBotSettings,
  setBotSettings as apiSetBotSettings,
  getBotProfile as apiGetBotProfile,
  setBotProfile as apiSetBotProfile,
  getBotAvatarBlob as apiGetBotAvatarBlob,
  setBotAvatar as apiSetBotAvatar,
  deleteBotAvatar as apiDeleteBotAvatar,
  type Song,
  type NowPlaying,
  type Playlist,
  type BotInfo,
  type BotCreate,
  type BotSettings,
  type BotProfile,
} from '@/api/music'

export const useMusicStore = defineStore('music', () => {
  const searchResults = ref<Song[]>([])
  const searching = ref(false)
  const searchKeyword = ref('')
  const nowplaying = ref<NowPlaying | null>(null)
  const queue = ref<Song[]>([])
  const volume = ref(50)
  const playMode = ref('seq')
  // 本地进度（每秒递增，轮询校正）
  const localPosition = ref(0)

  const searchPlatform = ref<'all' | 'netease' | 'qq' | 'bilibili'>('all')

  // ── bot 实例：多 bot 选择，activeBotId 经 localStorage 持久化 ──
  const LS_ACTIVE_BOT = 'active_bot_id'
  const bots = ref<BotInfo[]>([])
  const activeBotId = ref<string>('')
  const activeBot = computed(() => bots.value.find((b) => b.id === activeBotId.value) || null)
  // bot 切换代数：拦截过期轮询响应（防切换后旧 bot 状态闪现）；start 重连定时器
  let botGen = 0
  let startPollTimer: ReturnType<typeof setTimeout> | null = null

  // ── 播放跟随开关（默认开启；点击播放时 bot 自动移到当前用户所在 TS 频道）──
  const followEnabled = ref(true)

  // ── bot 行为 / 外观设置 ──
  // 全局：空闲下线 + 空频道自动暂停（所有 bot 共享）
  const botSettings = ref<BotSettings>({ idleTimeoutMinutes: 0, autoPauseOnEmpty: false })
  // per-bot profile 开关（6 字段），随 activeBotId 切换而重新拉取
  const activeBotProfile = ref<BotProfile | null>(null)
  // 当前 active bot 的固定头像（objectURL；切换/上传/删除时 revoke 重建）
  const activeBotAvatarUrl = ref<string | null>(null)
  const avatarLoading = ref(false)
  let avatarObjUrl: string | null = null

  // ── 我的音乐：平台登录态（提升自 PlatformAccounts，供 MyMusic 置灰判断）──
  const platformStatus = ref<Record<string, { loggedIn: boolean; nickname?: string }>>({})
  const myActivePlatform = ref<'netease' | 'qq' | 'bilibili'>('netease')
  // 各平台歌单 / 推荐 / FM 缓存 + 展开的歌单歌曲
  const myPlaylists = ref<Record<string, Playlist[]>>({})
  const myRecommend = ref<Record<string, Song[]>>({})
  const myFm = ref<Record<string, Song[]>>({})
  const bilibiliPopular = ref<Song[]>([])
  const bilibiliPopularLoaded = ref(false)
  const playlistSongs = ref<Record<string, Song[]>>({})
  const myLoading = ref<Record<string, boolean>>({})
  const myUnsupported = ref<Record<string, boolean>>({})

  /** 搜索（按当前平台；all=三平台并行） */
  async function search(q: string) {
    if (!q.trim()) return
    searching.value = true
    searchKeyword.value = q
    try {
      if (searchPlatform.value === 'all') {
        // 三平台并行搜索，合并结果
        const [ne, qq, bili] = await Promise.allSettled([
          apiSearch(q, 'netease', activeBotId.value),
          apiSearch(q, 'qq', activeBotId.value),
          apiSearch(q, 'bilibili', activeBotId.value),
        ])
        const all: Song[] = []
        for (const r of [ne, qq, bili]) {
          if (r.status === 'fulfilled') all.push(...(r.value.results || []))
        }
        searchResults.value = all
      } else {
        const res = await apiSearch(q, searchPlatform.value, activeBotId.value)
        searchResults.value = res.results || []
      }
    } catch {
      searchResults.value = []
    } finally {
      searching.value = false
    }
  }

  /** 播放（query=歌名 或 'id:xxx'，platform 指定音源，song 透传元数据用于回填 QQ 入队丢失字段） */
  async function play(query: string, queued = false, platform?: string, song?: Song) {
    const res = await apiPlay(query, queued, platform, song, activeBotId.value)
    // 上游 play 失败时仍返回 HTTP 200，必须显式检查并抛出，否则前端会误显示"正在播放"但实际没播：
    //  - {error:"Bot not found"} 等：bot_id 无效 / bot 未连接 / 上游 4xx
    //  - {message:"Cannot play: ..."}：QQ 未登录 / 版权 VIP 限制
    if (res?.error) {
      throw new Error(typeof res.error === 'string' ? res.error : '播放失败')
    }
    const msg = res?.message
    if (typeof msg === 'string' && /cannot play/i.test(msg)) {
      throw new Error('无法播放该曲目（可能需登录对应平台，或版权/VIP 限制）')
    }
    await fetchNowplaying()
    await fetchQueue()
    return res
  }

  /** 暂停 */
  async function pause() {
    await apiPause(activeBotId.value)
    await fetchNowplaying()
  }

  /** 恢复 */
  async function resume() {
    await apiResume(activeBotId.value)
    await fetchNowplaying()
  }

  /** 下一首 */
  async function next() {
    await apiNext(activeBotId.value)
    await fetchNowplaying()
    await fetchQueue()
  }

  /** 停止 */
  async function stop() {
    await apiStop(activeBotId.value)
    await fetchNowplaying()
    await fetchQueue()
  }

  /** 跳转 */
  async function seek(position: number) {
    await apiSeek(position, activeBotId.value)
    localPosition.value = position
    await fetchNowplaying()
  }

  /** 音量（防抖发送，避免频繁请求） */
  let volTimer: ReturnType<typeof setTimeout> | null = null
  async function updateVolume(val: number) {
    volume.value = val
    // 防抖：拖动结束后 300ms 才发送
    if (volTimer) clearTimeout(volTimer)
    volTimer = setTimeout(async () => {
      try { await apiSetVolume(val, activeBotId.value) } catch { /* 静默 */ }
    }, 300)
  }

  /** 清空队列 */
  async function clear() {
    await apiClear(activeBotId.value)
    await fetchQueue()
  }

  /** 移除队列中指定位置的单曲 */
  async function removeQueueAt(index: number) {
    await apiRemoveQueueItem(index, activeBotId.value)
    await fetchQueue()
  }

  /** 跳转到队列指定位置播放（点击队列项切歌） */
  async function playQueueAt(index: number) {
    const res = await apiPlayQueueAt(index, activeBotId.value)
    if (res?.error) throw new Error(typeof res.error === 'string' ? res.error : '切换失败')
    await fetchNowplaying()
    await fetchQueue()
    return res
  }

  /** 拖动调序：移动队列项到新位置 */
  async function moveQueueItem(from: number, to: number) {
    await apiMoveQueueItem(from, to, activeBotId.value)
    await fetchQueue()
  }

  /** 当前播放 */
  async function fetchNowplaying() {
    const gen = botGen
    try {
      const np = await apiGetNowplaying(activeBotId.value)
      if (gen !== botGen) return // 切换发生，丢弃过期响应
      nowplaying.value = np
      volume.value = np.volume ?? 50
      playMode.value = np.playMode || 'seq'
      if (typeof np.position === 'number') localPosition.value = np.position
    } catch {
      // 静默
    }
  }

  /** 队列 */
  async function fetchQueue() {
    const gen = botGen
    try {
      const res = await apiGetQueue(activeBotId.value)
      if (gen !== botGen) return
      queue.value = (res.items || []) as Song[]
    } catch {
      queue.value = []
    }
  }

  /** 播放模式 */
  async function setMode(mode: string) {
    playMode.value = mode
    try { await apiSetMode(mode, activeBotId.value) } catch { /* 静默 */ }
    await fetchNowplaying()
  }

  // ── 我的音乐 ──

  /** 拉取三平台登录态（并发；逐 key 写入避免整对象展开读快照导致的并发覆盖） */
  async function fetchPlatformStatus() {
    const platforms = ['netease', 'qq', 'bilibili'] as const
    const results = await Promise.all(
      platforms.map(async (p) => {
        try {
          const res = await apiGetAuthStatus(p, activeBotId.value)
          return { p, loggedIn: !!res.loggedIn, nickname: res.nickname as string | undefined }
        } catch {
          return { p, loggedIn: false, nickname: undefined }
        }
      }),
    )
    for (const r of results) {
      platformStatus.value[r.p] = { loggedIn: r.loggedIn, nickname: r.nickname }
    }
  }

  /** 用户歌单（自建+收藏） */
  async function fetchMyPlaylists(platform: string) {
    const key = `${platform}:playlists`
    myLoading.value = { ...myLoading.value, [key]: true }
    try {
      const res = await apiGetMyPlaylists(platform, activeBotId.value)
      if (res.unsupported) {
        myUnsupported.value = { ...myUnsupported.value, [key]: true }
        myPlaylists.value = { ...myPlaylists.value, [platform]: [] }
      } else {
        myPlaylists.value = { ...myPlaylists.value, [platform]: (res.data as Playlist[]) || [] }
      }
    } catch {
      // 失败不写状态（保持 undefined），允许重试（切走再切回 / 重新展开触发）
    } finally {
      myLoading.value = { ...myLoading.value, [key]: false }
    }
  }

  /** 歌单内歌曲（懒加载，展开时调） */
  async function fetchPlaylistSongs(playlistId: string, platform: string) {
    const key = `song:${playlistId}`
    myLoading.value = { ...myLoading.value, [key]: true }
    try {
      const res = await apiGetPlaylistSongs(playlistId, platform, activeBotId.value)
      if (res.unsupported) {
        myUnsupported.value = { ...myUnsupported.value, [key]: true }
        playlistSongs.value = { ...playlistSongs.value, [playlistId]: [] }
      } else {
        playlistSongs.value = { ...playlistSongs.value, [playlistId]: (res.data as Song[]) || [] }
      }
    } catch {
      // 失败保持 undefined，允许重试
    } finally {
      myLoading.value = { ...myLoading.value, [key]: false }
    }
  }

  /** 每日推荐 */
  async function fetchRecommend(platform: string) {
    const key = `${platform}:recommend`
    myLoading.value = { ...myLoading.value, [key]: true }
    try {
      const res = await apiGetRecommendSongs(platform, activeBotId.value)
      if (res.unsupported) {
        myUnsupported.value = { ...myUnsupported.value, [key]: true }
        myRecommend.value = { ...myRecommend.value, [platform]: [] }
      } else {
        myRecommend.value = { ...myRecommend.value, [platform]: (res.data as Song[]) || [] }
      }
    } catch {
      // 失败保持 undefined，允许重试
    } finally {
      myLoading.value = { ...myLoading.value, [key]: false }
    }
  }

  /** 私人 FM */
  async function fetchPersonalFm(platform: string) {
    const key = `${platform}:fm`
    myLoading.value = { ...myLoading.value, [key]: true }
    try {
      const res = await apiGetPersonalFm(platform, activeBotId.value)
      if (res.unsupported) {
        myUnsupported.value = { ...myUnsupported.value, [key]: true }
        myFm.value = { ...myFm.value, [platform]: [] }
      } else {
        myFm.value = { ...myFm.value, [platform]: (res.data as Song[]) || [] }
      }
    } catch {
      // 失败保持 undefined，允许重试
    } finally {
      myLoading.value = { ...myLoading.value, [key]: false }
    }
  }

  /** B 站热门视频（无需登录） */
  async function fetchBilibiliPopular() {
    const key = 'bilibili:popular'
    myLoading.value = { ...myLoading.value, [key]: true }
    try {
      const res = await apiGetBilibiliPopular(20, activeBotId.value)
      bilibiliPopular.value = (res.data as Song[]) || []
      bilibiliPopularLoaded.value = true
    } catch {
      // 失败不设 loaded，允许重试
    } finally {
      myLoading.value = { ...myLoading.value, [key]: false }
    }
  }

  /** 整单/批量入队（后端循环 add，最多 50 首） */
  async function enqueueAll(songs: Song[], platform?: string) {
    const res = await apiEnqueueSongs(platform, songs, activeBotId.value)
    await fetchQueue()
    return res
  }

  // ── bot 实例管理 ──

  /** 拉取 bot 列表，并选定 active（localStorage 命中 → default → 第一个） */
  async function fetchBots() {
    // 先清残留：防切换账号后用旧账号的 activeBotId 请求（owner 校验会 403，且串账号数据）
    activeBotId.value = ''
    bots.value = []
    try {
      const res = await apiGetBots()
      bots.value = res.bots || []
    } catch {
      bots.value = []
    }
    const stored = localStorage.getItem(LS_ACTIVE_BOT)
    if (stored && bots.value.some((b) => b.id === stored)) {
      activeBotId.value = stored
    } else if (bots.value.length) {
      const def = bots.value.find((b) =>b.default) || bots.value[0]
      activeBotId.value = def.id
      localStorage.setItem(LS_ACTIVE_BOT, def.id)
    } else {
      activeBotId.value = ''
    }
    // activeBot 就绪后拉取其 profile / 头像（fetchBots 不经 setActiveBot，需在此补）
    if (activeBotId.value) {
      void fetchBotProfile()
      void refreshAvatar()
    }
    // 平台登录态随当前 bot 自动拉取（不等用户点开平台账号面板）
    void fetchPlatformStatus()
  }

  /** 切换 active bot：持久化 + 清旧 bot 播放态 + 拉新 bot */
  async function setActiveBot(id: string) {
    botGen++ // 作废所有 in-flight 轮询，防旧 bot 状态闪现
    activeBotId.value = id
    localStorage.setItem(LS_ACTIVE_BOT, id)
    nowplaying.value = null
    queue.value = []
    localPosition.value = 0
    activeBotProfile.value = null
    await Promise.all([fetchNowplaying(), fetchQueue(), fetchBotProfile(), refreshAvatar(), fetchPlatformStatus()])
  }

  async function createBot(payload: BotCreate) {
    const created = await apiCreateBot(payload)
    await fetchBots()
    return created
  }

  async function startBot(id: string) {
    await apiStartBot(id)
    await fetchBots()
    // start 是异步 TS 连接，延迟二次确认 status（清理前一个定时器防叠加）
    if (startPollTimer) clearTimeout(startPollTimer)
    startPollTimer = setTimeout(() => { void fetchBots(); startPollTimer = null }, 2000)
  }

  async function stopBot(id: string) {
    await apiStopBot(id)
    await fetchBots()
    if (id === activeBotId.value) {
      await Promise.all([fetchNowplaying(), fetchQueue()])
    }
  }

  async function deleteBot(id: string) {
    await apiDeleteBot(id)
    await fetchBots()
    if (id === activeBotId.value) {
      await Promise.all([fetchNowplaying(), fetchQueue()])
    }
  }

  /** 拉取播放跟随开关 */
  async function fetchFollowSetting() {
    try {
      const res = await apiGetFollowSetting()
      followEnabled.value = res.enabled
    } catch {
      // 静默，保持默认 true
    }
  }

  /** 设置播放跟随开关 */
  async function setFollow(enabled: boolean) {
    await apiSetFollowSetting(enabled)
    followEnabled.value = enabled
  }

  // ── bot 行为 / 外观设置 ──

  /** 拉取全局 bot 行为设置 */
  async function fetchBotSettings() {
    try {
      botSettings.value = await apiGetBotSettings()
    } catch {
      // 静默，保持默认
    }
  }

  /** 更新全局 bot 行为设置（仅传需要改的字段） */
  async function saveBotSettings(payload: Partial<BotSettings>) {
    botSettings.value = await apiSetBotSettings(payload)
    return botSettings.value
  }

  /** 拉取当前 active bot 的 profile 开关 */
  async function fetchBotProfile() {
    if (!activeBotId.value) {
      activeBotProfile.value = null
      return
    }
    try {
      activeBotProfile.value = await apiGetBotProfile(activeBotId.value)
    } catch {
      activeBotProfile.value = null
    }
  }

  /** 更新当前 active bot 的 profile 开关（上游立即生效） */
  async function saveBotProfile(payload: Partial<BotProfile>) {
    if (!activeBotId.value) return
    activeBotProfile.value = await apiSetBotProfile(activeBotId.value, payload)
    return activeBotProfile.value
  }

  /** 重新拉取当前 active bot 的固定头像（revoke 旧 objectURL）。404=未设置，静默置空 */
  async function refreshAvatar() {
    const gen = botGen
    if (avatarObjUrl) {
      URL.revokeObjectURL(avatarObjUrl)
      avatarObjUrl = null
    }
    activeBotAvatarUrl.value = null
    if (!activeBotId.value) return
    avatarLoading.value = true
    try {
      const blob = await apiGetBotAvatarBlob(activeBotId.value)
      // 切换发生则丢弃过期响应（blob 未转 objectURL，无需 revoke），防乱序覆盖
      if (gen !== botGen) return
      if (blob && blob.size > 0) {
        avatarObjUrl = URL.createObjectURL(blob)
        activeBotAvatarUrl.value = avatarObjUrl
      }
    } catch {
      // 404 = 未设置固定头像
    } finally {
      if (gen === botGen) avatarLoading.value = false
    }
  }

  /** 释放当前 objectURL（组件卸载时调用，防内存泄漏） */
  function disposeAvatar() {
    if (avatarObjUrl) {
      URL.revokeObjectURL(avatarObjUrl)
      avatarObjUrl = null
    }
    activeBotAvatarUrl.value = null
  }

  /** 上传/替换当前 active bot 的固定头像（data:image/...;base64,...） */
  async function uploadAvatar(dataUrl: string) {
    if (!activeBotId.value) return
    await apiSetBotAvatar(activeBotId.value, dataUrl)
    await refreshAvatar()
  }

  /** 移除当前 active bot 的固定头像 */
  async function removeAvatar() {
    if (!activeBotId.value) return
    await apiDeleteBotAvatar(activeBotId.value)
    await refreshAvatar()
  }

  return {
    searchResults,
    searching,
    searchKeyword,
    searchPlatform,
    nowplaying,
    queue,
    volume,
    playMode,
    localPosition,
    bots,
    activeBotId,
    activeBot,
    platformStatus,
    myActivePlatform,
    myPlaylists,
    myRecommend,
    myFm,
    bilibiliPopular,
    bilibiliPopularLoaded,
    playlistSongs,
    myLoading,
    myUnsupported,
    search,
    play,
    pause,
    resume,
    next,
    stop,
    seek,
    updateVolume,
    clear,
    removeQueueAt,
    playQueueAt,
    moveQueueItem,
    setMode,
    fetchNowplaying,
    fetchQueue,
    fetchPlatformStatus,
    fetchMyPlaylists,
    fetchPlaylistSongs,
    fetchRecommend,
    fetchPersonalFm,
    fetchBilibiliPopular,
    enqueueAll,
    fetchBots,
    setActiveBot,
    createBot,
    startBot,
    stopBot,
    deleteBot,
    followEnabled,
    fetchFollowSetting,
    setFollow,
    botSettings,
    activeBotProfile,
    activeBotAvatarUrl,
    avatarLoading,
    fetchBotSettings,
    saveBotSettings,
    fetchBotProfile,
    saveBotProfile,
    refreshAvatar,
    uploadAvatar,
    removeAvatar,
    disposeAvatar,
  }
})
