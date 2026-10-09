async function attach(file) {
  const status = document.querySelector('#status')
  try {
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true })
    if (!tab?.id || !/^https?:\/\//.test(tab.url || '')) throw new Error('请在普通网页标签页中使用')
    await chrome.scripting.executeScript({ target: { tabId: tab.id }, files: ['identity.js', file] })
    status.textContent = '已连接。保持通话页和视频页打开。'
  } catch (error) { status.textContent = error.message || '连接失败，请刷新页面再试' }
}
document.querySelector('#dashboard').onclick = () => attach('dashboard.js')
document.querySelector('#video').onclick = () => attach('video.js')
document.querySelector('#disconnect').onclick = async () => {
  await chrome.runtime.sendMessage({ type: 'disconnect' })
  document.querySelector('#status').textContent = '已断开。'
}
