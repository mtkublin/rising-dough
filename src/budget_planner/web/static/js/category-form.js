/* T-R66: category form live preview + swatch/segmented selection state. */
(function () {
  var FALLBACK = { income: "#2f8f5a", expense: "#c9403a", transit: "#3b7fa3", adjustment: "#8a7a90" };
  var DIR_LABEL = { income: "↑ income", expense: "↓ expense", transit: "⇄ transit" };

  rdWire("[data-cat-form]", function (form) {
    var nameInput = form.querySelector("[data-cat-name]");
    var dirInputs = form.querySelectorAll("[data-cat-dir]");
    var defaultRadio = form.querySelector("[data-cat-color-default]");
    var swatchRadios = form.querySelectorAll("[data-cat-color-swatch]");
    var clearInput = form.querySelector("[data-cat-clear]");
    var previewPill = form.querySelector("[data-cat-preview-pill]");
    var previewDir = form.querySelector("[data-cat-preview-dir]");

    function activeDirection() {
      var checked = form.querySelector("[data-cat-dir]:checked");
      if (checked) return checked.value;
      var hidden = form.querySelector("input[type='hidden'][data-cat-dir]");
      return hidden ? hidden.value : "expense";
    }
    function activeColor() {
      if (defaultRadio && defaultRadio.checked) return null;
      var picked = form.querySelector("[data-cat-color-swatch]:checked");
      return picked ? picked.value : null;
    }
    function syncClear() {
      if (clearInput) clearInput.checked = !!(defaultRadio && defaultRadio.checked);
    }
    function toggleActive(selector, cls) {
      form.querySelectorAll(selector).forEach(function (label) {
        var input = label.querySelector("input[type='radio']");
        label.classList.toggle(cls, !!(input && input.checked));
      });
    }
    function syncSelected() {
      toggleActive(".rd-swatch, .rd-swatches__default", "is-selected");
      toggleActive(".rd-segmented__item", "rd-segmented__item--active");
    }
    function syncPreview() {
      var name = (nameInput && nameInput.value.trim()) || "name";
      var dir = activeDirection();
      var color = activeColor() || FALLBACK[dir];
      if (previewPill) {
        previewPill.textContent = name;
        previewPill.setAttribute("style",
          "background: color-mix(in oklab, " + color + " 16%, transparent); color: " + color);
      }
      if (previewDir) {
        previewDir.className = "rd-dir rd-dir--" + dir;
        previewDir.textContent = DIR_LABEL[dir] || "⟲ adjust";
      }
    }
    function syncAll() { syncClear(); syncSelected(); syncPreview(); }

    if (nameInput) nameInput.addEventListener("input", syncPreview);
    dirInputs.forEach(function (i) {
      i.addEventListener("change", function () { syncSelected(); syncPreview(); });
    });
    if (defaultRadio) defaultRadio.addEventListener("change", syncAll);
    swatchRadios.forEach(function (r) { r.addEventListener("change", syncAll); });
    syncAll();
  });
})();
