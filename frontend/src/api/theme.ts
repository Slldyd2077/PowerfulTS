import apiClient from './client'

export type BackgroundKind = 'desktop' | 'mobile'

export interface BackgroundInfo {
  url: string
  color: string
}

export interface ThemeConfig {
  desktop: BackgroundInfo | null
  mobile: BackgroundInfo | null
  /** 遮罩暗度 0-85 */
  dim: number
  /** 背景模糊 px 0-24 */
  blur: number
}

export async function getTheme(): Promise<ThemeConfig> {
  const { data } = await apiClient.get<ThemeConfig>('/theme')
  return data
}

export async function uploadBackground(kind: BackgroundKind, file: File): Promise<ThemeConfig> {
  const { data } = await apiClient.put<ThemeConfig>(`/theme/background/${kind}`, file, {
    headers: { 'Content-Type': file.type || 'application/octet-stream' },
    timeout: 60000,
  })
  return data
}

export async function deleteBackground(kind: BackgroundKind): Promise<ThemeConfig> {
  const { data } = await apiClient.delete<ThemeConfig>(`/theme/background/${kind}`)
  return data
}

export async function putAppearance(dim: number, blur: number): Promise<ThemeConfig> {
  const { data } = await apiClient.put<ThemeConfig>('/theme/appearance', { dim, blur })
  return data
}
