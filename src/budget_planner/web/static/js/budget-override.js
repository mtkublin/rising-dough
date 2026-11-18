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
    if (!document.getElementById("plan-budget")) {
      /* Plan -> Year cell popover: no budget region here; reload to show the saved cell. */
      window.location.reload();
      return;
    }
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

  /* Tier radios -> segmented chip state + hint text (formerly an inline script;
   * month/year come from data-month-label / data-this-year on the form). */
  function wireTierForm(form) {
    if (form.__tierWired) return;
    form.__tierWired = true;
    var hintTail = form.querySelector("[data-override-hint-tail]");
    var month = form.getAttribute("data-month-label") || "";
    var year = form.getAttribute("data-this-year") || "";
    function sync() {
      var picked = form.querySelector("input[name='tier']:checked");
      form.querySelectorAll(".rd-override__tiers .rd-segmented__item").forEach(function (item) {
        var r = item.querySelector("input[name='tier']");
        item.classList.toggle("rd-segmented__item--active", !!(r && r.checked));
      });
      if (!hintTail || !picked) return;
      if (picked.value === "default") hintTail.textContent = "replaces the default";
      else if (picked.value === "recurring") hintTail.textContent = "replaces default every " + month;
      else hintTail.textContent = "wins over default for " + month + " " + year + " only";
    }
    form.querySelectorAll("input[name='tier']").forEach(function (t) {
      t.addEventListener("change", sync);
    });
    sync();
  }

  function scanTierForms(root) {
    if (!root || !root.querySelectorAll) return;
    if (root.matches && root.matches("[data-override-form]")) wireTierForm(root);
    root.querySelectorAll("[data-override-form]").forEach(wireTierForm);
  }

  document.addEventListener("htmx:load", function (evt) { scanTierForms(evt.target); });
  scanTierForms(document);
})();
