/* ═══════════════════════════════════════════════════════════
   WHICH BUILDING IS THIS?

   The backend routes for exactly one facility, chosen by the SITE environment
   variable at container start and never at runtime. Until now nothing on screen
   said which, so a safety officer looking at the dashboard could not tell
   whether the evacuation routes being generated described the home layout or
   the industrial unit -- and the two have different rooms, different exits and
   a different hazard radius. A correct route drawn for the wrong building is
   the failure this badge exists to make visible.

   IT IS A READOUT, NOT A CONTROL. Changing the site means restarting the
   service with a different SITE value, because the graph, the exits and the
   ground truth all come from one file loaded at import. Rendering it as a
   dropdown would promise something the architecture does not offer.

   NOT THE SAME THING AS THE DETECTION SETTING, WHICH ALSO SAYS "HOME". The
   dropdown beside this one asks what counts as a fire -- a candle is a fire in
   a demonstration and an ordinary object in a canteen. That is an operator's
   choice about the camera. This is which building the routing graph describes.
   Two independent axes that happen to share the words "home" and "industrial",
   which is precisely why they are drawn differently and why a disagreement
   between them is called out rather than left for someone to notice.

   Shared by every page: the dashboard, the reports page and the ablation page
   all carry a .topbar-right, so one script keeps the three from drifting.
═══════════════════════════════════════════════════════════ */
(function () {
  'use strict';

  var ICON = {
    // A house, and a factory with a chimney. The shape carries the meaning at a
    // glance; the text is there for anyone who does not read icons.
    home: 'M12 3 2 11h3v9h5v-6h4v6h5v-9h3L12 3Z',
    industrial: 'M2 20V10l5 3V10l5 3V10l5 3V4h3v16H2Zm3-2h14v-3H5v3Z',
  };

  function el(tag, cls, text) {
    var n = document.createElement(tag);
    if (cls) n.className = cls;
    if (text != null) n.textContent = text;
    return n;
  }

  function svg(path) {
    var s = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
    s.setAttribute('viewBox', '0 0 24 24');
    s.setAttribute('aria-hidden', 'true');
    var p = document.createElementNS('http://www.w3.org/2000/svg', 'path');
    p.setAttribute('d', path);
    s.appendChild(p);
    return s;
  }

  function render(plan) {
    var bar = document.querySelector('.topbar-right');
    if (!bar) return;

    var key = (plan && plan.siteKey) || 'unknown';
    var known = key === 'home' || key === 'industrial';

    var badge = el('div', 'site-badge site-' + (known ? key : 'unknown'));
    badge.id = 'site-badge';
    badge.appendChild(svg(ICON[key] || ICON.industrial));

    var stack = el('div', 'site-badge-text');
    stack.appendChild(el('span', 'site-badge-label', 'FACILITY'));
    stack.appendChild(el('span', 'site-badge-name',
      (plan && plan.siteName) || 'Unknown site'));
    badge.appendChild(stack);

    /* The revision matters more than it looks. A route is validated against the
       plan revision it was generated under, so "which building" and "which
       version of that building" are both part of reading a stored result. */
    badge.title = known
      ? 'Routing for ' + plan.siteName + ' (' + key + ', plan ' + plan.revision +
        '). Set by SITE at start-up; restart the service to change it.'
      : 'The backend did not report a recognised site.';

    bar.appendChild(badge);
    flagMismatch(key, badge);
  }

  /* The detection setting is an independent axis with its own default, and the
     two disagreeing is a real condition rather than a cosmetic one: it means
     the camera is being judged by one building's definition of fire while the
     evacuation routes describe another. Neither value is wrong on its own, so
     this warns and does not correct. */
  function flagMismatch(siteKey, badge) {
    var sel = document.getElementById('detect-mode');
    if (!sel) return;
    function sync() {
      var differs = sel.value && siteKey !== 'unknown' && sel.value !== siteKey;
      badge.classList.toggle('site-badge-mismatch', !!differs);
      if (differs) {
        badge.title = 'The detection setting is "' + sel.value + '" but the ' +
          'routing graph is the ' + siteKey + ' site. That is allowed, but the ' +
          'two describe different buildings.';
      }
    }
    sel.addEventListener('change', sync);
    sync();
  }

  function load() {
    fetch('/api/site/plan')
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (plan) { render(plan); })
      // A badge that cannot reach the backend still renders, saying so. Showing
      // nothing would read as "no site selected" rather than "not reachable".
      .catch(function () { render(null); });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', load);
  } else {
    load();
  }
})();
