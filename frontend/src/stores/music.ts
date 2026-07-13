import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { ElMessage } from 'element-plus'
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
  getMusicQuality as apiGetMusicQuality,
  setMusicQuality as apiSetMusicQuality,
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

  const searchPlatform = ref<'all' | 'netease' | 'qq' | 'bilibili' | 'kugou'>('all')

  // ── bot 实例：多 bot 选择，activeBotId 经 localStorage 持久化 ──
  const LS_ACTIVE_BOT = 'active_bot_id'
  const LS_LIBRARY_BOT = 'library_bot_id'
  const bots = ref<BotInfo[]>([])
  const activeBotId = ref<string>('')
  const activeBot = computed(() => bots.value.find((b) => b.id === activeBotId.value) || null)
  const ownLibraryBotId = computed(() => bots.value.find((b) => !b.shared)?.id || '')
  const libraryBots = computed(() => bots.value.filter((b) => !b.shared || b.sharePlaylists))
  // 曲库来源可在自己的账号与“附带歌单”的共享账号间切换；实际播放始终走 activeBotId。
  const libraryBotId = ref<string>('')
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
  const ownPlatformStatus = ref<Record<string, { loggedIn: boolean; nickname?: string }>>({})
  const myActivePlatform = ref<'netease' | 'qq' | 'bilibili' | 'kugou'>('netease')

  // ── 音质设置 ──
  // 当前各平台音质（{ netease, qq, bilibili, kugou }）
  const quality = ref<Record<string, string>>({})
  // 音质选项定义
  const QUALITY_OPTIONS = {
    netease: [
      { value: 'standard', label: '标准 (128kbps)', vip: false },
      { value: 'higher', label: '较高 (192kbps)', vip: false },
      { value: 'exhigh', label: '极高 (320kbps)', vip: false },
      { value: 'lossless', label: '无损 (FLAC)', vip: false },
      { value: 'hires', label: 'Hi-Res', vip: false },
      { value: 'jymaster', label: '超清母带', vip: true },
    ],
    qq: [
      { value: '128', label: '标准 (128kbps)', vip: false },
      { value: '320', label: '高品质 (320kbps)', vip: false },
      { value: 'flac', label: '无损 (FLAC)', vip: true },
    ],
    bilibili: [
      { value: 'high', label: '最高可用（自动）', vip: false },
    ],
    kugou: [
      { value: '128', label: '标准 (128kbps)', vip: false },
      { value: '320', label: '高品质 (320kbps)', vip: false },
      { value: 'flac', label: '无损 (FLAC)', vip: true },
      { value: 'high', label: 'Hi-Res（高解析）', vip: true },
    ],
  } as const

  const QUALITY_ALIASES: Record<string, Record<string, string>> = {
    qq: { standard: '128', higher: '320', exhigh: '320', lossless: 'flac' },
    kugou: { standard: '128', higher: '320', exhigh: '320', lossless: 'flac', hires: 'high' },
  }

  function normalizeQuality(platform: string, value: string): string {
    return QUALITY_ALIASES[platform]?.[value] || value
  }
  // 各平台歌单 / 推荐 / FM 缓存 + 展开的歌单歌曲
  const myPlaylists = ref<Record<string, Playlist[]>>({})
  const myRecommend = ref<Record<string, Song[]>>({})
  const myFm = ref<Record<string, Song[]>>({})
  const bilibiliPopular = ref<Song[]>([])
  const bilibiliPopularLoaded = ref(false)
  const playlistSongs = ref<Record<string, Song[]>>({})
  const myLoading = ref<Record<string, boolean>>({})
  const myUnsupported = ref<Record<string, boolean>>({})

  function clearLibraryData() {
    platformStatus.value = {}
    myPlaylists.value = {}
    myRecommend.value = {}
    myFm.value = {}
    playlistSongs.value = {}
    myUnsupported.value = {}
  }

  async function setLibraryBot(id: string) {
    if (!libraryBots.value.some((b) => b.id === id)) return
    libraryBotId.value = id
    localStorage.setItem(LS_LIBRARY_BOT, id)
    clearLibraryData()
    await fetchPlatformStatus()
  }

  /** 搜索（按当前平台；all=四平台并行） */
  async function search(q: string) {
    if (!q.trim()) return
    searching.value = true
    searchKeyword.value = q
    try {
      if (searchPlatform.value === 'all') {
        // 四平台并行搜索，合并结果并按平台分组
        const resultsByPlatform = await Promise.allSettled([
          apiSearch(q, 'netease', activeBotId.value).catch(() => ({ results: [] })).then((r) => ({ platform: 'netease', results: r.results || [] })),
          apiSearch(q, 'qq', activeBotId.value).catch(() => ({ results: [] })).then((r) => ({ platform: 'qq', results: r.results || [] })),
          apiSearch(q, 'bilibili', activeBotId.value).catch(() => ({ results: [] })).then((r) => ({ platform: 'bilibili', results: r.results || [] })),
          apiSearch(q, 'kugou', activeBotId.value).catch(() => ({ results: [] })).then((r) => ({ platform: 'kugou', results: r.results || [] })),
        ])
        const all: Song[] = []
        for (const r of resultsByPlatform) {
          if (r.status === 'fulfilled' && r.value) {
            // 确保每个歌曲都有 platform 标识
            const songs = (r.value.results || []).map((s: Song) => ({
              ...s,
              platform: s.platform || r.value.platform,
            }))
            all.push(...songs)
          }
        }
        // 按相关性排序：歌名完全匹配 > 歌名包含关键词 > 歌手名包含关键词
        const query = q.toLowerCase().trim()
        all.sort((a, b) => {
          const aName = (a.name || '').toLowerCase()
          const bName = (b.name || '').toLowerCase()
          const aArtist = (a.artist || '').toLowerCase()
          const bArtist = (b.artist || '').toLowerCase()

          // 完全匹配优先
          const aExact = aName === query
          const bExact = bName === query
          if (aExact && !bExact) return -1
          if (!aExact && bExact) return 1

          // 歌名包含关键词
          const aNameContains = aName.includes(query)
          const bNameContains = bName.includes(query)
          if (aNameContains && !bNameContains) return -1
          if (!aNameContains && bNameContains) return 1

          // 歌手名包含关键词
          const aArtistContains = aArtist.includes(query)
          const bArtistContains = bArtist.includes(query)
          if (aArtistContains && !bArtistContains) return -1
          if (!aArtistContains && bArtistContains) return 1

          return 0
        })
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
    const follow = res?.follow as { moved?: boolean; reason?: string } | undefined
    if (followEnabled.value && follow && !follow.moved && follow.reason !== 'already_together') {
      const followErrors: Record<string, string> = {
        bot_not_found: '机器人尚未连接到 TS，无法自动移动频道',
        bot_nickname_unknown: '无法读取机器人 TS 昵称，请检查 Bot 配置',
        user_offline: 'TS 查询未找到你的在线身份，请确认网页账号与当前 TS 身份一致',
        user_no_channel: '无法确定你当前所在的 TS 频道',
        move_failed: 'TS ServerQuery 拒绝移动机器人，请检查 clientmove 权限',
        connect_failed: '无法连接 TS ServerQuery，机器人频道跟随失败',
        exception: '机器人频道跟随发生异常，请查看后端日志',
      }
      ElMessage.warning(followErrors[follow.reason || ''] || `机器人频道跟随失败：${follow.reason || 'unknown'}`)
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

  /** 拉取各平台登录态（并发；逐 key 写入避免整对象展开读快照导致的并发覆盖） */
  async function fetchPlatformStatus() {
    const platforms = ['netease', 'qq', 'bilibili', 'kugou'] as const
    const results = await Promise.all(
      platforms.map(async (p) => {
        try {
          const res = await apiGetAuthStatus(p, libraryBotId.value)
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

  /** 平台账号面板只展示/管理当前用户自己的账号，不受曲库来源切换影响。 */
  async function fetchOwnPlatformStatus() {
    const platforms = ['netease', 'qq', 'bilibili', 'kugou'] as const
    const results = await Promise.all(platforms.map(async (p) => {
      try {
        const res = await apiGetAuthStatus(p, ownLibraryBotId.value)
        return { p, loggedIn: !!res.loggedIn, nickname: res.nickname as string | undefined }
      } catch {
        return { p, loggedIn: false, nickname: undefined }
      }
    }))
    for (const r of results) ownPlatformStatus.value[r.p] = { loggedIn: r.loggedIn, nickname: r.nickname }
  }

  /** 用户歌单（自建+收藏） */
  async function fetchMyPlaylists(platform: string) {
    const key = `${platform}:playlists`
    myLoading.value = { ...myLoading.value, [key]: true }
    try {
      const res = await apiGetMyPlaylists(platform, libraryBotId.value)
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
      const res = await apiGetPlaylistSongs(playlistId, platform, libraryBotId.value)
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
      const res = await apiGetRecommendSongs(platform, libraryBotId.value)
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
      const res = await apiGetPersonalFm(platform, libraryBotId.value)
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
    const storedLibrary = localStorage.getItem(LS_LIBRARY_BOT)
    if (storedLibrary && libraryBots.value.some((b) => b.id === storedLibrary)) {
      libraryBotId.value = storedLibrary
    } else {
      libraryBotId.value = ownLibraryBotId.value || libraryBots.value[0]?.id || ''
      if (libraryBotId.value) localStorage.setItem(LS_LIBRARY_BOT, libraryBotId.value)
    }
    // activeBot 就绪后拉取其 profile / 头像（fetchBots 不经 setActiveBot，需在此补）
    if (activeBotId.value) {
      void fetchBotProfile()
      void refreshAvatar()
      void fetchQuality()
    }
    // 平台登录态随当前 bot 自动拉取（不等用户点开平台账号面板）
    void fetchPlatformStatus()
    void fetchOwnPlatformStatus()
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
    await Promise.all([fetchNowplaying(), fetchQueue(), fetchBotProfile(), refreshAvatar(), fetchPlatformStatus(), fetchQuality()])
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

  // ── 音质设置 ──

  /** 拉取当前各平台音质配置 */
  async function fetchQuality() {
    const botId = activeBotId.value
    if (!botId) {
      quality.value = {}
      return
    }
    try {
      const res = await apiGetMusicQuality(botId)
      if (activeBotId.value !== botId) return
      quality.value = Object.fromEntries(
        Object.entries(res)
          .filter((entry): entry is [string, string] => typeof entry[1] === 'string')
          .map(([platform, value]) => [platform, normalizeQuality(platform, value)]),
      )
    } catch {
      // 静默失败
    }
  }

  /** 设置当前 bot 在指定平台的音质 */
  async function setQuality(q: string, platform: keyof typeof QUALITY_OPTIONS) {
    if (!activeBotId.value) {
      ElMessage.error('请先选择机器人')
      return
    }
    try {
      const res = await apiSetMusicQuality(q, platform, activeBotId.value)
      if (res.success) {
        await fetchQuality()
        const label = QUALITY_OPTIONS[platform].find((option) => option.value === q)?.label || q
        ElMessage.success(`${platform === 'netease' ? '网易云' : platform === 'qq' ? 'QQ音乐' : platform === 'bilibili' ? 'B站' : '酷狗'}音质已切换为：${label}`)
      } else {
        ElMessage.error(res.error || '音质切换失败')
      }
    } catch (e) {
      ElMessage.error('音质切换失败，请稍后重试')
      console.error('setQuality error:', e)
    }
  }

  /** 根据平台和 VIP 状态获取可用音质选项 */
  function getAvailableQualities(platform: 'netease' | 'qq' | 'bilibili' | 'kugou', isVip: boolean) {
    const all = QUALITY_OPTIONS[platform] || []
    return isVip ? all : all.filter((opt) => !opt.vip)
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
    libraryBotId,
    ownLibraryBotId,
    libraryBots,
    setLibraryBot,
    platformStatus,
    ownPlatformStatus,
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
    fetchOwnPlatformStatus,
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
    quality,
    QUALITY_OPTIONS,
    fetchQuality,
    setQuality,
    getAvailableQualities,
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
