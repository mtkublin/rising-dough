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
 *   <script src="/static/htmx-csrf.js" defer></script>
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

  function readToken() {
    var meta = document.querySelector('meta[name="csrf-token"]');
    var token = meta ? meta.getAttribute("content") : "";
    return token || null;
  }

  if (typeof window === "undefined" || !window.htmx) {
    // htmx not loaded yet — bail. Rely on `defer` ordering.
    return;
  }

  window.htmx.defineExtension("csrf", {
    onEvent: function (name, evt) {
      if (name !== "htmx:configRequest") return;
      var detail = evt.detail || {};
      var verb = (detail.verb || "").toUpperCase();
      if (!UNSAFE[verb]) return;
      var token = readToken();
      if (!token) return;
      detail.headers = detail.headers || {};
      detail.headers[HEADER_NAME] = token;
    },
  });
})();
