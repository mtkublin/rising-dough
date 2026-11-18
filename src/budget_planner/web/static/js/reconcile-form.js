/* T-R39: live Difference callout + Record button amount (reconcile modal). */
(function () {
  rdWire("[data-reconcile-form]", function (form) {
    var ccy = form.dataset.currency || "";
    var decimals = parseInt(form.dataset.decimals || "2", 10);
    var scale = Math.pow(10, decimals);
    var derivedMinor = parseInt(form.dataset.derived || "0", 10);
    var limitMinor = form.dataset.byAvailable === "1" ? parseInt(form.dataset.limit || "0", 10) : null;
    var usedEl = form.querySelector("[data-reconcile-used]");
    var input = form.querySelector("[data-reconcile-actual]");
    var delta = form.querySelector("[data-reconcile-delta]");
    var amountEl = form.querySelector("[data-reconcile-delta-amount]");
    var submitBtn = form.querySelector("[data-reconcile-submit]");
    if (!input) return;
    function parseMajor(v) {
      if (!v) return null;
      var n = parseFloat(v.toString().replace(",", ".").trim());
      return Number.isFinite(n) ? n : null;
    }
    function fmt(n) {
      return n.toLocaleString("en-US", { minimumFractionDigits: decimals, maximumFractionDigits: decimals });
    }
    function sync() {
      var val = parseMajor(input.value);
      if (val === null) {
        if (delta) delta.setAttribute("hidden", "");
        if (submitBtn) submitBtn.textContent = "Record ↩";
        return;
      }
      var target = limitMinor === null ? val : val - (limitMinor / scale);
      if (usedEl && limitMinor !== null) usedEl.textContent = fmt(Math.max(limitMinor / scale - val, 0));
      var deltaMajor = (Math.round(target * scale) - derivedMinor) / scale;
      var sign = deltaMajor > 0 ? "+" : (deltaMajor < 0 ? "−" : "");
      var absAmount = fmt(Math.abs(deltaMajor));
      if (amountEl) amountEl.textContent = sign + absAmount + " " + ccy;
      if (delta) delta.removeAttribute("hidden");
      if (submitBtn) submitBtn.textContent = "Record " + (deltaMajor === 0 ? fmt(0) : sign + absAmount) + " ↩";
    }
    input.addEventListener("input", sync);
    sync();
  });
})();
