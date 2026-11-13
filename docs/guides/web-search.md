# Knowledge sources: the web, your documents and the encyclopedia

Jarvis answers from three sources beyond what the language model already knows:

| Source | Ask, for example | Setup |
| --- | --- | --- |
| **The web** | *"Search the internet for today's PSEi close"* | None (DuckDuckGo); SearXNG recommended |
| **Your documents** | *"How much do I owe in total?"*, *"What's on my resume?"* | Choose a folder in Settings |
| **Encyclopedia** | *"Who was José Rizal?"* | None (Wikipedia) |

Check what's active in **Settings → Knowledge**, or run `uv run jarvis-doctor`.

## Web search

Web search is **on by default**. Jarvis searches, reads the relevant part of the top two result pages (not just the one-line snippets), and says which site the answer came from.

**What gets sent.**

- Only the search terms. Jarvis is told never to put your personal details in a web query.
- E-mail addresses and long numbers (card, account, phone and ID numbers) are removed from every query automatically, as a safety net.
- Jarvis never fetches pages on your own network (`localhost`, LAN or Tailscale addresses), even if a search result points there.

There are two ways to search:

1. **DuckDuckGo (no setup).** It works out of the box, free and without a key. DuckDuckGo has no official search API, so Jarvis reads its plain-HTML results page. If DuckDuckGo decides there are too many searches, it shows a captcha. Jarvis respects that and pauses DuckDuckGo searches for five minutes, then says so. The page could also change without notice.
2. **SearXNG (recommended, private, reliable).** [SearXNG](https://docs.searxng.org) is a free meta-search engine you run on your own PC. It asks Google, Bing, DuckDuckGo, Wikipedia and others on your behalf, without tracking. When it's set up, Jarvis uses it first and falls back to DuckDuckGo only if it's down.

### Setting up SearXNG (5 minutes, needs Docker)

1. Install **Docker Desktop** (free for personal use) from [docker.com](https://www.docker.com/products/docker-desktop/) and start it once.
2. From the repository folder, start SearXNG:

    ```powershell
    cd services\searxng
    docker compose up -d
    ```

    It's configured for Jarvis already ([`services/searxng/settings.yml`](https://github.com/acn-ryanpacot/aidashboard/blob/main/services/searxng/settings.yml): JSON output on, no rate limiter). It's bound to `127.0.0.1:8888` only, so nothing else on your network can use it, and it restarts with Docker.

3. Open <http://127.0.0.1:8888> in a browser and search for something, to check it works.
4. Point Jarvis at it in `services/core/.env`, then restart the core:

    ```dotenv
    JARVIS_SEARXNG_URL=http://127.0.0.1:8888
    ```

Settings → Knowledge now shows **Web search: SearXNG, then DuckDuckGo**.

!!! tip "Optional: your own secret"
    SearXNG signs its own cookies with a secret key. The default is fine for an instance only your PC can reach. To use your own anyway, create `services/searxng/.env` containing `SEARXNG_SECRET=` followed by a long random string, then run `docker compose up -d` again.

### Web search settings

| Variable | Default | Notes |
| --- | --- | --- |
| `JARVIS_WEB_SEARCH` | `auto` | `auto` = SearXNG if set, then DuckDuckGo · `searxng` = SearXNG only · `duckduckgo` · `off` |
| `JARVIS_SEARXNG_URL` | (empty) | e.g. `http://127.0.0.1:8888` |
| `JARVIS_WEB_SEARCH_REGION` | `wt-wt` | DuckDuckGo region, e.g. `ph-en` for Philippine results |
| `JARVIS_WEB_READ_PAGES` | `true` | Read the top two result pages; `false` = snippets only (faster) |

## Your documents

Give Jarvis a folder, and he uses everything in it to answer questions about you: your resume, bills, statements, payslips, insurance policies, a spreadsheet of debts.

1. Make sure the embedding model is installed: `ollama pull nomic-embed-text`.
2. Create a folder, e.g. `C:\Users\you\Documents\Jarvis`, and put your files in it. Subfolders are fine.
3. Open **Settings → Knowledge → Documents folder**, paste the folder path (Windows *Copy as path* quotes are fine), and **Save**.

Jarvis reads the files in the background. Settings shows the progress (e.g. *"14 of 15 files ready (9 PDFs, 3 spreadsheets, 2 Word files, 1 note)"*) and lists any file it couldn't read, with the reason. New and changed files are picked up within five minutes; **Re-index now** re-reads everything immediately.

**What it reads.**

| Files | How |
| --- | --- |
| PDF (`.pdf`) | The text layer of each page (up to 300 pages) |
| Word (`.docx`) | Paragraphs and tables |
| Excel (`.xlsx`, `.xlsm`) and CSV (`.csv`, `.tsv`) | Every visible sheet, row by row; see below |
| Notes (`.md`, `.txt`, `.rst`, `.org`) | As they are |

**What it skips.**

- Scanned PDFs (photos of paper) have no text, so Settings marks them *"no text layer — probably a scan"*. If your bank offers a downloadable statement, use that instead of a scan.
- Password-protected PDFs.
- Old `.doc`/`.xls` formats: re-save them as `.docx`/`.xlsx`.
- Office lock files (`~$…`), hidden folders and files over 40 MB.

### Exact numbers from spreadsheets

Small local models are bad at arithmetic, so Jarvis doesn't add numbers up himself. His `read_spreadsheet` tool does the maths and gives him finished results to read out. For each numeric column, it reports:

- the **total**,
- the **largest** and **smallest** values, with the row they belong to,
- the **average**.

Ask *"How much do I owe in total?"*, *"How much is left on the BDO card?"* (only the rows mentioning BDO) or *"What's my biggest monthly payment?"*.

For the best results:

- Put a header row at the top (`Creditor`, `Balance`, `Monthly`, `Rate`). A title row above it is fine.
- Use one row per item, and keep the first text column for the item's name.
- Currency (`₱52,000`, `PHP 1,699`), percentages and negative numbers in parentheses (`(1,200)`) are understood.
- Rates, percentages, years and days are compared but not added up. ID-like columns (`Account no`, `Ref`, `Phone`) are ignored.
- In Excel, formulas count as the value Excel last calculated, so save the file in Excel after editing.

### Privacy

- Files are read on your PC and embedded by your local Ollama model. The passages are cached in `~/.jarvis-os/jarvis.db`. Nothing is uploaded, and document contents are never put in web searches.
- **Paired phones can ask about your documents too.** That's handy, but if you lose a phone, revoke it in **Settings → Phone access**. The folder itself can only be changed on the PC.
- To remove something from Jarvis's index, delete or move the file out of the folder. Its passages are dropped at the next check. Clearing the folder field removes them all.

You can also set the folder in `.env` (`JARVIS_DOCUMENTS_DIR=C:/Users/you/Documents/Jarvis`); the Settings screen overrides it. `JARVIS_DOCUMENTS_RESCAN_S` (default `300`) sets how often Jarvis looks for new files.

## Encyclopedia (on by default)

`lookup_encyclopedia` uses Wikipedia's public REST API. It is free, needs no key, and you can turn it off with `JARVIS_ENCYCLOPEDIA_ENABLED=false`.

Wikimedia's [robot policy](https://w.wiki/4wJS) rejects generic User-Agents with HTTP 403. The default works, but the policy asks for real contact details. If you publish your repo, set `JARVIS_ENCYCLOPEDIA_USER_AGENT` to include its URL.

## Troubleshooting

| Symptom | Fix |
| --- | --- |
| Jarvis says he can't search the web | Restart the core after updating; Settings → Knowledge should show the provider. Phrase it explicitly: *"search the web for …"* |
| *"DuckDuckGo is limiting searches"* | Wait five minutes, or set up SearXNG |
| `jarvis-doctor`: *SearXNG not answering* | Start Docker Desktop, then `docker compose up -d` in `services/searxng` |
| SearXNG returns 403 to Jarvis | JSON output is off: use the bundled `settings.yml` |
| *"The embedding model isn't available"* | `ollama pull nomic-embed-text`, then **Re-index now** |
| A PDF shows *"no text layer"* | It's a scan; get a digital copy |
| Spreadsheet totals look wrong | Check the header row and that amounts are numbers, not text with notes in them |
