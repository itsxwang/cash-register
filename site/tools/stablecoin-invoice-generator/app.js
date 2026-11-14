/* Stablecoin Invoice Generator — 100% client-side.
 * State lives in localStorage. The invoice sheet is rendered from a single
 * render() pass; Print/Save-PDF uses the browser; "Export standalone HTML"
 * writes a self-contained file (inline CSS + inline QR SVG).
 */
(function () {
  "use strict";

  var $ = function (sel, el) { return (el || document).querySelector(sel); };
  var $$ = function (sel, el) { return Array.prototype.slice.call((el || document).querySelectorAll(sel)); };

  /* ---------------- state ---------------- */
  var KEY = "invoicegen.v1";
  var state = {
    seller: { name: "", email: "", website: "", address: "" },
    client: { name: "", email: "", address: "" },
    meta: { number: nextNumber(1), date: today(), due: today(14), currency: "USDT", tax: 0, notes: "Payment due within 7 days. Thank you!" },
    items: [{ desc: "", qty: 1, price: 0 }],
    pay: { chain: "usdt_base", address: "" },
    counter: 1
  };

  function load() {
    try {
      var raw = localStorage.getItem(KEY);
      if (raw) {
        var saved = JSON.parse(raw);
        Object.keys(state).forEach(function (k) {
          if (saved[k] === undefined) return;
          if (Array.isArray(state[k])) { state[k] = saved[k]; return; }
          if (typeof state[k] === "object" && state[k] !== null) {
            state[k] = Object.assign({}, state[k], saved[k]);
          } else {
            state[k] = saved[k];
          }
        });
      }
    } catch (e) {}
  }
  function save() {
    try { localStorage.setItem(KEY, JSON.stringify(state)); } catch (e) {}
  }
  function nextNumber(n) {
    var y = new Date().getFullYear();
    return "INV-" + y + "-" + String(n || 1).padStart(4, "0");
  }
  function today(offsetDays) {
    var d = new Date();
    if (offsetDays) d.setDate(d.getDate() + offsetDays);
    return d.toISOString().slice(0, 10);
  }
  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"]/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c];
    });
  }
  function money(n) {
    n = Number(n) || 0;
    return n.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  }

  /* ---------------- invoice styles (shared with export) ---------------- */
  var INVOICE_CSS = [
    "body{margin:0;font-family:system-ui,-apple-system,'Segoe UI',Roboto,sans-serif;color:#0f172a;background:#fff}",
    ".sheet{max-width:760px;margin:0 auto;padding:40px 44px;background:#fff;box-sizing:border-box}",
    ".inv-head{display:flex;justify-content:space-between;gap:24px;border-bottom:3px solid #4f46e5;padding-bottom:18px}",
    ".inv-title{font-size:28px;font-weight:800;letter-spacing:.04em;color:#4f46e5;margin:0 0 6px}",
    ".inv-head .who{font-size:13px;color:#334155;line-height:1.5}",
    ".inv-head .who b{font-size:15px;color:#0f172a}",
    ".inv-meta{display:grid;grid-template-columns:1fr 1fr 1fr;gap:12px;margin:18px 0 26px;font-size:13px}",
    ".inv-meta div span{display:block;color:#64748b;font-size:11px;text-transform:uppercase;letter-spacing:.06em}",
    ".inv-meta div b{font-weight:600}",
    ".inv-parties{display:grid;grid-template-columns:1fr 1fr;gap:24px;margin-bottom:26px;font-size:13px}",
    ".inv-parties .lbl{color:#64748b;font-size:11px;text-transform:uppercase;letter-spacing:.06em;margin-bottom:4px}",
    "table.inv{width:100%;border-collapse:collapse;font-size:13.5px}",
    "table.inv th{text-align:left;background:#f1f5f9;padding:10px 12px;border-bottom:2px solid #0f172a;font-size:12px;text-transform:uppercase;letter-spacing:.05em}",
    "table.inv td{padding:10px 12px;border-bottom:1px solid #e2e8f0;vertical-align:top}",
    "table.inv .num{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}",
    "table.inv tfoot td{border:none;padding-top:10px}",
    ".totals{width:280px;margin-left:auto;font-size:13.5px}",
    ".totals .tr{display:flex;justify-content:space-between;padding:6px 12px}",
    ".totals .grand{border-top:2px solid #0f172a;font-weight:700;font-size:15px}",
    ".pay{margin-top:28px;border:2px solid #4f46e5;border-radius:14px;padding:16px 18px;display:flex;gap:20px;align-items:flex-start;background:#eef2ff}",
    ".pay .qrbox{background:#fff;border-radius:10px;padding:8px;flex:0 0 auto}",
    ".pay .qrbox svg{display:block}",
    ".pay h4{margin:0 0 8px;font-size:13px;text-transform:uppercase;letter-spacing:.06em;color:#4f46e5}",
    ".pay .kv{font-size:12.5px;line-height:1.7}",
    ".pay .kv b{font-variant-numeric:tabular-nums}",
    ".pay code{font-family:ui-monospace,Menlo,Consolas,monospace;font-size:11.5px;word-break:break-all;display:block}",
    ".inv-notes{margin-top:22px;font-size:12.5px;color:#334155}",
    ".inv-foot{margin-top:34px;border-top:1px solid #e2e8f0;padding-top:12px;display:flex;justify-content:space-between;font-size:11px;color:#94a3b8}",
    "@media print{.sheet{padding:0}}",
    "@page{size:A4;margin:14mm}"
  ].join("\n");

  /* ---------------- payment helpers ---------------- */
  var CHAINS = {
    usdt_base:     { label: "USDT on Base",     token: "0xfde4C96c8593536E31F229EA8f37b2ADa2699bb2", chainId: 8453,  decimals: 6, kind: "eip681" },
    usdt_arbitrum: { label: "USDT on Arbitrum", token: "0xFd086bC7CD5C481DCC9C85cebE478A3862bCeD3", chainId: 42161, decimals: 6, kind: "eip681" },
    usdt_eth:      { label: "USDT on Ethereum", token: "0xdAC17F958D2ee523a2206206994597C13D831ec7", chainId: 1,    decimals: 6, kind: "eip681" },
    usdc_base:     { label: "USDC on Base",     token: "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913", chainId: 8453,  decimals: 6, kind: "eip681" },
    sol:           { label: "SOL (Solana)",     kind: "solana", decimals: 9 },
    btc:           { label: "BTC (Bitcoin)",    kind: "bitcoin", decimals: 8 }
  };

  function totals() {
    var sub = 0;
    state.items.forEach(function (it) { sub += (Number(it.qty) || 0) * (Number(it.price) || 0); });
    var tax = sub * ((Number(state.meta.tax) || 0) / 100);
    return { sub: sub, tax: tax, total: sub + tax };
  }

  function paymentUri(ch, total) {
    var addr = state.pay.address;
    var memo = state.meta.number;
    if (!addr) return null;
    if (ch.kind === "eip681") {
      var units = Math.round(total * Math.pow(10, ch.decimals));
      return "ethereum:" + ch.token + "@" + ch.chainId + "/transfer?address=" + addr + "&uint256=" + units;
    }
    if (ch.kind === "bitcoin") {
      return "bitcoin:" + addr + "?label=" + encodeURIComponent(memo) + "&message=" + encodeURIComponent(memo);
    }
    if (ch.kind === "solana") {
      return "solana:" + addr + "?memo=" + encodeURIComponent(memo);
    }
    return addr;
  }

  function qrSvg(text) {
    if (!text) return "";
    try {
      var qr = qrcode(0, "M");
      qr.addData(text);
      qr.make();
      return qr.createSvgTag({ cellSize: 4, margin: 2, scalable: true });
    } catch (e) { return ""; }
  }

  /* ---------------- render ---------------- */
  function render() {
    var ch = CHAINS[state.pay.chain] || CHAINS.usdt_base;
    var t = totals();
    var cur = esc(state.meta.currency || "USDT");
    var uri = paymentUri(ch, t.total);
    var qr = qrSvg(uri);

    var rows = state.items.map(function (it, i) {
      var amt = (Number(it.qty) || 0) * (Number(it.price) || 0);
      return "<tr><td>" + esc(it.desc || "—") + "</td>" +
        "<td class='num'>" + esc(it.qty) + "</td>" +
        "<td class='num'>" + money(it.price) + "</td>" +
        "<td class='num'>" + money(amt) + "</td></tr>";
    }).join("");

    function lines(txt) {
      return String(txt || "").split("\n").filter(Boolean).map(esc).join("<br>");
    }

    $("#sheet").innerHTML =
      "<div class='inv-head'>" +
        "<div class='who'><b>" + (esc(state.seller.name) || "Your Name") + "</b><br>" +
          lines(state.seller.address) +
          (state.seller.email ? "<br>" + esc(state.seller.email) : "") +
          (state.seller.website ? "<br>" + esc(state.seller.website) : "") +
        "</div>" +
        "<div style='text-align:right'><div class='inv-title'>INVOICE</div>" +
          "<div style='font-size:13px;color:#475569'><b>" + esc(state.meta.number) + "</b></div>" +
          "<div style='font-size:12px;color:#64748b'>denominated in " + cur + "</div>" +
        "</div>" +
      "</div>" +
      "<div class='inv-meta'>" +
        "<div><span>Invoice date</span><b>" + esc(state.meta.date) + "</b></div>" +
        "<div><span>Due date</span><b>" + esc(state.meta.due) + "</b></div>" +
        "<div><span>Amount due</span><b>" + money(t.total) + " " + cur + "</b></div>" +
      "</div>" +
      "<div class='inv-parties'>" +
        "<div><div class='lbl'>From</div><b>" + esc(state.seller.name) + "</b></div>" +
        "<div><div class='lbl'>Bill to</div><b>" + (esc(state.client.name) || "—") + "</b>" +
          (state.client.email ? "<br>" + esc(state.client.email) : "") +
          (state.client.address ? "<br>" + lines(state.client.address) : "") +
        "</div>" +
      "</div>" +
      "<table class='inv'><thead><tr><th>Description</th><th class='num'>Qty</th>" +
        "<th class='num'>Unit (" + cur + ")</th><th class='num'>Amount (" + cur + ")</th></tr></thead>" +
        "<tbody>" + rows + "</tbody>" +
        "<tfoot><tr><td colspan='4'>" +
          "<div class='totals'>" +
            "<div class='tr'><span>Subtotal</span><span>" + money(t.sub) + "</span></div>" +
            "<div class='tr'><span>Tax (" + (Number(state.meta.tax) || 0) + "%)</span><span>" + money(t.tax) + "</span></div>" +
            "<div class='tr grand'><span>Total due</span><span>" + money(t.total) + " " + cur + "</span></div>" +
          "</div>" +
        "</td></tr></tfoot></table>" +
      "<div class='pay'>" +
        (qr ? "<div class='qrbox'>" + qr + "</div>" : "") +
        "<div><h4>Payment details</h4><div class='kv'>" +
          "Network: <b>" + esc(ch.label) + "</b><br>" +
          "Amount: <b>" + money(t.total) + " " + cur + "</b><br>" +
          "Memo: <b>" + esc(state.meta.number) + "</b><br>" +
          "<code>" + esc(state.pay.address || "add your address in the form") + "</code>" +
        "</div></div>" +
      "</div>" +
      "<div class='inv-notes'>" + esc(state.meta.notes || "") + "</div>" +
      "<div class='inv-foot'><span>" + esc(state.seller.name || "") + "</span>" +
        "<span>Invoice " + esc(state.meta.number) + "</span></div>";
  }

  /* ---------------- form binding ---------------- */
  function bindForm() {
    $$("[data-bind]").forEach(function (el) {
      var path = el.getAttribute("data-bind").split(".");
      var val = state;
      for (var i = 0; i < path.length - 1; i++) val = val[path[i]] || {};
      var field = path[path.length - 1];
      el.value = val[field] != null ? val[field] : "";
      var ev = (el.tagName === "SELECT" || el.type === "date" || el.type === "number") ? "change" : "input";
      el.addEventListener(ev, function () {
        val[field] = el.value;
        if (field === "chain" || field === "address") save();
        save();
        render();
      });
    });
  }

  function renderItems() {
    var host = $("#items");
    host.innerHTML = "";
    state.items.forEach(function (it, idx) {
      var row = document.createElement("div");
      row.className = "item-row";
      row.innerHTML =
        "<input type='text' placeholder='Description of work' value=\"" + esc(it.desc) + "\">" +
        "<input type='number' min='0' step='any' value=\"" + esc(it.qty) + "\">" +
        "<input type='number' min='0' step='any' value=\"" + esc(it.price) + "\">" +
        "<button class='remove' title='Remove'>&times;</button>";
      var inputs = row.querySelectorAll("input");
      inputs[0].addEventListener("input", function () { it.desc = inputs[0].value; save(); render(); });
      inputs[1].addEventListener("input", function () { it.qty = Number(inputs[1].value); save(); render(); });
      inputs[2].addEventListener("input", function () { it.price = Number(inputs[2].value); save(); render(); });
      row.querySelector(".remove").addEventListener("click", function () {
        if (state.items.length === 1) { state.items = [{ desc: "", qty: 1, price: 0 }]; }
        else state.items.splice(idx, 1);
        save(); renderItems(); render();
      });
      host.appendChild(row);
    });
  }

  /* ---------------- actions ---------------- */
  $("#btn-additem").addEventListener("click", function () {
    state.items.push({ desc: "", qty: 1, price: 0 });
    save(); renderItems(); render();
  });
  $("#btn-print").addEventListener("click", function () { window.print(); });
  $("#btn-clear").addEventListener("click", function () {
    if (!confirm("Clear all invoice data from this browser?")) return;
    localStorage.removeItem(KEY);
    location.reload();
  });
  $("#btn-example").addEventListener("click", function () {
    state.seller = { name: "Xion Dev Studio", email: "founder@xiondev.xyz", website: "https://xiondev.xyz", address: "Remote — worldwide" };
    state.client = { name: "Acme DAO LLC", email: "ap@acme.xyz", address: "789 Market St\nWilmington, DE" };
    state.items = [
      { desc: "Smart contract audit sprint", qty: 1, price: 2400 },
      { desc: "Payment-bot integration (hours)", qty: 12, price: 95 },
      { desc: "Hosting + infra (Nov)", qty: 1, price: 120 }
    ];
    state.meta.tax = 0;
    state.meta.notes = "Payment due within 7 days. USDT on Base preferred. Thank you!";
    save(); bindRefresh(); render();
  });
  $("#btn-new").addEventListener("click", function () {
    state.counter = (Number(state.counter) || 1) + 1;
    state.meta.number = nextNumber(state.counter);
    state.meta.date = today();
    state.meta.due = today(14);
    state.client = { name: "", email: "", address: "" };
    state.items = [{ desc: "", qty: 1, price: 0 }];
    save(); bindRefresh(); render();
  });

  function bindRefresh() {
    $$("[data-bind]").forEach(function (el) {
      var path = el.getAttribute("data-bind").split(".");
      var val = state;
      for (var i = 0; i < path.length - 1; i++) val = val[path[i]] || {};
      el.value = val[path[path.length - 1]] != null ? val[path[path.length - 1]] : "";
    });
    renderItems();
  }

  /* ---------------- export standalone HTML ---------------- */
  $("#btn-export").addEventListener("click", function () {
    var sheet = $("#sheet").innerHTML; // already includes the inline QR SVG
    var html = "<!DOCTYPE html>\n<html><head><meta charset='utf-8'>" +
      "<title>" + esc(state.meta.number) + "</title>" +
      "<style>" + INVOICE_CSS + "</style></head><body>" +
      "<div class='sheet'>" + sheet + "</div></body></html>";
    var blob = new Blob([html], { type: "text/html" });
    var a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = (state.meta.number || "invoice") + ".html";
    document.body.appendChild(a); a.click(); a.remove();
  });

  /* ---------------- boot ---------------- */
  load();
  // inject invoice css (preview) — export reuses the same string
  var style = document.createElement("style");
  style.textContent = INVOICE_CSS;
  document.head.appendChild(style);
  // auto-fill invoice number & dates on very first run
  if (!localStorage.getItem(KEY)) {
    state.meta.number = nextNumber(1);
  }
  bindForm();
  renderItems();
  render();
})();
