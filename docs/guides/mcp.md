# Plugging in MCP servers

The [Model Context Protocol](https://modelcontextprotocol.io) is an open standard for exposing tools to AI models. Jarvis can launch any **stdio** MCP server and give its tools to the brain, which opens up file systems, Git, calendars, home automation, databases, and so on.

## Enable

```bash
cd services/core
uv sync --group dev --extra mcp
```

List servers in `services/core/.env` as JSON:

```dotenv
JARVIS_MCP_SERVERS=[{"name":"files","command":"npx","args":["-y","@modelcontextprotocol/server-filesystem","C:/Users/ryan/Documents"]}]
```

| Field     | Meaning                                                 |
| --------- | ------------------------------------------------------- |
| `name`    | Short id; tools appear as `name__tool`, e.g. `files__read_file` |
| `command` | Executable (`npx`, `uvx`, `python`, …)                  |
| `args`    | Arguments                                               |
| `env`     | Extra environment variables (e.g. API tokens)           |

On start-up the log shows `mcp_server_ready server=files tools=…`. A server that fails to start is skipped with a warning, and Jarvis keeps running.

## Tips

- Small local models handle a handful of tools much better than dozens. Enable only the servers you actually use.
- MCP servers run with **your** permissions. Only add servers you trust, and scope file-system servers to specific folders.
