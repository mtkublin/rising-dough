/* T-123 credit-limit lockstep + T-R65 currency-suffix sync (account form). */
(function () {
  function syncLimit(cb, field, limitInput) {
    var on = cb.checked;
    if (on) { field.removeAttribute("hidden"); field.removeAttribute("aria-hidden"); }
    else { field.setAttribute("hidden", ""); field.setAttribute("aria-hidden", "true"); }
    field.style.display = on ? "" : "none";
    if (limitInput) limitInput.disabled = !on;
  }

  function syncSuffixes(form) {
    var hidden = form.querySelector("input[type='hidden'][name='currency']");
    var disabledInput = form.querySelector("input[name='currency']:disabled, input[type='text'][disabled][aria-describedby='rd-currency-help']");
    var ccy = (hidden && hidden.value) || (disabledInput && disabledInput.value) || "";
    form.querySelectorAll("[data-currency-suffix]").forEach(function (el) {
      el.setAttribute("data-suffix", ccy);
    });
  }

  rdWire("[data-account-form]", function (form) {
    var cb = form.querySelector("[data-toggle-limit]");
    var field = form.querySelector("[data-limit-field]");
    var limitInput = field && field.querySelector("input[name='credit_limit']");
    if (cb && field) {
      cb.addEventListener("change", function () { syncLimit(cb, field, limitInput); });
      syncLimit(cb, field, limitInput);
    }
    var hasCurrencyHidden = form.querySelector("input[type='hidden'][name='currency']");
    var visible = hasCurrencyHidden && form.querySelector("input[role='combobox']");
    if (visible) {
      ["input", "change", "blur"].forEach(function (name) {
        visible.addEventListener(name, function () { syncSuffixes(form); });
      });
    }
    syncSuffixes(form);
  });
})();
