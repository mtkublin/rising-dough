/* T-R38: keep the amount field's currency suffix in sync with the picked
 * account. The currency map comes from data-account-currencies (JSON). */
(function () {
  rdWire("[data-txn-form]", function (form) {
    var suffix = form.querySelector("[data-currency-suffix]");
    var acctHidden = form.querySelector("input[type='hidden'][name='account_id']");
    if (!suffix) return;
    var map = {};
    try { map = JSON.parse(form.getAttribute("data-account-currencies") || "{}"); } catch (e) { map = {}; }
    function sync() {
      var id = acctHidden && acctHidden.value;
      suffix.setAttribute("data-suffix", id ? (map[id] || "") : "");
    }
    if (acctHidden) {
      form.addEventListener("input", sync);
      form.addEventListener("change", sync);
    }
    sync();
  });
})();
