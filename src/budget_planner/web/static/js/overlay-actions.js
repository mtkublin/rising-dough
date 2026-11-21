/* Generic delegated actions (T-D140b, ADR-0113: no inline handlers).
 *   [data-action="close-overlay"]      close the slide-over / modal
 *   [data-close-on-backdrop]           close when the backdrop itself is clicked
 *   [data-action="dismiss-flash"]      remove the flash banner
 *   [data-refresh-upcoming]            after a successful request, reload /today/upcoming
 *   [data-close-overlay-on-success]    after the form's own successful non-GET request, close the overlay
 *   [data-rec-chev]                    expand/collapse a recurring ledger row
 *   .rd-plan-year__cell popovers       close on outside click / Escape
 * Also hydrates #modal-root from #rd-modal-prerender (standalone slide-over pages). */
(function () {
  if (window.__overlayActionsWired) return;
  window.__overlayActionsWired = true;

  function clearParentOf(root) {
    if (root && root.parentElement) root.parentElement.innerHTML = "";
  }

  function closeOverlay(from) {
    var root = from.closest(".slide-over-root");
    if (root) { clearParentOf(root); return; }
    var modal = from.closest("#modal-root");
    if (modal) modal.innerHTML = "";
  }

  function toggleRecurringRow(btn) {
    var id = btn.getAttribute("data-rec-chev");
    var row = document.getElementById("recurring-" + id);
    var panel = document.getElementById("recurring-" + id + "-expand");
    if (!panel) return;
    var opening = panel.hasAttribute("hidden");
    if (opening) panel.removeAttribute("hidden"); else panel.setAttribute("hidden", "");
    btn.textContent = opening ? "▾" : "▸";
    btn.setAttribute("aria-expanded", opening ? "true" : "false");
    if (row) row.classList.toggle("rd-rec-row--expanded", opening);
  }

  function closeYearPopovers(target) {
    var cell = target.closest(".rd-plan-year__cell");
    document.querySelectorAll(".rd-year-popover-slot").forEach(function (slot) {
      if (cell && cell.contains(slot)) return;
      if (slot.children.length) slot.innerHTML = "";
    });
  }

  document.addEventListener("click", function (evt) {
    var t = evt.target;
    if (!(t instanceof Element)) return;

    var closer = t.closest('[data-action="close-overlay"]');
    if (closer) { closeOverlay(closer); return; }

    var flash = t.closest('[data-action="dismiss-flash"]');
    if (flash) {
      var banner = flash.closest(".flash");
      if (banner) banner.remove();
      return;
    }

    var backdrop = t.closest("[data-close-on-backdrop]");
    if (backdrop && t === backdrop) { clearParentOf(backdrop); return; }

    var chev = t.closest("[data-rec-chev]");
    if (chev) { toggleRecurringRow(chev); return; }

    closeYearPopovers(t);
  });

  document.addEventListener("keydown", function (evt) {
    if (evt.key !== "Escape") return;
    document.querySelectorAll(".rd-year-popover-slot").forEach(function (slot) {
      if (slot.children.length) slot.innerHTML = "";
    });
  });

  document.addEventListener("htmx:afterRequest", function (evt) {
    if (!evt.detail || !evt.detail.successful) return;
    var t = evt.target;
    if (!(t instanceof Element)) return;
    if (t.closest("[data-refresh-upcoming]") && window.htmx) {
      window.htmx.ajax("GET", "/today/upcoming", { target: "#upcoming-root", swap: "innerHTML" });
    }
    // Only the form's own submit closes the overlay; a GET from a descendant
    // (e.g. the live limit preview) must not (T-D-UT12-1).
    var verb = evt.detail.requestConfig && evt.detail.requestConfig.verb;
    if (t.matches("[data-close-overlay-on-success]") && verb !== "get") {
      clearParentOf(document.querySelector(".slide-over-root"));
    }
  });

  function hydratePrerender() {
    var root = document.getElementById("modal-root");
    var prerender = document.getElementById("rd-modal-prerender");
    if (!root || !prerender) return;
    root.innerHTML = prerender.innerHTML;
    prerender.remove();
    if (window.htmx) window.htmx.process(root);
  }
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", hydratePrerender);
  } else {
    hydratePrerender();
  }
})();
