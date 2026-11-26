/*
 * Custom category hues (ADR-0107 §5, ADR-0113). A server-rendered block
 * <span hidden data-color-rules="..."> holds the rules for hues outside the presets
 * (`[data-color="c-<hex>"]{--cat:..;--cat-edge:..}`). It is inert data (an attribute), so CSP style-src
 * (nonce-only) never sees it. This module feeds the rules to one constructed stylesheet through
 * the CSSOM, which style-src does not govern. It runs at load and after every htmx swap, because
 * a fragment response carries its own per-request nonce that the page policy would refuse.
 */
(() => {
  const sheet = new CSSStyleSheet();
  const seen = new Set();
  document.adoptedStyleSheets = [...document.adoptedStyleSheets, sheet];

  function apply(root) {
    for (const block of root.querySelectorAll('[data-color-rules]')) {
      for (const rule of block.getAttribute('data-color-rules').split('}')) {
        const text = rule.trim();
        if (!text || seen.has(text)) continue;
        seen.add(text);
        sheet.insertRule(`${text}}`, sheet.cssRules.length);
      }
    }
  }

  apply(document);
  document.addEventListener('htmx:afterSwap', (event) => {
    const target = event.detail && event.detail.target;
    apply(target instanceof Element && target.isConnected ? target.parentNode || document : document);
  });
})();
