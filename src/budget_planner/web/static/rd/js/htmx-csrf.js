/* T-D08 — HTMX CSRF extension.
 *
 * Reads the CSRF token from `<meta name="csrf-token">` (rendered by
 * base.html from `request.state.csrf_token`) and attaches it as the
 * `X-CSRF-Token` header on every HTMX-initiated request. Reading the meta
 * tag instead of `document.cookie` keeps the JS independent of the cookie
 * name, which differs between dev (`csrf`) and other envs (`__Host-csrf`)
 * — see ADR-0065.
 *
 * Install:
 *   <meta name="csrf-token" content="{{ csrf_token }}">
 *   <script src="/static/rd/js/csrf.js" defer></script>   (shared token reader)
 *   <script src="/static/rd/js/htmx-csrf.js" defer></script>
 *   <body hx-ext="csrf">
 *
 * The extension is a no-op on GET/HEAD/OPTIONS (safe methods); the server
 * only enforces the token on POST/PUT/PATCH/DELETE anyway, but trimming
 * the header on safe requests keeps the wire quieter.
 */

(function () {
  "use strict";

  var HEADER_NAME = "X-CSRF-Token";
  var UNSAFE = { POST: 1, PUT: 1, PATCH: 1, DELETE: 1 };

  if (typeof window === "undefined" || !window.htmx) {
    // htmx not loaded yet — bail. Rely on `defer` ordering.
    return;
  }

  // T-UR04 (ADR-0107 section 3): a 422 carries the dialog re-rendered with its
  // error summary and aria-invalid fields. HTMX skips 4xx bodies by default, so
  // let the 422 swap in (the server sets HX-Retarget / HX-Reswap on it).
  document.addEventListener("htmx:beforeSwap", function (evt) {
    var detail = evt.detail || {};
    if (detail.xhr && detail.xhr.status === 422) {
      detail.shouldSwap = true;
      detail.isError = false;
    }
  });

  window.htmx.defineExtension("csrf", {
    onEvent: function (name, evt) {
      if (name !== "htmx:configRequest") return;
      var detail = evt.detail || {};
      var verb = (detail.verb || "").toUpperCase();
      if (!UNSAFE[verb]) return;
      var token = window.budgetCsrf && window.budgetCsrf.token();
      if (!token) return;
      detail.headers = detail.headers || {};
      detail.headers[HEADER_NAME] = token;
    },
  });
})();
