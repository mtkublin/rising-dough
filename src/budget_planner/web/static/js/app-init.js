/* App bootstrap (was inline in base.html; moved for the strict prod CSP, ADR-0113). */
(function () {
        window.__TODAY_LOCAL__ = document.body.dataset.todayLocal || "";
        document.body.addEventListener("htmx:beforeSwap", function (evt) {
          if (evt.detail.xhr && (evt.detail.xhr.status === 422 || evt.detail.xhr.status === 429)) {
            // 429: throttled form re-render (T-D18a, ADR-0072)
            evt.detail.shouldSwap = true;
            evt.detail.isError = false;
          }
        });
        document.body.addEventListener("htmx:afterRequest", function (evt) {
          var detail = evt.detail || {};
          var xhr = detail.xhr;
          if (!xhr || xhr.status < 200 || xhr.status >= 300) return;
          var form = evt.target;
          if (!(form instanceof HTMLFormElement)) return;
          if (!form.hasAttribute("data-reset-on-submit")) return;
          var verb = (detail.requestConfig && detail.requestConfig.verb) || "";
          if (["post", "put", "delete"].indexOf(verb.toLowerCase()) === -1) return;
          form.reset();
          form.querySelectorAll("input[data-default-today]").forEach(function (i) {
            i.value = window.__TODAY_LOCAL__ || "";
          });
          form.querySelectorAll("[data-combobox-input]").forEach(function (i) {
            i.value = i.dataset.initialLabel || "";
          });
          form.querySelectorAll("[data-combobox-value]").forEach(function (i) {
            i.value = "";
          });
          var slide = form.closest(".slide-over-root");
          if (slide && slide.parentElement) {
            slide.parentElement.innerHTML = "";
          }
        });
        /* Toast handler via HX-Trigger. */
        document.body.addEventListener("toast", function (e) {
          var d = e.detail || {};
          var root = document.getElementById("toast-root");
          if (!root) return;
          var el = document.createElement("div");
          el.className = "rd-toast rd-toast--" + (d.kind || "info");
          el.innerHTML = '<span>' + (d.message || "") + '</span>';
          if (d.undo_href) {
            var btn = document.createElement("button");
            btn.className = "rd-toast__undo";
            btn.textContent = "Undo";
            btn.addEventListener("click", function () {
              htmx.ajax("POST", d.undo_href, { target: "body", swap: "none" });
              el.remove();
            });
            el.appendChild(btn);
          }
          root.appendChild(el);
          setTimeout(function () { el.remove(); }, 4000);
        });
        /* View Transitions default. */
        if (document.startViewTransition && !window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
          document.body.addEventListener("htmx:beforeSwap", function (evt) {
            if (!evt.detail || !evt.detail.xhr) return;
            var swap = evt.detail.target && evt.detail.target.getAttribute && evt.detail.target.getAttribute("hx-swap") || "";
            if (swap.indexOf("transition:true") !== -1) {
              evt.detail.doSwap = function (f) { document.startViewTransition(f); };
            }
          });
        }
})();
