/* Crypto Invoice Generator v1.1.1 — 100% client-side.
 * State lives in localStorage. The invoice sheet renders from a single
 * render() pass; Print/Save-PDF uses the browser; "Export standalone HTML"
 * writes a self-contained file (inline CSS + inline QR SVG).
 *
 * Asset policy of the store this tool ships from: native BTC / ETH / SOL are
 * first-class ("coins nobody can freeze"). An optional custom-token field
 * lets the invoicer bill in whatever their client insists on — that choice
 * is made locally, in the invoicer's copy, and never touches our store.
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
    meta: { number: nextNumber(1), date: today(), due: today(14), currency: "ETH", tax: 0, notes: "Payment due within 7 days. Thank you!" },
    items: [{ desc: "", qty: 1, price: 0 }],
    pay: { network: "eth", address: "", tokenContract: "", tokenDecimals: 6, tokenChainId: 8453, exactAmount: "" },
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

  /* ---------------- money & units ----------------
   * Integer-exact unit conversion: decimals are handled by STRING math
   * (decStrToUnits), so 18-decimal wei never passes through a float.
   */
  var CURRENCY_DECIMALS = { ETH: 6, SOL: 6, BTC: 8, USD: 2 };
  var NETWORK_DECIMALS = { eth: 18, sol: 9, btc: 8 };

  function fmtAmount(n, cur) {
    var dp = CURRENCY_DECIMALS[cur] != null ? CURRENCY_DECIMALS[cur] : 2;
    n = Number(n) || 0;
    return n.toLocaleString("en-US", { minimumFractionDigits: dp, maximumFractionDigits: dp });
  }

  /* "0.05" + 18 -> "50000000000000000" (exact, no float) */
  function decStrToUnits(s, dec) {
    var str = String(s == null ? "" : s).trim();
    var m = /^(\d+)?(?:\.(\d*))?$/.exec(str);
    if (!m || (!m[1] && !m[2])) return null;
    var intPart = m[1] || "0";
    var frac = m[2] || "";
    if (frac.length < dec) frac += new Array(dec - frac.length + 1).join("0");
    else frac = frac.slice(0, dec);
    var units = (intPart + frac).replace(/^0+(?=\d)/, "");
    return units === "" ? "0" : units;
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
    ".pay .qrbox svg{display:block;max-width:100%;height:auto}",
    ".pay h4{margin:0 0 8px;font-size:13px;text-transform:uppercase;letter-spacing:.06em;color:#4f46e5}",
    ".pay .kv{display:block;grid-template-columns:none;gap:0;align-items:initial;font-size:12.5px;line-height:1.7}",
    ".pay .kv b{font-variant-numeric:tabular-nums}",
    ".sheet .pay code{font-family:ui-monospace,Menlo,Consolas,monospace;font-size:11.5px;word-break:break-all;display:block;background:transparent;border:0;border-radius:0;padding:0;color:#0f172a;user-select:text}",
    ".inv-notes{margin-top:22px;font-size:12.5px;color:#334155}",
    ".inv-foot{margin-top:34px;border-top:1px solid #e2e8f0;padding-top:12px;display:flex;justify-content:space-between;font-size:11px;color:#94a3b8}",
    "@media print{.sheet{padding:0}}",
    // Phone widths: keep the invoice readable without horizontal scrolling.
    "@media screen and (max-width:560px){.sheet{padding:24px 18px}table.inv{font-size:11px;table-layout:fixed}table.inv th:nth-child(1),table.inv td:nth-child(1){width:38%}table.inv th:nth-child(2),table.inv td:nth-child(2){width:16%}table.inv th:nth-child(3),table.inv td:nth-child(3){width:23%}table.inv th:nth-child(4),table.inv td:nth-child(4){width:23%}table.inv th,table.inv td{padding:6px 3px;overflow-wrap:anywhere}table.inv th{font-size:8.5px;letter-spacing:0;white-space:normal}table.inv th.num{white-space:normal}.inv-parties{gap:12px}.brandline{gap:10px}}",
    "@page{size:A4;margin:14mm}"
  ].join("\n");

  /* ---------------- payment resolution ---------------- */
  var NETWORK_SHORT = {
    eth: "Base (0x…) address",
    sol: "Solana address",
    btc: "Bitcoin address"
  };

  function addrKind(a) {
    a = (a || "").trim();
    if (!a) return "";
    if (/^0x[0-9a-fA-F]{40}$/.test(a)) return "eth";
    if (/^(bc1[a-zA-HJ-NP-Z0-9]{25,62}|[13][a-km-zA-HJ-NP-Z1-9]{25,34})$/.test(a)) return "btc";
    if (/^[1-9A-HJ-NP-Za-km-z]{32,44}$/.test(a)) return "sol";
    return "unknown";
  }

  function addrWarning() {
    var el = $("#addr-warning");
    if (!el) return;
    var addr = (state.pay.address || "").trim();
    var net = state.pay.network;
    var msg = "";
    if (addr && net !== "custom") {
      var kind = addrKind(addr);
      if (kind === "unknown") {
        msg = "That doesn't look like a valid " + NETWORK_SHORT[net] + " — double-check it before sending this invoice.";
      } else if (kind !== net) {
        msg = "This looks like a " + kind.toUpperCase() + " address, but \"Get paid on\" is set to " +
              NETWORK_SHORT[net] + ". The QR would not be payable — change one of them.";
      }
    }
    el.textContent = msg;
  }

  var NETWORK_LABEL = {
    eth: "ETH (native) — Base",
    sol: "SOL (native) — Solana",
    btc: "BTC (native) — Bitcoin",
    custom: "Custom EVM token"
  };

  function totals() {
    var sub = 0;
    state.items.forEach(function (it) { sub += (Number(it.qty) || 0) * (Number(it.price) || 0); });
    var tax = sub * ((Number(state.meta.tax) || 0) / 100);
    return { sub: sub, tax: tax, total: sub + tax };
  }

  /* Resolve the exact on-chain units the payer should send (string, exact). */
  function paymentUnits(total) {
    var cur = state.meta.currency;
    var net = state.pay.network;
    var disp = fmtAmount(total, cur).replace(/,/g, "");  // display-quantized total
    var exactManual = state.pay.exactAmount ? decStrToUnits(state.pay.exactAmount, NETWORK_DECIMALS[net] != null ? NETWORK_DECIMALS[net] : Number(state.pay.tokenDecimals) || 6) : null;

    if (net === "custom") {
      return { units: exactManual, via: "token", dec: Number(state.pay.tokenDecimals) || 6, exactSource: state.pay.exactAmount ? "manual" : null };
    }
    if (cur === "ETH" && net === "eth") return { units: decStrToUnits(disp, 18), via: "eth", dec: 18, exactSource: "invoice" };
    if (cur === "SOL" && net === "sol") return { units: decStrToUnits(disp, 9), via: "sol", dec: 9, exactSource: "invoice" };
    if (cur === "BTC" && net === "btc") return { units: decStrToUnits(disp, 8), via: "btc", dec: 8, exactSource: "invoice" };
    return { units: exactManual, via: net, dec: NETWORK_DECIMALS[net], exactSource: state.pay.exactAmount ? "manual" : null };
  }

  function unitsToUriAmount(unitsStr, dec) {
    /* units string -> decimal coin string with full precision */
    if (unitsStr == null) return null;
    var s = unitsStr.replace(/^0+(?=\d)/, "");
    while (s.length <= dec) s = "0" + s;
    var out = s.slice(0, s.length - dec) + "." + s.slice(s.length - dec);
    return out.replace(/(\.\d*?)0+$/, "$1").replace(/\.$/, "");
  }

  function paymentUri(net, total) {
    var addr = state.pay.address;
    var memo = state.meta.number;
    var plan = paymentUnits(total);
    if (!addr) return null;

    if (plan.via === "eth") {
      return plan.units ? "ethereum:" + addr + "@8453?value=" + plan.units
                        : "ethereum:" + addr + "@8453";
    }
    if (plan.via === "custom") {
      var cid = Number(state.pay.tokenChainId) || 8453;
      var contract = state.pay.tokenContract;
      if (!contract) return addr;
      return plan.units
        ? "ethereum:" + contract + "@" + cid + "/transfer?address=" + addr + "&uint256=" + plan.units
        : addr;
    }
    if (plan.via === "btc") {
      var btcAmt = plan.units ? unitsToUriAmount(plan.units, 8) : null;
      return "bitcoin:" + addr +
        (btcAmt ? "?amount=" + btcAmt + "&" : "?") +
        "label=" + encodeURIComponent(memo) + "&message=" + encodeURIComponent(memo);
    }
    if (plan.via === "sol") {
      var solAmt = plan.units ? unitsToUriAmount(plan.units, 9) : null;
      return "solana:" + addr +
        (solAmt ? "?amount=" + solAmt + "&" : "?") +
        "memo=" + encodeURIComponent(memo);
    }
    return addr;
  }

  function qrSvg(text) {
    if (!text) return "";
    try {
      var qr = qrcode(0, "M");
      qr.addData(text);
      qr.make();
      return qr.createSvgTag({ cellSize: 4, margin: 2 });
    } catch (e) { return ""; }
  }

  /* ---------------- render ---------------- */
  function render() {
    var cur = state.meta.currency || "USD";
    var net = state.pay.network;
    var t = totals();
    var plan = paymentUnits(t.total);
    var uri = paymentUri(net, t.total);
    // Never render a QR for an address that does not match the selected
    // network: a scannable-but-unpayable QR on an invoice is worse than none.
    var addrOk = net === "custom" || !uri || addrKind(state.pay.address) === net;
    var qr = addrOk ? qrSvg(uri) : "";

    var amountLine = plan.units
      ? "<b>" + esc(unitsToUriAmount(plan.units, plan.dec)) + "</b> (" + esc(plan.exactSource === "manual" ? "set manually" : "exact, from invoice total") + ")"
      : "<b>" + esc(fmtAmount(t.total, cur)) + " " + esc(cur) + "</b> — settle at the network rate";

    var rows = state.items.map(function (it) {
      var amt = (Number(it.qty) || 0) * (Number(it.price) || 0);
      return "<tr><td>" + esc(it.desc || "—") + "</td>" +
        "<td class='num'>" + esc(it.qty) + "</td>" +
        "<td class='num'>" + esc(fmtAmount(it.price, cur)) + "</td>" +
        "<td class='num'>" + esc(fmtAmount(amt, cur)) + "</td></tr>";
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
          "<div style='font-size:12px;color:#64748b'>amounts in " + esc(cur) + "</div>" +
        "</div>" +
      "</div>" +
      "<div class='inv-meta'>" +
        "<div><span>Invoice date</span><b>" + esc(state.meta.date) + "</b></div>" +
        "<div><span>Due date</span><b>" + esc(state.meta.due) + "</b></div>" +
        "<div><span>Amount due</span><b>" + esc(fmtAmount(t.total, cur)) + " " + esc(cur) + "</b></div>" +
      "</div>" +
      "<div class='inv-parties'>" +
        "<div><div class='lbl'>From</div><b>" + esc(state.seller.name) + "</b></div>" +
        "<div><div class='lbl'>Bill to</div><b>" + (esc(state.client.name) || "—") + "</b>" +
          (state.client.email ? "<br>" + esc(state.client.email) : "") +
          (state.client.address ? "<br>" + lines(state.client.address) : "") +
        "</div>" +
      "</div>" +
      "<table class='inv'><thead><tr><th>Description</th><th class='num'>Qty</th>" +
        "<th class='num'>Unit (" + esc(cur) + ")</th><th class='num'>Amount (" + esc(cur) + ")</th></tr></thead>" +
        "<tbody>" + rows + "</tbody>" +
        "<tfoot><tr><td colspan='4'>" +
          "<div class='totals'>" +
            "<div class='tr'><span>Subtotal</span><span>" + esc(fmtAmount(t.sub, cur)) + "</span></div>" +
            "<div class='tr'><span>Tax (" + (Number(state.meta.tax) || 0) + "%)</span><span>" + esc(fmtAmount(t.tax, cur)) + "</span></div>" +
            "<div class='tr grand'><span>Total due</span><span>" + esc(fmtAmount(t.total, cur)) + " " + esc(cur) + "</span></div>" +
          "</div>" +
        "</td></tr></tfoot></table>" +
      "<div class='pay'>" +
        (qr ? "<div class='qrbox'>" + qr + "</div>" : "") +
        "<div><h4>Payment details</h4><div class='kv'>" +
          "Network: <b>" + esc(NETWORK_LABEL[net] || net) + "</b><br>" +
          "Amount: " + amountLine + "<br>" +
          "Memo: <b>" + esc(state.meta.number) + "</b><br>" +
          "<code>" + esc(state.pay.address || "add your address in the form") + "</code>" +
        "</div></div>" +
      "</div>" +
      "<div class='inv-notes'>" + esc(state.meta.notes || "") + "</div>" +
      "<div class='inv-foot'><span>" + esc(state.seller.name || "") + "</span>" +
        "<span>Invoice " + esc(state.meta.number) + "</span></div>";

    // custom-token fields visibility
    var ct = $("#custom-token-fields");
    if (ct) ct.classList.toggle("hidden", net !== "custom");
    addrWarning();
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
    state.meta.currency = "ETH";
    state.items = [
      { desc: "Smart contract audit sprint", qty: 1, price: 0.5 },
      { desc: "Payment-bot integration (hours)", qty: 12, price: 0.0025 },
      { desc: "Hosting + infra (Nov)", qty: 1, price: 0.04 }
    ];
    state.meta.tax = 0;
    state.meta.notes = "Payment due within 7 days. Native ETH on Base preferred. Thank you!";
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
  // inject invoice css (preview) — export reuses the same string.
  // IMPORTANT: the invoice document's body{} rule is scoped to .sheet here —
  // injecting it globally forced a white body and killed dark mode on the app page.
  var style = document.createElement("style");
  style.textContent = INVOICE_CSS.replace(
    /body\{margin:0;font-family:[^}]*\}/,
    ".sheet{font-family:system-ui,-apple-system,'Segoe UI',Roboto,sans-serif;color:#0f172a}"
  );
  document.head.appendChild(style);
  if (!localStorage.getItem(KEY)) {
    state.meta.number = nextNumber(1);
  }
  bindForm();
  renderItems();
  render();
})();
