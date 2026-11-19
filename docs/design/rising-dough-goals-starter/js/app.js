/* Rising Dough · prototype settings. Guide pages carry data-theme-lock and only use the reset button.
   Loaded in <head> (blocking, ~1 kB) so the theme and the starter
   visibility apply before first paint. Settings → Preferences writes them; every app page reads them.
   localStorage keys: rd-theme = system | light | dark, rd-starter = shown | hidden. */
(function () {
  var root = document.documentElement;
  function get(k) { try { return localStorage.getItem(k); } catch (e) { return null; } }
  function set(k, v) { try { localStorage.setItem(k, v); } catch (e) {} }
  var built = root.getAttribute('data-theme') || 'dark';
  var dark = window.matchMedia ? window.matchMedia('(prefers-color-scheme: dark)') : null;
  function themePref() { return get('rd-theme'); }
  function applyTheme() {
    if (root.hasAttribute('data-theme-lock')) return;
    var p = themePref();
    var t = p === 'light' || p === 'dark' ? p : p === 'system' ? (dark && dark.matches ? 'dark' : 'light') : built;
    root.setAttribute('data-theme', t);
  }
  function starterPref() { return get('rd-starter') || root.getAttribute('data-starter-built') || 'shown'; }
  function applyStarter() {
    if (root.hasAttribute('data-theme-lock')) return;
    root.setAttribute('data-starter', starterPref());
  }
  applyTheme(); applyStarter();
  if (dark && dark.addEventListener) dark.addEventListener('change', applyTheme);
  window.addEventListener('storage', function () { applyTheme(); applyStarter(); sync(); });

  function sync() {
    var cur = { theme: themePref() || built, starter: starterPref() };
    Array.prototype.forEach.call(document.querySelectorAll('[data-pref]'), function (b) {
      b.setAttribute('aria-pressed', String(cur[b.getAttribute('data-pref')] === b.getAttribute('data-value')));
    });
    if (starterPref() === 'hidden' && document.body && document.body.hasAttribute('data-starter-page')) {
      location.replace(root.getAttribute('data-theme-file') === 'light' ? 'today.light.html' : 'today.html');
    }
  }
  document.addEventListener('DOMContentLoaded', function () {
    sync();
    document.addEventListener('click', function (e) {
      var b = e.target.closest && e.target.closest('[data-pref]');
      if (b) {
        set(b.getAttribute('data-pref') === 'theme' ? 'rd-theme' : 'rd-starter', b.getAttribute('data-value'));
        applyTheme(); applyStarter(); sync(); return;
      }
      if (e.target.closest && e.target.closest('[data-reset-prefs]')) {
        try { localStorage.removeItem('rd-theme'); localStorage.removeItem('rd-starter'); } catch (x) {}
        applyTheme(); applyStarter(); sync();
      }
    });
  });
})();
