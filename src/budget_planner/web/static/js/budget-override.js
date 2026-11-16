/* Plan -> Budget inline override form (T-D49).
 * The form renders in a per-row slot (#override-slot-<category_id>) directly
 * under the clicked row. One open at a time; Esc / Cancel / outside click
 * closes it and returns focus to the row's Override button. After a
 * successful save the budget region is re-fetched so the row updates. */
(function () {
  if (window.__budgetOverrideWired) return;
  window.__budgetOverrideWired = true;

  var SLOT = "[data-override-slot]";

  function openSlots() {
    return Array.prototype.filter.call(document.querySelectorAll(SLOT), function (s) {
      return s.firstElementChild;
    });
  }

  function openerFor(slot) {
    var id = slot.id.replace("override-slot-", "");
    return document.querySelector('[data-override-open="' + id + '"]');
  }

  function closeSlot(slot, restoreFocus) {
    var opener = openerFor(slot);
    slot.innerHTML = "";
    if (restoreFocus && opener) opener.focus();
  }

  function closeAll(restoreFocus, except) {
    openSlots().forEach(function (s) {
      if (s !== except) closeSlot(s, restoreFocus);
    });
  }

  document.addEventListener("htmx:beforeRequest", function (evt) {
    var t = evt.target;
    if (!(t instanceof Element) || !t.hasAttribute("data-override-open")) return;
    var target = document.getElementById("override-slot-" + t.getAttribute("data-override-open"));
    closeAll(false, target);
  });

  document.addEventListener("htmx:afterSwap", function (evt) {
    var t = evt.target;
    if (!(t instanceof Element) || !t.matches(SLOT)) return;
    var input = t.querySelector("input[name='amount']");
    if (input) input.focus();
  });

  document.addEventListener("htmx:afterRequest", function (evt) {
    var form = evt.target;
    if (!(form instanceof HTMLFormElement) || !form.hasAttribute("data-override-inline")) return;
    var xhr = evt.detail && evt.detail.xhr;
    if (!xhr || xhr.status < 200 || xhr.status >= 300) return;
    var slot = form.closest(SLOT);
    if (slot) closeSlot(slot, true);
    if (window.htmx) {
      window.htmx.ajax("GET", window.location.href, {
        target: "#plan-budget",
        select: "#plan-budget",
        swap: "outerHTML",
      });
    }
  });

  document.addEventListener("click", function (evt) {
    var t = evt.target;
    if (!(t instanceof Element)) return;
    var cancel = t.closest("[data-override-cancel]");
    if (cancel) {
      var own = cancel.closest(SLOT);
      if (own) closeSlot(own, true);
      return;
    }
    if (t.closest(SLOT) || t.closest("[data-override-open]")) return;
    closeAll(false);
  });

  document.addEventListener("keydown", function (evt) {
    if (evt.key !== "Escape") return;
    var open = openSlots();
    if (!open.length) return;
    closeSlot(open[0], true);
  });
})();
