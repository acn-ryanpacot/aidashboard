# Knowledge sources: encyclopedia, web search and your documents

## Encyclopedia (on by default)

`lookup_encyclopedia` uses Wikipedia's public REST API. It is free, needs no key, and you can disable it with `JARVIS_ENCYCLOPEDIA_ENABLED=false`.

Wikimedia's [robot policy](https://w.wiki/4wJS) rejects generic User-Agents with HTTP 403. The default works, but the policy asks for real contact details. If you publish your repo, set `JARVIS_ENCYCLOPEDIA_USER_AGENT` to include its URL.

## Web search with SearXNG (optional, free, private)

[SearXNG](https://docs.searxng.org) is a self-hosted meta-search engine. It queries other engines on your behalf without tracking you.

1. Run it with Docker:

    ```bash
    docker run -d --name searxng -p 8888:8080 searxng/searxng
    ```

2. Enable JSON output. Edit `settings.yml` inside the container (or mount your own):

    ```yaml
    search:
      formats: [html, json]
    ```

    Then restart the container: `docker restart searxng`.

3. Point Jarvis at it:

    ```dotenv
    JARVIS_SEARXNG_URL=http://127.0.0.1:8888
    ```

Ask *"Jarvis, what's in the news about the Mars mission?"*. You'll see *"Searching the web…"* under the core while it works.

## Your own documents (local RAG)

```dotenv
JARVIS_DOCUMENTS_DIR=C:/Users/ryan/Documents/Notes
```

Make sure the embedding model is pulled (`ollama pull nomic-embed-text`). Jarvis indexes `.md`, `.txt`, `.rst` and `.org` files in the background and re-indexes only files that changed. Then ask, for example, *"Jarvis, what did I write about the kitchen renovation budget?"*.

Nothing leaves your machine: files are read locally, embedded by Ollama locally, and cached in `~/.jarvis-os/jarvis.db`.
