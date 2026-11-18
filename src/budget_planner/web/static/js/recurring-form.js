/* Recurring rule form (amount-source panels, formula terms, source multi-select)
 * and the recurring override form (month picker). T-D140b, ADR-0113.
 * Click/change handling is delegated on document; per-form init via rdWire. */
(function () {
  function formOf(el) { return el.closest("[data-recurring-form]"); }

  function syncPanels(form) {
    var selected = form.querySelector("[data-amount-source-radio]:checked");
    var value = selected ? selected.value : "fixed";
    form.querySelectorAll("[data-amount-source-panel]").forEach(function (panel) {
      var active = panel.getAttribute("data-amount-source-panel") === value;
      if (active) { panel.removeAttribute("hidden"); panel.removeAttribute("aria-hidden"); }
      else { panel.setAttribute("hidden", ""); panel.setAttribute("aria-hidden", "true"); }
    });
    form.querySelectorAll(".rd-amount-source__head .rd-segmented__item").forEach(function (chip) {
      var r = chip.querySelector("[data-amount-source-radio]");
      chip.classList.toggle("rd-segmented__item--active", !!(r && r.checked));
    });
  }

  function reindex(list) {
    list.querySelectorAll("[data-term-row]").forEach(function (row, idx) {
      row.querySelectorAll('[name^="terms["]').forEach(function (el) {
        el.name = el.name.replace(/terms\[\d+\]/, "terms[" + idx + "]");
      });
    });
  }

  function syncSrcSummary(wrap) {
    var sum = wrap.querySelector("[data-src-summary]");
    if (!sum) return;
    var checks = wrap.querySelectorAll('input[type="checkbox"]:checked');
    if (checks.length === 0) {
      sum.textContent = "— pick sources —";
      sum.classList.add("mut");
      return;
    }
    sum.textContent = Array.prototype.map.call(checks, function (c) {
      return c.parentElement.querySelector("span").textContent.trim();
    }).join(", ");
    sum.classList.remove("mut");
  }

  function addTerm(form) {
    var list = form.querySelector("[data-terms-list]");
    var tpl = form.parentElement.querySelector("[data-term-template]")
      || document.querySelector("[data-term-template]");
    if (!list || !tpl || !tpl.content) return;
    var frag = tpl.content.cloneNode(true);
    var nextIdx = list.querySelectorAll("[data-term-row]").length;
    frag.querySelectorAll("[name]").forEach(function (el) {
      el.name = el.name.replace(/__IDX__/g, String(nextIdx));
    });
    list.appendChild(frag);
    list.querySelectorAll("[data-src-select]").forEach(syncSrcSummary);
  }

  function closeSrcPanels(except) {
    document.querySelectorAll("[data-recurring-form] [data-src-select]").forEach(function (wrap) {
      if (wrap === except) return;
      var panel = wrap.querySelector("[data-src-panel]");
      var trig = wrap.querySelector("[data-src-trigger]");
      if (panel && !panel.hasAttribute("hidden")) {
        panel.setAttribute("hidden", "");
        if (trig) trig.setAttribute("aria-expanded", "false");
      }
    });
  }

  function toggleSrcPanel(trig) {
    var wrap = trig.closest("[data-src-select]");
    var panel = wrap && wrap.querySelector("[data-src-panel]");
    if (!panel) return;
    var opening = panel.hasAttribute("hidden");
    if (opening) panel.removeAttribute("hidden"); else panel.setAttribute("hidden", "");
    trig.setAttribute("aria-expanded", opening ? "true" : "false");
  }

  document.addEventListener("click", function (evt) {
    var t = evt.target;
    if (!(t instanceof Element)) return;

    var add = t.closest("[data-term-add]");
    var addForm = add && formOf(add);
    if (addForm) { addTerm(addForm); return; }

    var rm = t.closest("[data-term-remove]");
    var row = rm && rm.closest("[data-term-row]");
    if (row) {
      var list = row.closest("[data-terms-list]");
      row.remove();
      if (list) reindex(list);
      return;
    }

    var trig = t.closest("[data-src-trigger]");
    if (trig) { toggleSrcPanel(trig); closeSrcPanels(trig.closest("[data-src-select]")); return; }
    closeSrcPanels(t.closest("[data-src-select]"));

    document.querySelectorAll("details[data-period-picker][open]").forEach(function (picker) {
      if (!picker.contains(t)) picker.open = false;
    });
  });

  document.addEventListener("change", function (evt) {
    var t = evt.target;
    if (!(t instanceof Element)) return;
    var wrap = t.closest("[data-recurring-form] [data-src-select]");
    if (wrap) syncSrcSummary(wrap);
    if (t.matches("[data-amount-source-radio]")) {
      var form = formOf(t);
      if (form) syncPanels(form);
    }
  });

  rdWire("[data-recurring-form]", function (form) {
    syncPanels(form);
    form.querySelectorAll("[data-src-select]").forEach(syncSrcSummary);
  });

  /* Recurring override form: month/year stepper + month grid. */
  var MONTHS = ["January", "February", "March", "April", "May", "June", "July",
    "August", "September", "October", "November", "December"];

  rdWire("[data-recurring-override-form]", function (form) {
    var yearInput = form.querySelector("[data-period-year]");
    var monthInput = form.querySelector("[data-period-month]");
    var label = form.querySelector("[data-period-label]");
    var hint = form.querySelector("[data-period-hint]");
    var picker = form.querySelector("[data-period-picker]");
    var yearDisplay = form.querySelector("[data-year-display]");
    var grid = form.querySelector("[data-month-grid]");
    if (!yearInput || !monthInput) return;

    function render() {
      var y = parseInt(yearInput.value, 10);
      var m = parseInt(monthInput.value, 10);
      if (isNaN(y) || isNaN(m)) return;
      var text = MONTHS[m - 1] + " " + y;
      if (label) label.textContent = text;
      if (hint) hint.textContent = text;
      if (yearDisplay) yearDisplay.textContent = String(y);
      if (grid) {
        grid.querySelectorAll("[data-month-cell]").forEach(function (btn) {
          var mm = parseInt(btn.getAttribute("data-month-cell"), 10);
          btn.classList.toggle("rd-period-nav__cell--active", mm === m);
        });
      }
    }
    function step(delta) {
      var y = parseInt(yearInput.value, 10);
      var m = parseInt(monthInput.value, 10) + delta;
      while (m < 1) { m += 12; y -= 1; }
      while (m > 12) { m -= 12; y += 1; }
      yearInput.value = String(y);
      monthInput.value = String(m);
      render();
    }
    function bind(sel, fn) {
      var el = form.querySelector(sel);
      if (el) el.addEventListener("click", fn);
    }
    function shiftYear(delta) {
      return function (ev) {
        ev.preventDefault();
        yearInput.value = String(parseInt(yearInput.value, 10) + delta);
        render();
      };
    }
    bind("[data-period-prev]", function () { step(-1); });
    bind("[data-period-next]", function () { step(1); });
    bind("[data-year-prev]", shiftYear(-1));
    bind("[data-year-next]", shiftYear(1));
    if (grid) {
      grid.addEventListener("click", function (ev) {
        var cell = ev.target.closest("[data-month-cell]");
        if (!cell) return;
        ev.preventDefault();
        monthInput.value = cell.getAttribute("data-month-cell");
        render();
        if (picker && picker.open) picker.open = false;
      });
    }
    render();
  });
})();
