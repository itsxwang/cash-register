/* Hero 3D — three matte coins (BTC gold, ETH slate, SOL near-black) with the
 * official glyphs engraved on the faces, on site/index.html ONLY, per
 * design-language.md v2. Calm, not flashy: per-coin drift + gentle bob +
 * subtle mouse parallax, 30fps cap, DPR ≤ 1.5, paused when the tab is hidden
 * or the hero is offscreen. Skipped (static SVG fallback stays) on mobile
 * <768px, reduced-motion, or if WebGL/module load fails. window.__hero3dFrames
 * counts renders so tests can prove the loop is alive.
 *
 * Coin faces: CylinderGeometry discs (diameter:thickness 10:1) + a raised rim
 * torus; the top cap carries a CanvasTexture (512×512, drawn once at init —
 * no runtime cost) with the official Bitcoin ₿ / Ethereum diamond / Solana
 * three-bar marks (Simple Icons paths, CC0). No font or network dependency.
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

  /* Official brand glyphs, viewBox 0 0 24 24 (Simple Icons, CC0).
   * bitcoin = ₿ in its circle; ethereum = two mirrored pyramids (diamond);
   * solana = three parallel bars leaning up-right. */
  var GLYPHS = {
    btc: "M23.638 14.904c-1.602 6.43-8.113 10.34-14.542 8.736C2.67 22.05-1.244 15.525.362 9.105 1.962 2.67 8.475-1.243 14.9.358c6.43 1.605 10.342 8.115 8.738 14.548v-.002zm-6.35-4.613c.24-1.59-.974-2.45-2.64-3.03l.54-2.153-1.315-.33-.525 2.107c-.345-.087-.705-.167-1.064-.25l.526-2.127-1.32-.329-.537 2.148c-.286-.067-.57-.13-.859-.194l-1.865-.466-.34 1.367s.975.224.955.238c.535.134.63.486.615.766l-1.558 6.254c-.065.162-.23.406-.602.313.013.02-.955-.238-.955-.238l-.67 1.542 1.758.438c.327.082.647.168.964.25l-.593 2.382 1.316.328.539-2.162c.36.098.71.188 1.054.273l-.535 2.145 1.318.33.592-2.377c2.247.425 3.937.254 4.65-1.779.574-1.637-.028-2.582-1.212-3.197.862-.199 1.512-.765 1.688-1.935zm-3.015 4.222c-.407 1.632-3.16.75-4.053.53l.724-2.9c.893.223 3.757.665 3.329 2.37zm.407-4.271c-.372 1.487-2.667.732-3.412.547l.657-2.64c.745.185 3.146.532 2.755 2.093z",
    eth: "M11.944 17.97L4.58 13.62 11.943 24l7.37-10.38-7.372 4.35h.003zM12.056 0L4.69 12.223l7.365 4.354 7.365-4.35L12.056 0z",
    sol: "m23.8764 18.0313-3.962 4.1393a.9201.9201 0 0 1-.306.2106.9407.9407 0 0 1-.367.0742H.4599a.4689.4689 0 0 1-.2522-.0733.4513.4513 0 0 1-.1696-.1962.4375.4375 0 0 1-.0314-.2545.4438.4438 0 0 1 .117-.2298l3.9649-4.1393a.92.92 0 0 1 .3052-.2102.9407.9407 0 0 1 .3658-.0746H23.54a.4692.4692 0 0 1 .2523.0734.4531.4531 0 0 1 .1697.196.438.438 0 0 1 .0313.2547.4442.4442 0 0 1-.1169.2297zm-3.962-8.3355a.9202.9202 0 0 0-.306-.2106.941.941 0 0 0-.367-.0742H.4599a.4687.4687 0 0 0-.2522.0734.4513.4513 0 0 0-.1696.1961.4376.4376 0 0 0-.0314.2546.444.444 0 0 0 .117.2297l3.9649 4.1394a.9204.9204 0 0 0 .3052.2102c.1154.049.24.0744.3658.0746H23.54a.469.469 0 0 0 .2523-.0734.453.453 0 0 0 .1697-.1961.4382.4382 0 0 0 .0313-.2546.4444.4444 0 0 0-.1169-.2297zM.46 6.7225h18.7815a.9411.9411 0 0 0 .367-.0742.9202.9202 0 0 0 .306-.2106l3.962-4.1394a.4442.4442 0 0 0 .117-.2297.4378.4378 0 0 0-.0314-.2546.453.453 0 0 0-.1697-.196.469.469 0 0 0-.2523-.0734H4.7596a.941.941 0 0 0-.3658.0745.9203.9203 0 0 0-.3052.2102L.1246 5.9687a.4438.4438 0 0 0-.1169.2295.4375.4375 0 0 0 .0312.2544.4512.4512 0 0 0 .1692.196.4689.4689 0 0 0 .2518.0739z"
  };

  /* 512×512 face texture: matte radial base + engraved glyph (drawn once). */
  function faceTexture(kind, bgTop, bgEdge, paint) {
    var c = document.createElement("canvas");
    c.width = c.height = 512;
    var x = c.getContext("2d");
    var g = x.createRadialGradient(256, 190, 60, 256, 256, 300);
    g.addColorStop(0, bgTop);
    g.addColorStop(1, bgEdge);
    x.fillStyle = g;
    x.fillRect(0, 0, 512, 512);
    var p = new Path2D(GLYPHS[kind]);
    var s = 512 * 0.62 / 24; // glyph ≈ 62% of the face
    x.save();
    x.translate(256 - 12 * s, 256 - 12 * s);
    x.scale(s, s);
    paint(x, p);
    x.restore();
    var tex = new THREE.CanvasTexture(c);
    tex.colorSpace = THREE.SRGBColorSpace;
    tex.anisotropy = 4;
    return tex;
  }

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

    /* matte lighting: soft hemisphere + key + brand-tinted rim + camera fill */
    scene.add(new THREE.HemisphereLight(0xe8f0ff, 0x0b1220, 1.1));
    var key = new THREE.DirectionalLight(0xffffff, 1.4);
    key.position.set(-3, 5, 4);
    scene.add(key);
    var rim = new THREE.DirectionalLight(0x7ee0c0, 0.8);
    rim.position.set(4, -2, -3);
    scene.add(rim);
    var fill = new THREE.DirectionalLight(0xdde7ff, 0.55);
    fill.position.set(0, 0.6, 6);
    scene.add(fill);

    /* flat disc (diameter:thickness = 10:1) + raised rim ring; the top cap
     * carries the engraved face texture, side/bottom stay plain matte. */
    function coin(kind, bgTop, bgEdge, edgeColor, rimHex, paint) {
      var cap = new THREE.MeshStandardMaterial({
        map: faceTexture(kind, bgTop, bgEdge, paint),
        roughness: 0.8, metalness: 0.05
      });
      var plain = new THREE.MeshStandardMaterial({ color: edgeColor, roughness: 0.85, metalness: 0.08 });
      var m = new THREE.Mesh(new THREE.CylinderGeometry(1, 1, 0.2, 48), [plain, cap, plain]);
      var ring = new THREE.Mesh(
        new THREE.TorusGeometry(1.02, 0.05, 12, 64),
        new THREE.MeshStandardMaterial({ color: rimHex, roughness: 0.6, metalness: 0.15 })
      );
      ring.rotation.x = Math.PI / 2;
      m.add(ring);
      return m;
    }

    /* BTC: gold face, ₿ engraved in darker gold */
    var btc = coin("btc", "#fb9f2e", "#e08508", "#d97e06", 0xffb554, function (x, p) {
      x.fillStyle = "#a35f00";
      x.fill(p);
    });
    /* ETH: slate-blue face, diamond etched in light two-tone facets */
    var eth = coin("eth", "#7d92e8", "#5a72d4", "#4a5fbf", 0x8ea7f5, function (x, p) {
      x.fillStyle = "rgba(255,255,255,0.72)";
      x.fill(p);
      x.save();
      x.beginPath(); x.rect(12, 0, 12, 24); x.clip();
      x.fillStyle = "rgba(255,255,255,0.95)";
      x.fill(p);
      x.restore();
    });
    /* SOL: near-black face, three slanted bars in the official gradient */
    var sol = coin("sol", "#141031", "#0b0e1a", "#070a14", 0x9945ff, function (x, p) {
      var grad = x.createLinearGradient(0, 1.5, 24, 22.5);
      grad.addColorStop(0, "#9945FF");
      grad.addColorStop(1, "#14F195");
      x.fillStyle = grad;
      x.fill(p);
    });

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
    /* per-coin drift: small circular orbit + bob; faces stay camera-facing */
    var seed = [
      { cx: -1.55, cy: 0.35, cz: 0.4, ph: 0.0 },
      { cx: 1.35, cy: -0.5, cz: -0.2, ph: 2.1 },
      { cx: 1.9, cy: 1.05, cz: 0.7, ph: 4.2 }
    ];
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

      [btc, eth, sol].forEach(function (c, i) {
        var s = seed[i], w = now * 0.00035 + s.ph;
        c.position.x = s.cx + Math.sin(w) * 0.28;
        c.position.z = s.cz + Math.cos(w) * 0.34;
        c.position.y = s.cy + Math.sin(w * 1.35) * 0.16;
        c.rotation.x = 1.3 + Math.sin(w * 0.8) * 0.12;
        c.rotation.z = (i - 1) * 0.16;
      });

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
