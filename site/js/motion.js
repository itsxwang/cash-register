/* Cash Register storefront motion — calm confidence per design-language.md v2.
 * Scroll reveal (fade+rise 12px, 500ms ease-out, 60ms stagger), stat-counter
 * utility, and nothing else. prefers-reduced-motion: everything stays visible,
 * nothing animates. The html.js gate is set pre-paint by the head snippet, so
 * no-JS visitors and reduced-motion users never see hidden content.
 */
(function () {
  "use strict";
  if (document.documentElement.getAttribute("data-reduced") === "1") return;

  /* ---- scroll reveal ---- */
  var els = Array.prototype.slice.call(document.querySelectorAll(".reveal"));
  if (els.length && "IntersectionObserver" in window) {
    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        if (!entry.isIntersecting) return;
        entry.target.classList.add("revealed");
        io.unobserve(entry.target);
      });
    }, { rootMargin: "0px 0px -8% 0px", threshold: 0.08 });
    els.forEach(function (el, i) {
      if (el.style.transitionDelay === "") el.style.transitionDelay = (i % 6) * 60 + "ms";
      io.observe(el);
    });
  } else {
    els.forEach(function (el) { el.classList.add("revealed"); });
  }

  /* ---- animated stat counters (used where a section carries a real number;
   *      nothing fabricated — elements opt in via data-count-to) ---- */
  function animateCount(el) {
    var target = parseFloat(el.getAttribute("data-count-to"));
    var decimals = (el.getAttribute("data-count-decimals") || "0") | 0;
    if (isNaN(target)) return;
    var dur = 900, t0 = null;
    function tick(t) {
      if (t0 === null) t0 = t;
      var p = Math.min((t - t0) / dur, 1);
      var eased = 1 - Math.pow(1 - p, 3); // ease-out cubic, no bounce
      el.textContent = (target * eased).toFixed(decimals);
      if (p < 1) requestAnimationFrame(tick);
    }
    requestAnimationFrame(tick);
  }
  var counters = Array.prototype.slice.call(document.querySelectorAll("[data-count-to]"));
  if (counters.length && "IntersectionObserver" in window) {
    var io2 = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        if (!entry.isIntersecting) return;
        animateCount(entry.target);
        io2.unobserve(entry.target);
      });
    }, { threshold: 0.5 });
    counters.forEach(function (el) { io2.observe(el); });
  }
})();
