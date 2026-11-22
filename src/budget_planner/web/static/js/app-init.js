/* App bootstrap (was inline in base.html; moved for the strict prod CSP, ADR-0113). */
(function () {
        window.__TODAY_LOCAL__ = document.body.dataset.todayLocal || "";
        /* Error contract (ADR-0142): every 4xx/5xx shows a visible flash. */
        var FLASH_ONLY = /^\s*<div\s+id="flash-region(-assertive)?"/;
        var STATUS_TEXT = {
          400: "The request was not accepted. Check the form and try again.",
          401: "Your session has expired. Reload the page and sign in again.",
          403: "The request was refused. Reload the page and try again.",
          404: "That item was not found. It may have been removed.",
          409: "That item changed in the meantime. Reload and try again.",
          503: "A required service is unavailable. Try again shortly."
        };
        function showFlash(message) {
          var root = document.getElementById("flash-region-assertive");
          if (!root) return;
          root.textContent = "";
          var box = document.createElement("div");
          box.className = "flash flash-error";
          box.setAttribute("data-flash-kind", "error");
          var msg = document.createElement("span");
          msg.textContent = message;
          var btn = document.createElement("button");
          btn.type = "button";
          btn.className = "flash-dismiss";
          btn.setAttribute("aria-label", "Dismiss message");
          btn.setAttribute("data-action", "dismiss-flash");
          btn.textContent = "\u00d7";
          box.appendChild(msg);
          box.appendChild(btn);
          root.appendChild(box);
        }
        document.body.addEventListener("htmx:beforeSwap", function (evt) {
          var xhr = evt.detail.xhr;
          if (!xhr || xhr.status < 400) return;
          var text = xhr.responseText || "";
          if (FLASH_ONLY.test(text)) {
            /* Server flash partial: swap only its out-of-band region, leave the target alone. */
            evt.detail.shouldSwap = true;
            evt.detail.isError = false;
            evt.detail.swapOverride = "none";
          } else if (xhr.status === 422 || xhr.status === 429) {
            /* Form re-render (429: throttled, T-D18a, ADR-0072). */
            evt.detail.shouldSwap = true;
            evt.detail.isError = false;
          } else {
            evt.detail.shouldSwap = false;
            showFlash(STATUS_TEXT[xhr.status] || "Something went wrong on our side. Try again.");
          }
        });
        document.body.addEventListener("htmx:sendError", function () {
          showFlash("Could not reach the server. Check your connection and try again.");
        });
        document.body.addEventListener("htmx:timeout", function () {
          showFlash("The server took too long to respond. Try again.");
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
          el.className = "rd-toast rd-toast--" + (d.variant || "info");
          var msg = document.createElement("span");
          msg.textContent = d.message || "";
          el.appendChild(msg);
          if (d.undo_url) {
            var btn = document.createElement("button");
            btn.type = "button";
            btn.className = "rd-toast__undo";
            btn.textContent = "Undo";
            btn.addEventListener("click", function () {
              /* Undo endpoints read CSV form fields; join array payload values. */
              var values = {};
              var payload = d.undo_payload || {};
              Object.keys(payload).forEach(function (k) {
                values[k] = Array.isArray(payload[k]) ? payload[k].join(",") : payload[k];
              });
              /* Reload only once the undo succeeded (ADR-0142). */
              var undone = false;
              function onUndo(e) {
                var cfg = e.detail && e.detail.requestConfig;
                if (cfg && cfg.path === d.undo_url) undone = e.detail.successful === true;
              }
              document.body.addEventListener("htmx:afterRequest", onUndo);
              htmx.ajax("POST", d.undo_url, { target: "body", swap: "none", values: values }).then(function () {
                document.body.removeEventListener("htmx:afterRequest", onUndo);
                if (undone) window.location.reload();
              }, function () {
                document.body.removeEventListener("htmx:afterRequest", onUndo);
              });
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
