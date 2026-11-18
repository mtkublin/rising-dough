/* Idempotent per-element wiring for HTMX-swapped markup (T-D140b, ADR-0113).
 * rdWire(selector, fn): runs fn(el) once per matching element, on initial
 * load and for every subtree HTMX swaps in (htmx:load). No inline script. */
(function () {
  if (window.rdWire) return;
  var seen = new WeakMap();

  function scan(root, selector, fn) {
    if (!root || !root.querySelectorAll) return;
    var found = Array.prototype.slice.call(root.querySelectorAll(selector));
    if (root.matches && root.matches(selector)) found.unshift(root);
    found.forEach(function (el) {
      var done = seen.get(el) || {};
      if (done[selector]) return;
      done[selector] = true;
      seen.set(el, done);
      fn(el);
    });
  }

  window.rdWire = function (selector, fn) {
    function initial() { scan(document, selector, fn); }
    if (document.readyState === "loading") {
      document.addEventListener("DOMContentLoaded", initial);
    } else {
      initial();
    }
    document.addEventListener("htmx:load", function (evt) {
      scan(evt.target, selector, fn);
    });
  };
})();
