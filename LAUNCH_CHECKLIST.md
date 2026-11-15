# LAUNCH CHECKLIST — human steps only

Everything below is what **you** (the founder) must do by hand. The code and
site are already built and tested locally; these steps take a live store from
placeholders to first sale. Budget ~2–3 hours total (excluding distribution
posts). No paid services anywhere.

---

## 1. Put the repo on GitHub (~10 min)

- [ ] Create a **private or public** GitHub repo, e.g. `cash-register`
      (private is fine — Pages works from private repos on the free tier of
      the *public* plan only; if yours is private, use Cloudflare Pages instead).
- [ ] Push this directory:
      ```bash
      cd venture-00-cash-register
      git remote add origin git@github.com:YOUR_GITHUB_USERNAME/cash-register.git
      git push -u origin main
      ```
- [ ] Create a **second repo** `cash-register-releases` (public) — this is the
      delivery target for the download links.

## 2. Deploy the storefront for free (~10 min)

Pick **one**:

- **GitHub Pages**: repo → Settings → Pages → Source: `main` branch, `/ (root)`
  → site goes live at `https://YOUR_GITHUB_USERNAME.github.io/cash-register/`.
- **Cloudflare Pages** (works with private repos): dash.cloudflare.com →
  Workers & Pages → Create → Pages → Connect to Git → pick the repo →
  build command: *none*, output dir: `site`.

- [ ] After deploy, put the live URL into `config.yaml → store.url`.

## 3. Paste real wallet addresses ⚠️ (~15 min, do not skip)

- [ ] Edit `config.yaml`:
      - `addresses.btc` — your BTC receive address (bech32/bc1 recommended)
      - `addresses.sol` — your Solana address
      - `addresses.eth` — your receiving address for **native ETH on Base**
        (use a wallet you control; verify the network is Base before sharing)
      - `addresses.eth_chain_id` / `eth_chain_name` — keep `8453 / Base`
      - `store.contact_email` — where buyers send payment reports
        (Telegram is NOT used for buyer support: no buyer-facing Telegram)
- [ ] Regenerate the public data (this is what the site actually serves):
      ```bash
      python3 -m payments demo     # demo fixtures with your addresses
      python3 -m payments sync --refresh-fx
      ```
- [ ] Commit + push the regenerated `site/data/`.
- [ ] Sanity check: open the live checkout page — the demo banner should now
      say "Live store" (no PLACEHOLDER strings).

## 4. Watcher cron + free Etherscan key (~15 min)

- [ ] Get a **free Etherscan API key**: etherscan.io → sign up → API Keys
      (free tier: 5 req/s — plenty). It powers the native-ETH-on-Base watcher.
- [ ] Add the cron (every 10 min: check payments, re-sync site data, push):
      ```bash
      crontab -e
      ```
      ```
      ETHERSCAN_API_KEY=your_free_key
      */10 * * * * cd /home/xion/venture-00-cash-register && python3 -m payments check --all >> payments/data/cron.log 2>&1 && python3 -m payments sync >> payments/data/cron.log 2>&1 && git add site/data && git commit -qm "sync order data" && git push >> payments/data/cron.log 2>&1
      ```
- [ ] First cron run: check `payments/data/cron.log` for watcher notes.
      Run `python3 -m payments doctor` once manually to probe all endpoints.
- [ ] If your laptop isn't always-on: schedule the same steps as a GitHub
      Actions `schedule:` workflow (free for public repos) — that's a v2 task,
      the manual CSV flow needs nothing always-on.

## 5. Create the downloadable products (~10 min)

- [ ] Build all three zips reproducibly:
      ```bash
      bash scripts/build_releases.sh
      ```
      → `releases/crypto-invoice-generator-v1.1.0.zip`,
         `releases/cron-ping-monitor-v1.0.0.zip`,
         `releases/telegram-broadcaster-v1.0.0.zip`
      (names are verified against `config.yaml` by the script).
- [ ] GitHub → `cash-register-releases` → Draft new release per tool:
      tag matching the file name, attach the zip.
- [ ] Put the repo owner/name into `config.yaml → delivery.releases_base`,
      run `python3 -m payments sync`, commit, push.
- [ ] Test the whole loop **yourself**: pay **$1 worth of ETH on Base (or SOL
      or BTC)** to yourself through your own checkout page → add the CSV row →
      `payments check --all` → `sync` → download page shows your file.
      With a funded watcher address this also exercises the auto-match path.

## 6. First-day distribution — 5 free channels (~45 min)

- [ ] **GitHub visibility**: repo About link + topics (`crypto`, `invoice`,
      `telegram-bot`, `side-project`); pin it on your profile.
- [ ] **Reddit + Indie Hackers**: build-in-public post — screenshot the invoice
      generator output and the status page; link the store.
      (X/Twitter unavailable: founder's account banned — do not use.)
- [ ] **Reddit**: r/SideProject post ("I built a crypto-only storefront with no
      backend — here's the whole stack"); follow each sub's self-promo rules,
      answer every comment.
- [ ] **Indie Hackers**: milestone post on the product page you create — include
      real revenue numbers as they come (transparency posts travel).
- [ ] **Crypto-native watering holes**: Farcaster `/dev` + `/crypto` channels,
      Discord servers of the crypto job communities, dev-community threads
      (Reddit, Indie Hackers, Farcaster) —
      the invoice generator is the wedge: reply to "how do I invoice my crypto
      clients?" threads with a genuine demo link, not an ad.
      (Do not use Telegram for promotion: the founder's Telegram account is
      frozen — Telegram is dead as a channel for us except tool #3, which is
      a product we sell, and cron-ping's optional alerts, which are a feature
      buyers use in their own copy.)
- [ ] Optional: **Show HN** ("Show HN: Static-site crypto checkout with on-chain
      watchers, no Stripe") — post when the store has processed ≥1 real payment.

## 7. First-week hygiene

- [ ] Rotate nothing yet — but test `python3 -m payments rotate --order …` once
      so you know the leak-response path.
- [ ] Keep `payments/confirmations.csv` (your money ledger) **out of git**
      (already gitignored) and back it up.
- [ ] Watchers note mismatches in the order JSON (`watch_note`) — skim it when
      a buyer says "I paid but no download".
- [ ] Delete `DEMO-0001/2` fixtures from the live site if you don't want them
      public: `git rm site/data/orders/DEMO-*.json site/data/qr/DEMO-*.svg`.
