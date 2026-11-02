/* T-D08 — HTMX CSRF extension.
 *
 * Reads the `__Host-csrf` cookie (set by CSRFMiddleware) and attaches it
 * as the `X-CSRF-Token` header on every HTMX-initiated request. The
 * cookie is intentionally non-HttpOnly so this extension can read it;
 * the double-submit pattern makes JS readability safe (the token is a
 * nonce, not a credential — see ADR-0033 §4).
 *
 * Install:
 *   <script src="/static/htmx-csrf.js" defer></script>
 *   <body hx-ext="csrf">
 *
 * The extension is a no-op on GET/HEAD/OPTIONS (safe methods); the server
 * only enforces the token on POST/PUT/PATCH/DELETE anyway, but trimming
 * the header on safe requests keeps the wire quieter.
 */

(function () {
  "use strict";

  var COOKIE_NAME = "__Host-csrf";
  var HEADER_NAME = "X-CSRF-Token";
  var UNSAFE = { POST: 1, PUT: 1, PATCH: 1, DELETE: 1 };

  function readCookie(name) {
    var cookies = document.cookie ? document.cookie.split("; ") : [];
    for (var i = 0; i < cookies.length; i += 1) {
      var eq = cookies[i].indexOf("=");
      if (eq === -1) continue;
      if (cookies[i].slice(0, eq) === name) {
        return decodeURIComponent(cookies[i].slice(eq + 1));
      }
    }
    return null;
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
      var token = readCookie(COOKIE_NAME);
      if (!token) return;
      detail.headers = detail.headers || {};
      detail.headers[HEADER_NAME] = token;
    },
  });
})();
