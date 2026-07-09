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

  function onLogoutClick(label, event) {
    event.preventDefault();
    performLogout(label)
      .then(function () { location.href = '/at/' + label; })
      .catch(function (err) {
        // Never leave the user on a dead click: hand off to the native view,
        // where the JSF logout works normally.
        if (window.console && console.warn) console.warn('logout-fix: ' + err + ' — falling back to native logout');
        location.href = '/dataverse/' + label;
      });
  }

  function init() {
    var link = document.querySelector('[id$="' + LOGOUT_SUFFIX + '"]');
    if (!link) return; // no logout control on this page (e.g. logged-out state)
    var label = currentLabel();
    if (!label) return; // not an /at/<label> page we can service

    // Neutralise the dead inline mojarra.cljs(...) handler, then own the click.
    link.onclick = null;
    link.removeAttribute('onclick');
    link.addEventListener('click', function (e) { onLogoutClick(label, e); });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
