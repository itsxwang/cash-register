/* Cash Register storefront JS — vanilla, no build step.
 * Serves: home tool grid, per-tool checkout, order status, download gating.
 * All data comes from statically generated JSON (payments CLI -> site/data/).
 */
(function () {
  "use strict";

  /* ---- base path (works at site root and under GitHub Pages /<repo>/) ---- */
  var BASE = (function () {
    var s = document.currentScript ? document.currentScript.src : "";
    var m = s.match(/^(.*\/)js\/store\.js/);
    return m ? m[1] : "/";
  })();

  function abs(p) {
    if (!p) return p;
    return p.indexOf("/") === 0 ? BASE + p.slice(1) : p;
  }

  function $(sel, el) { return (el || document).querySelector(sel); }
  function $$(sel, el) { return Array.prototype.slice.call((el || document).querySelectorAll(sel)); }

  function fetchJSON(path) {
    return fetch(abs(path)).then(function (r) {
      if (!r.ok) { var e = new Error("HTTP " + r.status); e.status = r.status; throw e; }
      return r.json();
    });
  }

  var catalogPromise = null;
  function catalog() {
    if (!catalogPromise) { catalogPromise = fetchJSON("/data/catalog.json").catch(function () { return null; }); }
    return catalogPromise;
  }

  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }

  function money(n) { return "$" + Number(n).toFixed(2); }

  /* ------------------------------------------------------------------ */
  /* demo-mode banner: addresses still placeholders                      */
  /* ------------------------------------------------------------------ */
  function demoBanner() {
    var host = $("[data-demo-banner]");
    if (!host) return;
    catalog().then(function (cat) {
      if (!cat) return;
      var placeholder = Object.keys(cat.chains || {}).some(function (k) {
        return String(cat.chains[k].address || "").toUpperCase().indexOf("PLACEHOLDER") !== -1;
      });
      if (placeholder) {
        host.innerHTML = "<strong>Demo mode.</strong> Wallet addresses in this store are placeholders. " +
          "Replace them in <code>config.yaml</code> (see LAUNCH_CHECKLIST.md) before selling.";
      } else {
        host.innerHTML = "<strong>Live store.</strong> You pay the wallet shown at checkout — " +
          "always the exact amount, and your order id is your receipt.";
      }
    });
  }

  /* ------------------------------------------------------------------ */
  /* home: render the tool grid from the catalog                          */
  /* ------------------------------------------------------------------ */
  function renderHome() {
    var grid = $("[data-tools-grid]");
    if (!grid) return;
    catalog().then(function (cat) {
      if (!cat || !cat.tools) { grid.innerHTML = "<p class='muted'>Catalog unavailable (open via a web server, e.g. <code>python3 -m http.server</code>).</p>"; return; }
      grid.innerHTML = Object.keys(cat.tools).map(function (id) {
        var t = cat.tools[id];
        return "<div class='card'>" +
          "<h3>" + esc(t.name) + "</h3>" +
          "<p>" + esc(t.blurb) + "</p>" +
          "<div class='price'>" + money(t.price_usd) + " <small>one-off, crypto</small></div>" +
          "<div class='row'><a class='btn small' href='" + esc(abs(t.landing)) + "'>Details</a>" +
          "<a class='btn ghost small' href='" + esc(abs(t.checkout)) + "'>Checkout</a></div>" +
          "</div>";
      }).join("");
      var b = $("[data-bundle]");
      if (b && cat.bundle) {
        b.textContent = money(cat.bundle.price_usd);
        var bundleNote = $("[data-bundle-note]");
        if (bundleNote) bundleNote.textContent = cat.bundle.note || "";
      }
    });
  }

  /* ------------------------------------------------------------------ */
  /* landing pages: inject price by tool id                              */
  /* ------------------------------------------------------------------ */
  function pageToolId() {
    var m = location.pathname.match(/tools\/([^/]+)\//);
    return m ? m[1] : null;
  }

  function injectPrices() {
    var ids = $$("[data-price-for]");
    if (!ids.length) return;
    catalog().then(function (cat) {
      if (!cat) return;
      ids.forEach(function (el) {
        var t = (cat.tools || {})[el.getAttribute("data-price-for")];
        if (t) el.textContent = money(t.price_usd);
      });
      var bundle = $("[data-bundle]");
      if (bundle && cat.bundle) bundle.textContent = money(cat.bundle.price_usd);
    });
  }

  /* ------------------------------------------------------------------ */
  /* client-side order id (unambiguous alphabet, mirrors payments/ids.py) */
  /* ------------------------------------------------------------------ */
  var ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789";
  function newOrderId() {
    var buf = new Uint32Array(8);
    (window.crypto || window.msCrypto).getRandomValues(buf);
    var out = "CR-";
    for (var i = 0; i < 8; i++) out += ALPHABET[buf[i] % ALPHABET.length];
    return out;
  }

  /* ---- payment URI builders (mirror payments/uris.py) ----------------
   * Asset policy: native ETH (EIP-681 value), native SOL, native BTC only.
   * ------------------------------------------------------------------ */
  function paymentUri(chain, ch, amount, rawUnits, memo) {
    if (chain === "eth") {
      // rawUnits = exact wei; always a clean 0.00001 ETH step => float64-exact
      return "ethereum:" + ch.address + "@" + ch.chain_id + "?value=" + rawUnits;
    }
    if (chain === "btc") {
      return "bitcoin:" + ch.address + "?amount=" + amount.toFixed(8) +
        "&label=" + encodeURIComponent(memo) + "&message=" + encodeURIComponent(memo);
    }
    if (chain === "sol") {
      return "solana:" + ch.address + "?amount=" + amount + "&memo=" + encodeURIComponent(memo);
    }
    return ch.address;
  }

  function makeQR(text, host) {
    host.innerHTML = "";
    if (!text) return;
    var qr = qrcode(0, "M");
    qr.addData(text);
    qr.make();
    host.innerHTML = qr.createSvgTag({ cellSize: 4, margin: 2, scalable: true });
    var svg = host.querySelector("svg");
    if (svg) { svg.style.width = "180px"; svg.style.height = "180px"; }
  }

  function copyText(text, btn) {
    function done() {
      if (!btn) return;
      var old = btn.textContent;
      btn.textContent = "Copied!";
      setTimeout(function () { btn.textContent = old; }, 1200);
    }
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).then(done, done);
    } else {
      var ta = document.createElement("textarea");
      ta.value = text; document.body.appendChild(ta); ta.select();
      try { document.execCommand("copy"); } catch (e) {}
      document.body.removeChild(ta); done();
    }
  }

  /* ------------------------------------------------------------------ */
  /* checkout page                                                       */
  /* ------------------------------------------------------------------ */
  function renderCheckout() {
    var root = $("[data-checkout]");
    if (!root) return;
    var params = new URLSearchParams(location.search);
    var item = params.get("item") || pageToolId();
    var urlOrder = params.get("order");

    catalog().then(function (cat) {
      if (!cat) { root.innerHTML = "<p class='muted'>Catalog unavailable — serve this site over HTTP.</p>"; return; }
      var tool = null;
      if (item === "bundle" && cat.bundle) {
        tool = {
          id: "bundle",
          name: "Lifetime bundle — all tools",
          price_usd: cat.bundle.price_usd,
          chains: Object.keys(cat.chains)
        };
      } else {
        tool = (cat.tools || {})[item];
      }
      if (!tool) { root.innerHTML = "<p class='muted'>Unknown item.</p>"; return; }
      $$("[data-tool-name]").forEach(function (el) { el.textContent = tool.name; });
      document.title = "Checkout — " + tool.name;

      if (urlOrder) { renderCheckoutWithOrder(cat, tool, urlOrder); }
      else { renderSelfServe(cat, tool); }
    });
  }

  function chainRow(chain) {
    return "<div class='kv'><span class='label'>Network</span><span>" + esc(chain) + "</span></div>";
  }

  function renderCheckoutWithOrder(cat, tool, orderId) {
    var root = $("[data-checkout]");
    fetchJSON("/data/orders/" + encodeURIComponent(orderId) + ".json").then(function (o) {
      var ch = cat.chains[o.chain] || {};
      var badge = "<span class='badge " + esc(o.status) + "'>" + esc(o.status.replace("_", " ")) + "</span>";
      root.innerHTML =
        "<h3 class='mt0'>Order " + esc(o.order_id) + " " + badge + "</h3>" +
        "<p class='muted'>" + esc(o.tool.name) + " — " + money(o.price_usd) + "</p>" +
        (o.status === "paid" && o.download
          ? "<div class='panel'><h3>You're in. Download:</h3>" +
            "<a class='btn' id='dl' href='" + esc(abs(o.download.url)) + "'>Download " + esc(o.tool.name) + "</a>" +
            "<p class='hint'>Link includes your token. If it stops working, ask for a re-issue.</p></div>"
          : "<div class='paybox'><div>" +
            "<div class='kv'><span class='label'>Send exactly</span><code id='amt'>" + esc(o.amount) + " " + esc(o.currency) + "</code>" +
            "<button class='btn ghost small copy-btn' data-copy='amt'>copy</button></div>" +
            "<div class='kv'><span class='label'>To</span><code id='addr'>" + esc(o.address) + "</code>" +
            "<button class='btn ghost small copy-btn' data-copy='addr'>copy</button></div>" +
            "<div class='kv'><span class='label'>Memo</span><code id='memo'>" + esc(o.memo) + "</code>" +
            "<button class='btn ghost small copy-btn' data-copy='memo'>copy</button></div>" +
            "<div class='kv'><span class='label'>Network</span><span>" + esc(o.chain_name) + "</span></div>" +
            (tool.delivery_note
              ? "<div class='kv'><span class='label'>Delivery</span>" + esc(tool.delivery_note) + "</div>"
              : "") +
            "<p class='hint'>Pay with any wallet that supports " + esc(o.chain_name) + ". The memo/unique amount is how the payment is matched to this order.</p>" +
            "</div><div class='qrbox'><div class='qr' id='qrhost'></div>" +
            "<p class='hint'>scan with your wallet</p></div></div>" +
            ivePaidBox(o)) +
        "<p><a href='" + esc(abs(o.status_url)) + "'>Check order status →</a></p>";
      if (o.payment_uri) makeQR(o.payment_uri, $("#qrhost"));
      wireCopyButtons();
      wireIvePaid(o);
    }).catch(function (e) {
      root.innerHTML = "<p>Order <code>" + esc(orderId) + "</code> not found (" + e.message + ").</p>" +
        "<p class='hint'>If you just paid, the founder may not have ingested it yet. " +
        "Try again in a few minutes or use the self-serve checkout below.</p>" +
        "<p><a class='btn ghost' href='checkout.html'>Self-serve checkout</a></p>";
    });
  }

  function renderSelfServe(cat, tool) {
    var root = $("[data-checkout]");
    var chains = (tool.chains && tool.chains.length ? tool.chains : Object.keys(cat.chains));
    var orderId = newOrderId();
    var fx = cat.fx || {};

    root.innerHTML =
      "<h3 class='mt0'>Checkout — <span data-tool-name>" + esc(tool.name) + "</span></h3>" +
      "<div class='chainpick' id='chainpick'>" + chains.map(function (c, i) {
        return "<label><input type='radio' name='chain' value='" + esc(c) + "'" + (i === 0 ? " checked" : "") + ">" +
          esc((cat.chains[c] || {}).label || c) + "</label>";
      }).join("") + "</div>" +
      "<div class='paybox'><div>" +
      "<div class='kv'><span class='label'>Price</span><code id='usd'>" + money(tool.price_usd) +
        (tool.id === "citation-monitor-weekly-digest" ? " / month" : "") + "</code></div>" +
      (tool.delivery_note
        ? "<div class='kv'><span class='label'>Delivery</span>" + esc(tool.delivery_note) + "</div>"
        : "") +
      "<div class='kv'><span class='label'>Send exactly</span><code id='amt'></code>" +
      "<button class='btn ghost small copy-btn' data-copy='amt'>copy</button></div>" +
      "<div class='kv'><span class='label'>To</span><code id='addr'></code>" +
      "<button class='btn ghost small copy-btn' data-copy='addr'>copy</button></div>" +
      "<div class='kv'><span class='label'>Memo</span><code id='memo'></code>" +
      "<button class='btn ghost small copy-btn' data-copy='memo'>copy</button></div>" +
      "<p class='hint' id='fxhint'></p>" +
      "<p class='hint'>This store confirms payments manually (founder checks the wallet, assisted by on-chain watchers). " +
      "Include the memo / use the exact amount so your payment can be matched.</p>" +
      "</div><div class='qrbox'><div class='qr' id='qrhost'></div><p class='hint'>scan with your wallet</p></div></div>" +
      (tool.id !== "bundle"
        ? "<div class='upsell'>💎 <strong>Get all 3 tools for $49</strong> — one payment, lifetime updates. " +
          "<a href='" + abs("/checkout.html?item=bundle") + "'>See the bundle →</a></div>"
        : "") +
      "<p class='hint'>New to paying with crypto? Read the <a href='" + abs("/crypto-guide.html") + "'>4-step payment guide</a> (1 min). " +
      "Refunds within 7 days — email xion.dev7@gmail.com.</p>" +
      ivePaidBox(null) +
      "<p class='hint'>Order id: <code id='oid'>" + esc(orderId) + "</code> <button class='btn ghost small' id='reid'>new id</button> " +
      "— write it down, you'll use it on the <a href='" + abs("/status.html") + "'>status page</a>.</p>";

    var state = { chain: chains[0] };
    function refresh() {
      var c = $("#chainpick input:checked") ? $("#chainpick input:checked").value : chains[0];
      state.chain = c;
      var ch = cat.chains[c];
      var memo = orderId;
      var amtText, rawUnits, amountCrypto;
      if (c === "eth" && fx.usd_eth) {
        // integer math in clean 0.00001 ETH steps (10^13 wei) — float64-exact
        var steps = Math.round(Number(tool.price_usd) * fx.usd_eth * 1e5); // units of 0.00001 ETH
        amountCrypto = steps / 1e5;
        rawUnits = steps * 1e13; // exact wei (clean steps keep it float64-exact)
        amtText = amountCrypto.toFixed(5) + " ETH";
      } else if (c === "btc" && fx.usd_btc) {
        amountCrypto = tool.price_usd * fx.usd_btc;
        rawUnits = Math.round(amountCrypto * 1e8);
        amtText = amountCrypto.toFixed(8) + " BTC";
      } else if (c === "sol" && fx.usd_sol) {
        amountCrypto = tool.price_usd * fx.usd_sol;
        rawUnits = Math.round(amountCrypto * 1e9);
        amtText = amountCrypto.toFixed(9) + " SOL";
      } else {
        amountCrypto = null; rawUnits = null;
        amtText = "equivalent of " + money(tool.price_usd);
      }
      $("#amt").textContent = amtText;
      $("#addr").textContent = ch.address;
      $("#memo").textContent = memo;
      $("#fxhint").textContent = (fx && fx.source)
        ? "Rate snapshot: 1 USD ≈ " +
          (c === "btc" ? fx.usd_btc.toFixed(8) + " BTC"
            : c === "eth" ? fx.usd_eth.toFixed(6) + " ETH"
            : fx.usd_sol.toFixed(9) + " SOL") +
          " (" + fx.source + ", " + (fx.updated_at || "") + "). Founder verifies the received value."
        : "";
      makeQR(paymentUri(c, ch, amountCrypto || 0, rawUnits || 0, memo), $("#qrhost"));
      state.amountText = amtText;
    }
    refresh();
    $("#chainpick").addEventListener("change", refresh);
    $("#reid").addEventListener("click", function () {
      orderId = newOrderId(); $("#oid").textContent = orderId; refresh();
    });

    wireCopyButtons();
    wireIvePaid({
      order_id: orderId, tool: tool, chain: state.chain,
      amount_text: function () { return state.amountText; },
      self_serve: true
    });
  }

  function ivePaidBox(order) {
    return "<div class='panel' id='ivepaid'><h3>Already paid? Tell the founder.</h3>" +
      "<div class='row'>" +
      "<label class='field' style='flex:1;min-width:220px'>Amount you sent" +
      "<input type='text' id='paidamt' placeholder='e.g. 0.01078 ETH'></label>" +
      "<label class='field' style='flex:1;min-width:220px'>Txid / link (optional)" +
      "<input type='text' id='paidtx' placeholder='0x… / signature…'></label>" +
      "</div>" +
      "<div class='row'>" +
      "<a class='btn' id='mailto'>Email the report</a>" +
      "<button class='btn ghost' id='copyreport'>Copy report</button>" +
      "</div>" +
      "<p class='hint'>The button opens your mail app with everything prefilled. After you send it, " +
      "the founder confirms (CSV + on-chain watchers) and your download link appears on the " +
      "<a href='" + abs("/status.html") + "'>status page</a>. Allow a few minutes.</p></div>";
  }

  function reportText(o, amt, tx) {
    return "ORDER REPORT\n" +
      "tool: " + o.tool.name + "\n" +
      "order id: " + o.order_id + "\n" +
      (o.self_serve ? "chain: " + (o.chain || "") + "\n" : "chain: " + (o.chain || "") + "\n") +
      "amount sent: " + (amt || (o.amount_text ? o.amount_text() : "")) + "\n" +
      "txid: " + (tx || "(not provided)") + "\n" +
      "memo used: " + o.order_id + "\n";
  }

  function wireIvePaid(o) {
    var box = $("#ivepaid");
    if (!box) return;
    var mailto = $("#mailto"), cp = $("#copyreport");
    var founderEmail = null;
    catalog().then(function (cat) {
      if (!cat) return;
      founderEmail = cat.store.contact_email;
      refreshLinks();
    });

    function body() {
      var amt = $("#paidamt") ? $("#paidamt").value : "";
      var tx = $("#paidtx") ? $("#paidtx").value : "";
      return reportText(o, amt, tx);
    }
    function refreshLinks() {
      var b = body();
      if (mailto) mailto.href = "mailto:" + (founderEmail || "") +
        "?subject=" + encodeURIComponent("Payment report — order " + o.order_id) +
        "&body=" + encodeURIComponent(b);
    }
    ["#paidamt", "#paidtx"].forEach(function (sel) {
      var el = $(sel); if (el) el.addEventListener("input", refreshLinks);
    });
    refreshLinks();
    if (cp) cp.addEventListener("click", function () { copyText(body(), cp); });

    // remember order locally for the status page
    try {
      var mine = JSON.parse(localStorage.getItem("cr.myorders") || "[]");
      mine.unshift({ id: o.order_id, tool: o.tool.name, at: new Date().toISOString() });
      localStorage.setItem("cr.myorders", JSON.stringify(mine.slice(0, 20)));
    } catch (e) {}
  }

  function wireCopyButtons() {
    $$("[data-copy]").forEach(function (btn) {
      var target = $("#" + btn.getAttribute("data-copy"));
      if (!target) return;
      btn.addEventListener("click", function () { copyText(target.textContent, btn); });
    });
  }

  /* ------------------------------------------------------------------ */
  /* status page                                                         */
  /* ------------------------------------------------------------------ */
  function renderStatus() {
    var root = $("[data-status]");
    if (!root) return;
    var oid = new URLSearchParams(location.search).get("order");
    var mine = [];
    try { mine = JSON.parse(localStorage.getItem("cr.myorders") || "[]"); } catch (e) {}

    function form(html) {
      root.innerHTML = html +
        (mine.length ? "<h3>Your recent orders (this browser)</h3>" + mine.map(function (m) {
          return "<p><a href='" + abs("/status.html") + "?order=" + encodeURIComponent(m.id) + "'>" +
            esc(m.id) + "</a> — " + esc(m.tool) + " <span class='muted'>" + esc((m.at || "").slice(0, 10)) + "</span></p>";
        }).join("") : "") +
        "<h3>Look up an order</h3><form id='sform' class='row'>" +
        "<input type='text' id='sid' placeholder='CR-XXXXXXXX' style='max-width:220px'>" +
        "<button class='btn' type='submit'>Check</button></form>";
      $("#sform").addEventListener("submit", function (ev) {
        ev.preventDefault();
        location.href = abs("/status.html") + "?order=" + encodeURIComponent($("#sid").value.trim().toUpperCase());
      });
    }

    if (!oid) {
      form("<h2>Order status</h2><p class='muted'>Enter your order id, or pick a recent order below.</p>");
      return;
    }

    fetchJSON("/data/orders/" + encodeURIComponent(oid) + ".json").then(function (o) {
      var steps = [
        { key: "created", label: "Order created — payment details issued", done: true },
        { key: "sent", label: "You sent the payment (exact amount + memo)", done: o.status !== "awaiting_payment" },
        { key: "confirmed", label: "Founder confirmed (manual CSV / on-chain watcher)", done: o.status === "paid" || o.status === "delivered" },
        { key: "download", label: "Download link unlocked", done: o.status === "paid" || o.status === "delivered" }
      ];
      root.innerHTML =
        "<h2 class='mt0'>Order " + esc(o.order_id) + " <span class='badge " + esc(o.status) + "'>" +
        esc(o.status.replace("_", " ")) + "</span></h2>" +
        "<p>" + esc(o.tool.name) + " — " + esc(o.chain_name) + " — " + money(o.price_usd) + "</p>" +
        "<ul class='timeline'>" + steps.map(function (s) {
          return "<li" + (s.done ? " class='done'" : "") + ">" + esc(s.label) + "</li>";
        }).join("") + "</ul>" +
        (o.status === "paid" && o.download
          ? "<a class='btn' href='" + esc(abs(o.download.url)) + "'>Go to download →</a> "
          : o.status === "awaiting_payment"
            ? "<a class='btn ghost' href='" + esc(abs(o.checkout_url)) + "'>Show payment details →</a> "
            : "") +
        "<a class='btn ghost' href='" + abs("/download.html") + "?order=" + encodeURIComponent(o.order_id) + "'>Download page</a>" +
        "<p class='hint'>Watch note: " + esc(o.watch_note || "—") + "</p>";
    }).catch(function () {
      form("<h2>Order status</h2><p>Order <code>" + esc(oid) + "</code> isn't registered yet.</p>" +
        "<p class='hint'>If you just paid and reported it, the founder processes confirmations in batches — " +
        "retry in a few minutes. Double-check the id (format CR-XXXXXXXX).</p>");
    });
  }

  /* ------------------------------------------------------------------ */
  /* download page                                                       */
  /* ------------------------------------------------------------------ */
  function renderDownload() {
    var root = $("[data-download]");
    if (!root) return;
    var oid = new URLSearchParams(location.search).get("order");
    if (!oid) {
      root.innerHTML = "<p>Missing order id. Find it on the <a href='" + abs("/status.html") + "'>status page</a>.</p>";
      return;
    }
    fetchJSON("/data/orders/" + encodeURIComponent(oid) + ".json").then(function (o) {
      if (o.status !== "paid" && o.status !== "delivered") {
        root.innerHTML = "<h2 class='mt0'>Not unlocked yet</h2>" +
          "<p>Order <code>" + esc(oid) + "</code> is <b>" + esc(o.status.replace("_", " ")) + "</b>.</p>" +
          "<p><a href='" + esc(abs(o.status_url)) + "'>Check status →</a></p>";
        return;
      }
      root.innerHTML = "<h2 class='mt0'>Download — " + esc(o.tool.name) + "</h2>" +
        "<p class='muted'>Order " + esc(o.order_id) + " · token " + esc((o.download || {}).token || "") + "</p>" +
        "<a class='btn' href='" + esc(abs((o.download || {}).url)) + "'>Download files</a>" +
        "<p class='hint'>Delivered via GitHub Releases (free). If the link 404s, the release was rotated — " +
        "message the founder with your order id for a fresh link.</p>";
    }).catch(function () {
      root.innerHTML = "<p>Order <code>" + esc(oid) + "</code> not found. " +
        "<a href='" + abs("/status.html") + "'>Back to status.</a></p>";
    });
  }

  /* ------------------------------------------------------------------ */
  /* dark mode — CSS variables only; choice persists in localStorage      */
  /* (the head anti-FOUC snippet already set data-theme before CSS paint) */
  /* ------------------------------------------------------------------ */
  function initTheme() {
    var btn = $("#theme-toggle");
    if (!btn) return;
    applyTheme(document.documentElement.getAttribute("data-theme") === "dark" ? "dark" : "light");
    btn.addEventListener("click", function () {
      var next = document.documentElement.getAttribute("data-theme") === "dark" ? "light" : "dark";
      applyTheme(next);
      try { localStorage.setItem("cr.theme", next); } catch (e) {}
    });
  }

  function applyTheme(theme) {
    var btn = $("#theme-toggle");
    document.documentElement.setAttribute("data-theme", theme);
    if (btn) {
      btn.textContent = theme === "dark" ? "☀️" : "🌙";
      btn.setAttribute("aria-pressed", theme === "dark" ? "true" : "false");
      btn.setAttribute("aria-label", theme === "dark" ? "Switch to light mode" : "Switch to dark mode");
    }
  }

  /* ------------------------------------------------------------------ */
  function init() {
    initTheme();
    demoBanner();
    renderHome();
    injectPrices();
    renderCheckout();
    renderStatus();
    renderDownload();
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init);
  else init();
})();
