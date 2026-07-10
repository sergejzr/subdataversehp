/*
 * logout-fix.js — shared logout repair for the static /at/<label> landing pages.
 *
 * Problem: the /at/ pages are static snapshots of a JSF view. Their "Log Out"
 * control calls mojarra.cljs(...) via inline onclick, but these pages never load
 * jsf.js/mojarra, so the click is a dead no-op (ReferenceError: mojarra is not
 * defined) and the user stays logged in.
 *
 * Fix: intercept the click and perform the logout ourselves. A real JSF logout is
 * a plain full-page form POST (NOT an ajax partial) with exactly three fields:
 *     <formId>                   = <formId>
 *     jakarta.faces.ViewState    = <live value>
 *     <formId>:lnk_header_logout = <formId>:lnk_header_logout
 * The static page's own ViewState is frozen/stale, so we fetch a LIVE one from the
 * matching /dataverse/<label> view at click time and replay it. (Validated on the
 * test instance: a freshly-fetched ViewState replayed in a hand-built POST performs
 * a real logout; a stale/mismatched one is rejected — hence "fetch fresh per click".)
 *
 * Self-contained, no dependencies. On any failure it falls back to the native
 * /dataverse/<label> page, where logout works normally — never a silent dead click.
 *
 * Robustness note: a third JS layer, /homepage/js/homepage.js (handleLogin()), rebuilds
 * the navbar login/logout markup client-side ~10s after load, restoring the original
 * inline onclick="mojarra.cljs(...)" on a freshly created DOM node. Anything we patched
 * onto the old node (a bound listener, a nulled onclick) is therefore lost. To be immune
 * to that, we do NOT touch the link node at all: we register a single delegated listener
 * on `document` in the CAPTURE phase, so we intercept the click before it can reach the
 * link's own (possibly just-restored) inline handler, no matter when the rebuild happens.
 *
 * On success we redirect to /at/<label>?loggedOut=1 and, on that load, show a brief
 * "Logged out successfully" toast, then scrub the query param via history.replaceState.
 */
