// Preserve episode selectors and unknown query parameters; ignore only campaign tags.
globalThis.powerfulTSMediaKey = raw => {
  try {
    const url = new URL(raw)
    for (const key of [...url.searchParams.keys()]) {
      if (key.startsWith('utm_') || ['spm', 'spm_id_from', 'vd_source', 'share_source', 'share_medium', 'share_plat', 'share_session_id', 'share_tag'].includes(key)) url.searchParams.delete(key)
    }
    if (url.searchParams.get('p') === '1') url.searchParams.delete('p')
    url.searchParams.sort()
    const hash = /^#t=/.test(url.hash) ? '' : url.hash
    return `${url.origin}${url.pathname.replace(/\/$/, '')}?${url.searchParams}${hash}`
  } catch { return '' }
}
