// T-068 — Global keyboard shortcuts. Reads `data-shortcut` off nav items so
// the keymap can never drift from the rail partial (ADR-0023).
(() => {
  const CHORD_MS = 1000;
  let pending = null; // { prefix, expiresAt }

  // WHY: typing in a field or already inside a <dialog> should never trigger
  // chords. Esc is the one global we always keep.
  const guarded = () => {
    const a = document.activeElement;
    if (!a) return false;
    if (a.closest("dialog[open]")) return true;
    const tag = a.tagName;
    return tag === "INPUT" || tag === "TEXTAREA" || a.isContentEditable;
  };

  // Hard-coded fallback: ensures `g a` and friends work even if the nav
  // partial changes shape. The DOM scan still runs so authored data-shortcut
  // overrides win.
  const FALLBACK_NAV = {
    "g o": "/today",
    "g l": "/ledger",
    "g p": "/plan",
    "g a": "/accounts",
    "g s": "/settings",
  };

  const navMap = () => {
    const map = { ...FALLBACK_NAV };
    document.querySelectorAll("[data-shortcut]").forEach(el => {
      const key = el.getAttribute("data-shortcut");
      const href = el.getAttribute("href");
      if (key && href) map[key] = href;
    });
    return map;
  };

  // T-071 — Overlay stack: native <dialog>[open] wins (focus trap + Esc are
  // free); fall back to role=dialog overlays (slide-over, drawer) by clearing
  // their mount root. Order matches visual z-index: last-opened overlay goes
  // first out.
  const closeTopmostOverlay = () => {
    const dlg = Array.from(document.querySelectorAll("dialog[open]")).pop();
    if (dlg) { dlg.close(); return true; }
    const slide = document.querySelector("[data-slideover]");
    if (slide) { const root = document.getElementById("modal-root"); if (root) root.innerHTML = ""; return true; }
    const drawer = document.querySelector("[data-drawer]");
    if (drawer) { const root = document.getElementById("drawer-root"); if (root) root.innerHTML = ""; return true; }
    return false;
  };

  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") {
      if (closeTopmostOverlay()) e.preventDefault();
      return;
    }
    if (guarded()) return;
    if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
      e.preventDefault();
      window.openCommandPalette?.();
      return;
    }
    if (e.metaKey || e.ctrlKey || e.altKey) return;

    const now = Date.now();
    if (pending && now > pending.expiresAt) pending = null;

    if (pending && pending.prefix === "g") {
      const chord = `g ${e.key.toLowerCase()}`;
      pending = null;
      const href = navMap()[chord];
      if (href) { e.preventDefault(); window.location.assign(href); }
      return;
    }
    if (e.key === "g") { pending = { prefix: "g", expiresAt: now + CHORD_MS }; return; }
    if (e.key === "n") {
      e.preventDefault();
      // T-069 — `n` opens the palette as the quick-add affordance.
      window.openCommandPalette?.();
      return;
    }
    if (e.key === "/") {
      const target = document.querySelector("[data-search-input]");
      if (target) { e.preventDefault(); target.focus(); }
      return;
    }
    if (e.key === "?") {
      const dlg = document.getElementById("shortcuts-dialog");
      if (dlg) { e.preventDefault(); dlg.showModal(); }
      return;
    }
    // T-064, T-107 — [ / ] cycle the ledger segmented control. Discover
    // views from the DOM so the keymap can never drift from the template.
    // After T-107 the segmented control is anchor-based (ADR-0028); the
    // active tab is marked with aria-current="page" and navigation goes
    // through location.assign so the full-document render path runs.
    if (e.key === "[" || e.key === "]") {
      const seg = document.querySelector("[data-ledger-views]");
      if (!seg) return;
      const items = Array.from(seg.querySelectorAll("[data-view]"));
      if (items.length === 0) return;
      const activeIdx = items.findIndex(el => el.getAttribute("aria-current") === "page");
      const idx = Math.max(0, activeIdx);
      const delta = e.key === "]" ? 1 : -1;
      const next = items[(idx + delta + items.length) % items.length];
      const href = next && next.getAttribute("href");
      if (href) { e.preventDefault(); window.location.assign(href); }
    }
  });
})();
