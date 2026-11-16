/*
 * Theme preference (Settings › Preferences: system · light · dark). Saved per browser, no backend.
 * Classic (non-module) script loaded in <head> so the theme applies before first paint.
 * Order: ?theme= in the URL (handoff review) › localStorage › system (no attribute).
 */
(() => {
  const KEY = 'rd-theme';
  let theme = null;
  try {
    const fromUrl = new URLSearchParams(window.location.search).get('theme');
    if (fromUrl === 'light' || fromUrl === 'dark' || fromUrl === 'system') {
      window.localStorage.setItem(KEY, fromUrl);
    }
    theme = window.localStorage.getItem(KEY);
  } catch {
    theme = null;
  }
  if (theme === 'light' || theme === 'dark') {
    document.documentElement.dataset.theme = theme;
  }
})();
