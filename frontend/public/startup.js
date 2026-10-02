// Only the first-paint screen: it disappears after React commits. No automatic reload.
(() => {
  const screen = document.getElementById('startup-loading')
  const message = document.getElementById('startup-message')
  if (!screen || !message) return
  const update = () => {
    if (!screen?.isConnected || !message) return
    screen.dataset.slow = 'true'
    message.textContent = navigator.onLine
      ? 'Taking longer than usual to open. You can reload if the connection was interrupted.'
      : 'You appear to be offline. Reconnect, then reload to open OpenAnonymi.'
  }
  const timer = window.setTimeout(update, 10000)
  const online = () => {
    if (screen.isConnected && screen.dataset.slow === 'true') {
      message.textContent = 'You’re connected again. Reload when you’re ready if the page hasn’t opened.'
    }
  }
  const visibility = () => {
    const orbit = screen.querySelector('.startup-orbit')
    if (screen.isConnected && orbit) orbit.style.animationPlayState = document.hidden ? 'paused' : 'running'
  }
  window.addEventListener('offline', update)
  window.addEventListener('online', online)
  document.addEventListener('visibilitychange', visibility)
  const observer = new MutationObserver(() => {
    if (screen.isConnected) return
    clearTimeout(timer)
    window.removeEventListener('offline', update)
    window.removeEventListener('online', online)
    document.removeEventListener('visibilitychange', visibility)
    observer.disconnect()
  })
  observer.observe(document.body, { childList: true })
  if (!navigator.onLine) update()
  visibility()
  document.getElementById('startup-retry')?.addEventListener('click', () => location.reload())
})()
