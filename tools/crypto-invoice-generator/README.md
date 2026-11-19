# Crypto Invoice Generator v1.1.1

Professional, printable invoices with a crypto payment block — **BTC (BIP-21),
native ETH on Base (EIP-681), SOL (Solana Pay)** as first-class options, plus an
optional custom-token field for clients who insist on some other EVM token.

100% client-side and fully offline: `app.html` + `app.css` + `app.js`, plus the
bundled `css/`, `js/` and `fonts/` folders it loads (keep the folder together).
No build step, no server, no uploads. All data lives in your browser's
localStorage.

## Use

1. Open `app.html` in any modern browser (works offline — keep the whole folder together).
2. Fill your details once — they persist. Load the example to see a full invoice.
3. Print (→ Save as PDF) or **Export standalone HTML** to attach by email.
4. "Save & new invoice" bumps the invoice number and clears the client section.

## Billing modes

- **Invoice in ETH / SOL / BTC** (recommended): line items are priced in the
  coin; the payment QR carries the exact on-chain amount (integer math —
  no float drift on 18-decimal wei).
- **Invoice in USD**: the invoice reads in dollars; optionally set the
  *exact coin amount* field and the QR carries exact units. Leave it empty
  and the QR is a send-to address with your invoice number as the memo —
  settle at the network rate.
- **Custom EVM token** (optional): paste the contract address, decimals and
  chain id; the QR becomes a token-transfer URI. This is *your* choice, made
  in *your* copy of the tool — the store that ships this tool never accepts
  centralized stablecoins or issuer-controlled assets in its own checkout.

## Privacy & history

Nothing leaves the device. To keep an audit trail, export each invoice HTML
(and print to PDF). To move between machines, copy your browser's
`localStorage["invoicegen.v1"]`.

## Updates

Free minor updates for life — re-download with your order id from the store's
download page.
