/** 注册会去掉首尾空格；TS 非 SDK 客户端的昵称按 Unicode 字符计数。 */
export function tsNicknameError(nickname: string): string | null {
  const name = nickname.trim()
  if (!name) return 'TS 昵称不能为空'
  const length = Array.from(name).length
  return length < 3 || length > 30 ? 'TS 昵称需为 3–30 个字符' : null
}
