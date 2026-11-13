# 0017. Web search without setup, and a documents folder Jarvis can read

- Status: Accepted
- Date: 2026-11-13

## Context

In use, Jarvis told the user that he "can't search the internet" and is "limited to what I taught him". Both tools existed, but neither was usable out of the box:

- **Web search** needed a self-hosted SearXNG (Docker plus a hand-edited `settings.yml`). Without one, the `web_search` tool wasn't registered. The prompt then listed only "tasks, reminders, memory, weather and looking things up", so the model truthfully said it couldn't search.
- **Documents** only indexed plain-text notes. The user wants a folder of their own files (resume and other PDFs, bills, Word documents, an Excel file of debts) to be a source for answers.
- A 3B local model can't add up a column of numbers reliably, so "how much do I owe?" needs exact arithmetic.

The project's constraints still apply: zero cost, local-first, private.

## Decision

1. **Web search is on by default**:
   - `JARVIS_WEB_SEARCH=auto` uses SearXNG when configured, otherwise DuckDuckGo's plain-HTML results page (no key). `FallbackWebSearch` tries the providers in order.
   - **Respect DuckDuckGo's limits.** When it answers with a captcha, the provider stops querying it for five minutes and says so. It never switches endpoints or disguises traffic to get around the limit. SearXNG stays the recommended route.
   - The repo bundles a ready `services/searxng/compose.yaml` and `settings.yml`, bound to loopback, so SearXNG is one `docker compose up -d`.
   - **Read pages, not just snippets.** `web_search` fetches the top two result pages in parallel (5 s each) and extracts the paragraphs that share the most words with the query. The tool output names each site, so answers can cite it.
   - **Privacy and safety.** E-mails and long ID-like numbers are stripped from queries, and the tool description forbids personal details. The page reader refuses non-public addresses: it resolves the host and requires every address to be global, so a search result can't point Jarvis at the LAN, `localhost` or the tailnet.
2. **The documents folder reads PDF, Word, Excel and CSV**:
   - Readers use small pure-Python libraries: `pypdf`, `python-docx` and `openpyxl` (BSD and MIT), plus the stdlib `csv` module. They're core dependencies, so nothing extra to install.
   - Spreadsheets are indexed as passages of a few rows each, written as `Column: value` and prefixed with the file and sheet.
   - Unreadable files (scans, encrypted PDFs) are recorded with a reason and shown in Settings, not retried until they change.
3. **The folder is a live setting** (`documents_dir`, [ADR-0012](0012-runtime-settings.md)), so it can be chosen in Settings → Knowledge without editing `.env`.
   - The index is always built when tools and an embedder exist, and re-scans every five minutes by modification time.
   - Changing the folder drops the old folder's passages.
   - Changing the folder is refused from paired devices: a phone token must not be able to point Jarvis at a different folder of the user's PC.
4. **`read_spreadsheet` does the arithmetic.** For a matched file (a fuzzy name match) and an optional row filter, it returns the total, largest, smallest and average per numeric column, with row labels.
   - Currency, percentages and accounting negatives are parsed.
   - Rates, years and days are never summed; identifier columns are skipped.
   - `list_documents` lists the folder.
5. **The prompt states the real abilities.** `describe_abilities` lists the tools that are actually registered (including "searching the internet" and "reading the user's own documents"). When no tools are attached to a turn, the prompt tells the model never to deny one of those abilities and to suggest a phrasing instead.

## Alternatives considered

- **A paid search API** (Brave, Bing, Google). It's reliable, but it costs money or needs an account with a key, which goes against ADR-0003.
- **Scraping Google.** It's against Google's terms and breaks quickly.
- **Getting around DuckDuckGo's captcha** (switching to its lite page, rotating user agents). That defeats an anti-bot measure: rejected. Backing off is the honest behaviour.
- **OCR for scanned PDFs** (Tesseract, or a vision model). It's a heavy dependency for a minority of files, so it's deferred. Scans are reported so the user knows.
- **Letting the LLM sum spreadsheet cells from search passages.** It's unreliable on small models, and passages hold only part of a sheet.
- **Converting files with an external tool** (LibreOffice, `pdftotext`). That's an extra install on Windows; the pure-Python readers cover the formats that matter.

## Consequences

- *"Search the web for …"* works after a clean install. Results depend on DuckDuckGo's HTML page until SearXNG is set up.
- The documents index can now hold personal financial data in `~/.jarvis-os/jarvis.db`, and paired phones can query it through Jarvis. The guide says so and points to device revocation.
- Three small dependencies are added to the core (about 5 MB).
- Every web search now makes up to two extra page requests, which adds a second or two. `JARVIS_WEB_READ_PAGES=false` turns that off.
