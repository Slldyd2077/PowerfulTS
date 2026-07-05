import apiClient from './client'

export interface SettingItem {
  label: string
  sensitive: boolean
  restart: boolean
  reload?: string
  value: string
  is_set: boolean
}

export async function getAdminSettings(): Promise<{ settings: Record<string, SettingItem> }> {
  const { data } = await apiClient.get('/admin/settings')
  return data
}

export async function putAdminSettings(items: Record<string, string>): Promise<{ success: boolean; need_restart: boolean; reloaded: string[] }> {
  const { data } = await apiClient.put('/admin/settings', { items })
  return data
}

export interface NapcatStatus {
  connected: boolean
  user_id?: string
  nickname?: string
  error?: string
}

export async function checkNapcatStatus(): Promise<NapcatStatus> {
  const { data } = await apiClient.get('/admin/napcat/status')
  return data
}
