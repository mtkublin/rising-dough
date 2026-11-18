// T-068 — Command palette. Native <dialog> gives focus trap + Esc close for
// free; this module only wires the keyboard interactions and filtering.
(() => {
  const dialog = document.getElementById("command-palette");
  if (!dialog) return;
  const input = dialog.querySelector(".palette-input");
  const items = () => Array.from(dialog.querySelectorAll(".palette-item"));
  const visible = () => items().filter(li => !li.classList.contains("palette-item--hidden"));
  let cursor = 0;

  // WHY: expose a shared opener so shortcuts.js (and future HTMX hooks) do not
  // reach into dialog internals.
  const open = () => {
    if (!dialog.open) dialog.showModal();
    input.value = "";
    items().forEach(li => li.classList.remove("palette-item--hidden"));
    cursor = 0;
    highlight();
    requestAnimationFrame(() => input.focus());
  };
  window.openCommandPalette = open;

  const highlight = () => {
    visible().forEach((li, i) => li.setAttribute("aria-selected", i === cursor ? "true" : "false"));
  };

  const activate = (li) => {
    if (!li) return;
    dialog.close();
    const url = li.dataset.url;
    if (url) { window.location.assign(url); return; }
    const action = li.dataset.action;
    if (action) runAction(action);
  };

  // WHY: palette actions must work on every page, so they do not depend on a
  // page-specific button; "new" loads the same overlay as the top-bar Add.
  const ACTIONS = {
    new: () => {
      if (window.htmx) window.htmx.ajax("GET", "/add?when=happened", { target: "#modal-root", swap: "innerHTML" });
    },
    shortcuts: () => {
      const dlg = document.getElementById("shortcuts-dialog");
      if (dlg && !dlg.open) dlg.showModal();
    },
  };
  const runAction = (action) => {
    const fn = ACTIONS[action];
    if (fn) fn();
  };

  input.addEventListener("input", () => {
    const q = input.value.trim().toLowerCase();
    items().forEach(li => {
      if (li.classList.contains("palette-section")) return;
      const label = (li.dataset.label || li.textContent || "").toLowerCase();
      li.classList.toggle("palette-item--hidden", q.length > 0 && !label.includes(q));
    });
    cursor = 0;
    highlight();
  });

  dialog.addEventListener("keydown", (e) => {
    const vis = visible();
    if (e.key === "ArrowDown") { e.preventDefault(); cursor = Math.min(cursor + 1, vis.length - 1); highlight(); }
    else if (e.key === "ArrowUp") { e.preventDefault(); cursor = Math.max(cursor - 1, 0); highlight(); }
    else if (e.key === "Enter") { e.preventDefault(); activate(vis[cursor]); }
  });

  dialog.addEventListener("click", (e) => {
    const li = e.target.closest(".palette-item");
    if (li && !li.classList.contains("palette-section")) activate(li);
  });
})();
