import apiClient from './client'

export interface BiliVideo {
  bvid: string
  title: string
  author: string
  pic?: string
  duration?: string
  play?: number
}

export interface BiliSearchResult {
  keyword: string
  count: number
  results: BiliVideo[]
}

export interface BiliPlayResult {
  success: boolean
  title: string
  bvid: string
  owner?: string
}

/** 去除 B 站搜索结果标题里的 <em> 高亮标签 */
export function cleanTitle(title: string): string {
  return title.replace(/<[^>]+>/g, '')
}

/** 补全封面协议 */
export function picUrl(pic?: string): string {
  if (!pic) return ''
  return pic.startsWith('//') ? 'https:' + pic : pic
}

/** 搜索 B 站视频 */
export async function searchBili(keyword: string, page = 1): Promise<BiliSearchResult> {
  const { data } = await apiClient.get('/bili/search', { params: { keyword, page } })
  return data
}

/** 播放指定 BV 号 */
export async function playBili(bvid: string, queue = false): Promise<BiliPlayResult> {
  const { data } = await apiClient.post('/bili/play', { bvid, queue })
  return data
}