(function () {
  'use strict';

  var LOGOUT_SUFFIX = ':lnk_header_logout';

  // Derive the collection label from the page path: /at/<label>/... -> <label>.
  function currentLabel() {
    var parts = location.pathname.split('/').filter(Boolean);
    if (parts[0] === 'at' && parts[1]) return parts[1];
    return null;
  }

  // Parse a fetched /dataverse/<label> HTML document for the live logout fields.
  function extractLogoutFields(html) {
    var doc = new DOMParser().parseFromString(html, 'text/html');
    var link = doc.querySelector('[id$="' + LOGOUT_SUFFIX + '"]');
    if (!link) return null;
    var form = link.closest('form');
    if (!form) return null;
    var vs = form.querySelector('input[name$="faces.ViewState"]');
    if (!vs || !vs.value) return null;
    var formId = form.id || link.id.slice(0, link.id.length - LOGOUT_SUFFIX.length);
    if (!formId) return null;
    return { formId: formId, logoutId: link.id, vsName: vs.name, vsValue: vs.value };
  }

  // Fetch a live ViewState and POST the logout. Returns true on success.
  function performLogout(label) {
    var view = '/dataverse/' + label;
    return fetch(view, { credentials: 'same-origin' })
      .then(function (res) {
        if (!res.ok) throw new Error('GET ' + view + ' -> ' + res.status);
        return res.text();
      })
      .then(function (html) {
        var f = extractLogoutFields(html);
        if (!f) throw new Error('could not extract live logout fields');
        var body = new URLSearchParams();
        body.set(f.formId, f.formId);
        body.set(f.vsName, f.vsValue);
        body.set(f.logoutId, f.logoutId);
        return fetch(view, {
          method: 'POST',
          credentials: 'same-origin',
          headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
          redirect: 'manual',
          body: body.toString()
        });
      })
      .then(function (res) {
        // A real logout answers with a 3xx redirect. With redirect:'manual' that
        // surfaces as an opaqueredirect (status 0); anything else (e.g. a 500 error
        // page from a rejected ViewState) is treated as failure.
        var ok = res.type === 'opaqueredirect' || (res.status >= 200 && res.status < 400);
        if (!ok) throw new Error('logout POST -> ' + res.status);
        return true;
      });
  }

  // Delegated, capture-phase click handler on `document`. Runs before the logout
  // link's own inline handler (and before default #-navigation), and survives the
  // navbar being re-rendered — see the Robustness note at the top of this file.
  function onDocumentClickCapture(event) {
    var target = event.target;
    var link = target && target.closest ? target.closest('[id$="' + LOGOUT_SUFFIX + '"]') : null;
    if (!link) return; // not a logout click — leave every other click untouched

    var label = currentLabel();
    if (!label) return; // not an /at/<label> page we can service — let the click proceed

    // Stop the event synchronously, before any async work below, so neither the
    // target's (possibly just-restored) inline mojarra.cljs(...) handler nor the
    // default anchor navigation ever runs.
    event.preventDefault();
    event.stopImmediatePropagation();

    performLogout(label)
      .then(function () { location.href = '/at/' + label + '?loggedOut=1'; })
      .catch(function (err) {
        // Never leave the user on a dead click: hand off to the native view,
        // where the JSF logout works normally.
        if (window.console && console.warn) console.warn('logout-fix: ' + err + ' — falling back to native logout');
        location.href = '/dataverse/' + label;
      });
  }

  // ---- Success toast --------------------------------------------------------
  // After a successful logout we redirect to /at/<label>?loggedOut=1; on that next
  // page load we show a brief confirmation, then scrub the param so a refresh or a
  // shared link never re-triggers it. Fully self-contained (inline styles, no deps).
  function showToast(message) {
    var host = document.body || document.documentElement;
    if (!host) return;
    var t = document.createElement('div');
    t.setAttribute('role', 'status');
    t.textContent = message;
    var s = t.style;
    s.position = 'fixed';
    s.top = '20px';
    s.right = '20px';
    s.zIndex = '2147483647';
    s.maxWidth = '80vw';
    s.padding = '10px 16px';
    s.background = '#2e7d32';
    s.color = '#fff';
    s.font = '14px/1.4 -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif';
    s.borderRadius = '6px';
    s.boxShadow = '0 2px 10px rgba(0,0,0,0.25)';
    // Paint at full opacity IMMEDIATELY so visibility never depends on a later
    // frame. The earlier version mounted at opacity:0 and only flipped to 1 inside
    // a single requestAnimationFrame; if that frame's style flush lost the race
    // (observed only in Firefox — the toast stayed invisible on the /at/ page even
    // though the redirect and DOM insertion had succeeded), the toast never showed.
    // Now the fade is a purely cosmetic transform slide: even if it never runs, the
    // toast is already visible.
    s.opacity = '1';
    s.transform = 'translateY(-6px)';
    s.transition = 'transform 0.25s ease, opacity 0.4s ease';
    s.willChange = 'transform';
    s.pointerEvents = 'none';
    host.appendChild(t);
    void t.offsetHeight;                    // commit the start state before transitioning
    // settle in on the next frame, hold ~3s, fade out, then remove
    requestAnimationFrame(function () { s.transform = 'translateY(0)'; });
    setTimeout(function () {
      s.opacity = '0';
      setTimeout(function () { if (t.parentNode) t.parentNode.removeChild(t); }, 500);
    }, 3000);
  }

  function maybeShowLogoutToast() {
    if (!/[?&]loggedOut=1(?:&|$)/.test(location.search)) return;
    // Show the toast FIRST, then scrub the query (the /at/ page has no other params
    // worth keeping) so a reload or shared URL doesn't re-show it. Ordering matters:
    // the toast must be mounted before any replaceState/re-render can intervene.
    showToast('Logged out successfully');
    try { history.replaceState(null, '', location.pathname + location.hash); } catch (e) {}
  }

  document.addEventListener('click', onDocumentClickCapture, true);

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', maybeShowLogoutToast);
  } else {
    maybeShowLogoutToast();
  }
})();
