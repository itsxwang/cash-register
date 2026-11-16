/* Hero 3D — three floating matte coins (BTC gold, ETH slate, SOL teal) on
 * site/index.html ONLY, per design-language.md v2. Calm, not flashy:
 * slow orbit + gentle bob + subtle mouse parallax, 30fps cap, DPR ≤ 1.5,
 * paused when the tab is hidden or the hero is offscreen. Everything is
 * skipped (static SVG fallback stays) on mobile <768px, reduced-motion,
 * or if WebGL/module load fails. window.__hero3dFrames counts renders
 * so tests can prove the loop is alive.
 */
(function () {
  "use strict";
  var host = document.querySelector(".hero-art");
  if (!host) return;

  var reduced = document.documentElement.getAttribute("data-reduced") === "1" ||
    (window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches);
  var small = window.innerWidth < 768;
  if (reduced || small) return; // SVG fallback remains visible

  /* idle debounce: let first paint + LCP settle before pulling ~160KB gzip */
  setTimeout(function () {
    import("./vendor/three.module.min.js").then(function (THREE) {
      init(THREE);
    }).catch(function () { /* fallback stays */ });
  }, 1500);

  function init(THREE) {
    var renderer;
    try {
      renderer = new THREE.WebGLRenderer({ alpha: true, antialias: true, powerPreference: "low-power" });
    } catch (e) { return; }
    renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 1.5));
    renderer.outputColorSpace = THREE.SRGBColorSpace;
    renderer.domElement.setAttribute("aria-hidden", "true");
    host.appendChild(renderer.domElement);
    var fallback = host.querySelector(".hero-art-fallback");
    if (fallback) fallback.style.display = "none";

    var scene = new THREE.Scene();
    var camera = new THREE.PerspectiveCamera(38, 1, 0.1, 50);
    camera.position.set(0, 0.15, 7.2);

    /* matte lighting: soft hemisphere + key + brand-tinted rim */
    scene.add(new THREE.HemisphereLight(0xe8f0ff, 0x0b1220, 1.1));
    var key = new THREE.DirectionalLight(0xffffff, 1.5);
    key.position.set(-3, 4, 5);
    scene.add(key);
    var rim = new THREE.DirectionalLight(0x7ee0c0, 0.9);
    rim.position.set(4, -2, -3);
    scene.add(rim);

    function coin(colorHex, rimHex) {
      var geo = new THREE.CylinderGeometry(1, 1, 0.16, 48);
      var mat = new THREE.MeshStandardMaterial({
        color: colorHex, roughness: 0.82, metalness: 0.08
      });
      var m = new THREE.Mesh(geo, mat);
      var edge = new THREE.Mesh(
        new THREE.TorusGeometry(1, 0.035, 12, 64),
        new THREE.MeshStandardMaterial({ color: rimHex, roughness: 0.6, metalness: 0.15 })
      );
      edge.rotation.x = Math.PI / 2;
      m.add(edge);
      return m;
    }

    var btc = coin(0xf7931a, 0xffb554);
    var eth = coin(0x627eea, 0x8ea7f5);
    var sol = coin(0x14f195, 0x9945ff);

    /* loose triangle, each coin scaled + phased for a floating feel */
    btc.position.set(-1.55, 0.35, 0.4);  btc.scale.setScalar(1.15);
    eth.position.set(1.35, -0.5, -0.2);  eth.scale.setScalar(0.95);
    sol.position.set(1.9, 1.05, 0.7);    sol.scale.setScalar(0.7);

    var group = new THREE.Group();
    group.add(btc); group.add(eth); group.add(sol);
    group.rotation.z = 0.12;
    scene.add(group);

    var frames = 0;
    window.__hero3dFrames = frames;

    /* gentle mouse parallax (0–1 lerped, damped) */
    var px = 0, py = 0, tx = 0, ty = 0;
    function onMove(e) {
      var w = window.innerWidth || 1, h = window.innerHeight || 1;
      tx = (e.clientX / w - 0.5) * 2;
      ty = (e.clientY / h - 0.5) * 2;
    }
    window.addEventListener("pointermove", onMove, { passive: true });

    function resize() {
      var w = host.clientWidth || 300, h = host.clientHeight || 200;
      renderer.setSize(w, h, false);
      camera.aspect = w / h;
      camera.updateProjectionMatrix();
    }
    resize();
    window.addEventListener("resize", resize, { passive: true });

    /* pause: hidden tab or hero scrolled out of view */
    var visible = true, onscreen = true;
    function running() { return visible && onscreen; }
    document.addEventListener("visibilitychange", function () {
      visible = document.visibilityState === "visible";
    });
    if ("IntersectionObserver" in window) {
      new IntersectionObserver(function (entries) {
        onscreen = entries[0] && entries[0].isIntersecting;
      }, { threshold: 0.05 }).observe(host);
    }

    var last = performance.now(), acc = 0, STEP = 1 / 30;
    function tick(now) {
      requestAnimationFrame(tick);
      var dt = Math.min((now - last) / 1000, 0.1);
      last = now;
      if (!running()) return;      // no work while hidden/offscreen
      acc += dt;
      if (acc < STEP) return;      // 30fps accumulator
      acc = 0;

      px += (tx - px) * 0.04;      // damped parallax
      py += (ty - py) * 0.04;

      group.rotation.y += dt * 0.22;
      btc.position.y = 0.35 + Math.sin(now * 0.00042) * 0.16;
      eth.position.y = -0.5 + Math.sin(now * 0.00033 + 2.1) * 0.14;
      sol.position.y = 1.05 + Math.sin(now * 0.00051 + 4.2) * 0.12;
      btc.rotation.x = 0.45; btc.rotation.z = 0.15;
      eth.rotation.x = 0.5;  eth.rotation.z = -0.2;
      sol.rotation.x = 0.35; sol.rotation.z = 0.25;

      camera.position.x = px * 0.5;
      camera.position.y = 0.15 + py * -0.35;
      camera.lookAt(0, 0.1, 0);

      renderer.render(scene, camera);
      window.__hero3dFrames = ++frames;
    }
    requestAnimationFrame(tick);

    /* if the GL context dies, fall back to the SVG so the hero is never empty */
    renderer.domElement.addEventListener("webglcontextlost", function (ev) {
      ev.preventDefault();
      if (fallback) fallback.style.display = "block";
      if (renderer.domElement.parentNode) renderer.domElement.parentNode.removeChild(renderer.domElement);
    });
  }
})();
