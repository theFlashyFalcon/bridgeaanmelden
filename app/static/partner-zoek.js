/*
 * Naam/nummer-zoekdropdown voor partnervelden. Velden krijgen dit door een
 * data-partner-zoek + data-achternaam-id attribuut te zetten op het
 * voornaamveld (zie registrations/start.html en index.html).
 *
 * - Typen (naam of NBB-nummer) toont een dropdown met matches uit de
 *   ledenlijst van de eigen club(s), favorieten eerst.
 * - Klikken op een resultaat vult voornaam + achternaam.
 * - Klikken op het sterretje maakt/verwijdert een favoriet, zonder de
 *   velden te vullen.
 * - Focus op een leeg veld toont meteen de favorieten.
 */
(function () {
  var paneel = null;
  var actieveInput = null;
  var actieveAchternaamInput = null;
  var zoekTimer = null;
  var laatsteQuery = null;

  function csrfTokenVoor(input) {
    // Het CSRF-token is sessiegebonden, niet formuliergebonden — een token
    // dat ergens anders op de pagina staat (bv. niet in hetzelfde <form>,
    // zoals bij de bulk-aanmeldvelden) werkt net zo goed.
    var form = input.closest('form');
    var veld = (form && form.querySelector('input[name="_csrf_token"]'))
      || document.querySelector('input[name="_csrf_token"]');
    return veld ? veld.value : '';
  }

  function sluitPaneel() {
    if (paneel) paneel.hidden = true;
    actieveInput = null;
    actieveAchternaamInput = null;
  }

  function positioneerPaneel(input) {
    var rect = input.getBoundingClientRect();
    paneel.style.position = 'fixed';
    paneel.style.left = rect.left + 'px';
    paneel.style.top = rect.bottom + 'px';
    paneel.style.width = Math.max(rect.width, 220) + 'px';
  }

  function maakItem(persoon, isFavoriet) {
    var item = document.createElement('div');
    item.className = 'partner-zoek-item';
    item.style.cssText = 'display:flex;align-items:center;justify-content:space-between;' +
      'padding:.4rem .6rem;cursor:pointer;gap:.5rem;';

    var tekst = document.createElement('span');
    tekst.textContent = persoon.voornaam + ' ' + persoon.achternaam +
      (persoon.nummer ? ' (' + persoon.nummer + ')' : '');
    tekst.style.cssText = 'overflow:hidden;text-overflow:ellipsis;white-space:nowrap;';
    item.appendChild(tekst);

    var ster = document.createElement('button');
    ster.type = 'button';
    ster.className = 'partner-zoek-ster';
    ster.setAttribute('aria-label', isFavoriet ? 'Verwijder als favoriet' : 'Maak favoriet');
    ster.textContent = isFavoriet ? '★' : '☆';
    ster.style.cssText = 'background:none;border:none;cursor:pointer;font-size:1.1rem;' +
      'line-height:1;padding:.15rem .3rem;flex-shrink:0;color:#c9a227;';
    item.appendChild(ster);

    item.addEventListener('mousedown', function (e) {
      // mousedown i.p.v. click, zodat dit vóór de blur van het inputveld vuurt
      if (e.target === ster) return;
      e.preventDefault();
      if (actieveInput) actieveInput.value = persoon.voornaam;
      if (actieveAchternaamInput) actieveAchternaamInput.value = persoon.achternaam;
      sluitPaneel();
    });

    ster.addEventListener('mousedown', function (e) {
      e.preventDefault();
      e.stopPropagation();
      var input = actieveInput;
      var token = csrfTokenVoor(input);
      fetch('/partners/favorieten/toggle', {
        method: 'POST',
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
        body: new URLSearchParams({
          voornaam: persoon.voornaam,
          achternaam: persoon.achternaam,
          nummer: persoon.nummer || '',
          _csrf_token: token,
        }),
      })
        .then(function (r) { return r.json(); })
        .then(function (data) {
          ster.textContent = data.favoriet ? '★' : '☆';
          ster.setAttribute('aria-label', data.favoriet ? 'Verwijder als favoriet' : 'Maak favoriet');
        })
        .catch(function () {});
    });

    return item;
  }

  function toonResultaten(data) {
    paneel.innerHTML = '';
    var favorietNamen = {};
    (data.favorieten || []).forEach(function (f) {
      favorietNamen[(f.voornaam + '|' + f.achternaam).toLowerCase()] = true;
    });

    var alles = (data.favorieten || []).map(function (f) { return { p: f, fav: true }; })
      .concat((data.resultaten || []).map(function (r) { return { p: r, fav: false }; }));

    if (!alles.length) {
      var leeg = document.createElement('div');
      leeg.style.cssText = 'padding:.5rem .6rem;color:var(--color-muted);font-size:.85rem;';
      leeg.textContent = 'Geen namen gevonden.';
      paneel.appendChild(leeg);
    } else {
      alles.forEach(function (entry) { paneel.appendChild(maakItem(entry.p, entry.fav)); });
    }
    paneel.hidden = false;
  }

  function zoek(input) {
    var q = input.value.trim();
    if (q === laatsteQuery) return;
    laatsteQuery = q;
    fetch('/partners/zoek?q=' + encodeURIComponent(q))
      .then(function (r) { return r.json(); })
      .then(function (data) {
        if (actieveInput === input) toonResultaten(data);
      })
      .catch(function () {});
  }

  function init() {
    paneel = document.createElement('div');
    paneel.className = 'partner-zoek-paneel';
    paneel.hidden = true;
    paneel.style.cssText = 'z-index:1000;background:var(--color-bg,#fff);' +
      'border:1px solid var(--color-border,#ccc);border-radius:var(--radius,6px);' +
      'box-shadow:0 4px 12px rgba(0,0,0,.15);max-height:220px;overflow-y:auto;';
    document.body.appendChild(paneel);

    var velden = document.querySelectorAll('input[data-partner-zoek]');
    velden.forEach(function (input) {
      var achternaamId = input.getAttribute('data-achternaam-id');
      var achternaamInput = achternaamId ? document.getElementById(achternaamId) : null;

      function open() {
        actieveInput = input;
        actieveAchternaamInput = achternaamInput;
        laatsteQuery = null;
        positioneerPaneel(input);
        zoek(input);
      }

      input.addEventListener('focus', open);
      input.addEventListener('input', function () {
        actieveInput = input;
        actieveAchternaamInput = achternaamInput;
        clearTimeout(zoekTimer);
        zoekTimer = setTimeout(function () { zoek(input); }, 200);
      });
    });

    document.addEventListener('mousedown', function (e) {
      if (paneel.hidden) return;
      if (paneel.contains(e.target)) return;
      if (actieveInput && e.target === actieveInput) return;
      sluitPaneel();
    });
    document.addEventListener('keydown', function (e) {
      if (e.key === 'Escape') sluitPaneel();
    });
    window.addEventListener('resize', function () {
      if (actieveInput && !paneel.hidden) positioneerPaneel(actieveInput);
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
