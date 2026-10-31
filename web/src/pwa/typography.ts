/** Offline pages use local fonts before first render; no missing subset downloads. */
export function trackOfflineTypography() {
  const update = () => {
    document.documentElement.dataset.network = navigator.onLine === false ? 'offline' : 'online';
  };
  update();
  window.addEventListener('online', update);
  window.addEventListener('offline', update);
  return () => {
    window.removeEventListener('online', update);
    window.removeEventListener('offline', update);
  };
}
