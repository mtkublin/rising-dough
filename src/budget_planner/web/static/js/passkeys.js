/* T-D02b — passkey (WebAuthn) ceremonies for /auth/login and /auth/register.
 *
 * No inline script (CSP, ADR-0036 §3): this file binds to
 *   [data-passkey-login]     button on the login page
 *   form[data-passkey-register] on the add-a-passkey page
 *   [data-passkey-status]    live region for progress / errors
 *
 * Flow (ADR-0067 §1, ADR-0070 §3): POST .../begin → server returns the
 * WebAuthn options JSON and sets a signed, 5-minute challenge cookie →
 * navigator.credentials.{get,create} → POST .../finish with the credential
 * serialised as base64url JSON → server answers {redirect} or {error}.
 * Every POST carries the CSRF token from <meta name="csrf-token">
 * (ADR-0065).
 */
(function () {
  "use strict";

  var CSRF_HEADER = "X-CSRF-Token";
  var GENERIC_LOGIN_ERROR = "Passkey sign-in didn't work. Try again or use your password.";

  function csrfToken() {
    var meta = document.querySelector('meta[name="csrf-token"]');
    return meta ? meta.getAttribute("content") || "" : "";
  }

  function toBytes(b64url) {
    var b64 = b64url.replace(/-/g, "+").replace(/_/g, "/");
    while (b64.length % 4) b64 += "=";
    var bin = atob(b64);
    var out = new Uint8Array(bin.length);
    for (var i = 0; i < bin.length; i++) out[i] = bin.charCodeAt(i);
    return out.buffer;
  }

  function toB64url(buffer) {
    if (!buffer) return null;
    var bytes = new Uint8Array(buffer);
    var bin = "";
    for (var i = 0; i < bytes.length; i++) bin += String.fromCharCode(bytes[i]);
    return btoa(bin).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
  }

  function setStatus(el, message, isError) {
    if (!el) return;
    el.textContent = message;
    el.classList.toggle("rd-auth__status--error", Boolean(isError));
  }

  function postJson(url, body) {
    var headers = { Accept: "application/json" };
    headers[CSRF_HEADER] = csrfToken();
    if (body !== undefined) headers["Content-Type"] = "application/json";
    return fetch(url, {
      method: "POST",
      credentials: "same-origin",
      headers: headers,
      body: body === undefined ? undefined : JSON.stringify(body),
    }).then(function (resp) {
      return resp.json().then(
        function (data) { return { ok: resp.ok, data: data || {} }; },
        function () { return { ok: resp.ok, data: {} }; }
      );
    });
  }

  function descriptors(list) {
    return (list || []).map(function (d) {
      return { type: d.type, id: toBytes(d.id), transports: d.transports };
    });
  }

  function serialise(cred, response) {
    return {
      id: cred.id,
      rawId: toB64url(cred.rawId),
      type: cred.type,
      authenticatorAttachment: cred.authenticatorAttachment || undefined,
      clientExtensionResults: cred.getClientExtensionResults ? cred.getClientExtensionResults() : {},
      response: response,
    };
  }

  function supported() {
    return Boolean(window.PublicKeyCredential && navigator.credentials);
  }

  function markUnsupported(el, status) {
    el.setAttribute("disabled", "");
    el.setAttribute("aria-disabled", "true");
    setStatus(status, "This browser doesn't support passkeys.", true);
  }

  /* ── Login ─────────────────────────────────────────────────────── */
  function bindLogin(button) {
    var status = document.querySelector("[data-passkey-status]");
    if (!supported()) return markUnsupported(button, status);
    button.addEventListener("click", function () {
      var next = button.getAttribute("data-next") || "/";
      button.setAttribute("aria-busy", "true");
      setStatus(status, "Waiting for your passkey…", false);
      postJson("/auth/login/begin")
        .then(function (res) {
          if (!res.ok) throw new Error("begin");
          var opts = res.data;
          opts.challenge = toBytes(opts.challenge);
          opts.allowCredentials = descriptors(opts.allowCredentials);
          return navigator.credentials.get({ publicKey: opts });
        })
        .then(function (cred) {
          var r = cred.response;
          return postJson(
            "/auth/login/finish?next=" + encodeURIComponent(next),
            serialise(cred, {
              clientDataJSON: toB64url(r.clientDataJSON),
              authenticatorData: toB64url(r.authenticatorData),
              signature: toB64url(r.signature),
              userHandle: toB64url(r.userHandle),
            })
          );
        })
        .then(function (res) {
          if (!res.ok || !res.data.redirect) throw new Error("finish");
          window.location.assign(res.data.redirect);
        })
        .catch(function () {
          setStatus(status, GENERIC_LOGIN_ERROR, true);
        })
        .finally(function () {
          button.removeAttribute("aria-busy");
        });
    });
  }

  /* ── Registration ──────────────────────────────────────────────── */
  var REGISTER_ERRORS = {
    challenge_expired: "That took too long. Please try again.",
    duplicate_credential: "This passkey is already registered.",
    invalid_response: "Your device's response couldn't be verified.",
  };

  function bindRegister(form) {
    var status = form.querySelector("[data-passkey-status]");
    var submit = form.querySelector('button[type="submit"]');
    if (!supported()) return markUnsupported(submit, status);
    form.addEventListener("submit", function (evt) {
      evt.preventDefault();
      var label = (form.elements.namedItem("label") || {}).value || "";
      submit.setAttribute("aria-busy", "true");
      submit.setAttribute("disabled", "");
      setStatus(status, "Follow the prompt on your device…", false);
      postJson("/auth/register/begin")
        .then(function (res) {
          if (!res.ok) throw new Error("begin");
          var opts = res.data;
          opts.challenge = toBytes(opts.challenge);
          opts.user.id = toBytes(opts.user.id);
          opts.excludeCredentials = descriptors(opts.excludeCredentials);
          return navigator.credentials.create({ publicKey: opts });
        })
        .then(function (cred) {
          var r = cred.response;
          return postJson("/auth/register/finish", {
            label: label,
            credential: serialise(cred, {
              clientDataJSON: toB64url(r.clientDataJSON),
              attestationObject: toB64url(r.attestationObject),
              transports: r.getTransports ? r.getTransports() : [],
            }),
          });
        })
        .then(function (res) {
          if (!res.ok || !res.data.redirect) {
            throw new Error(res.data.error || "finish");
          }
          window.location.assign(res.data.redirect);
        })
        .catch(function (err) {
          var msg = REGISTER_ERRORS[err && err.message] ||
            "The passkey wasn't added. You can try again.";
          setStatus(status, msg, true);
        })
        .finally(function () {
          submit.removeAttribute("aria-busy");
          submit.removeAttribute("disabled");
        });
    });
  }

  function init() {
    var login = document.querySelector("[data-passkey-login]");
    if (login) bindLogin(login);
    var register = document.querySelector("form[data-passkey-register]");
    if (register) bindRegister(register);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
