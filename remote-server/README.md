# flora-remote-mcp

Remote MCP server for the flora assistant, running on **Cloudflare Workers**.
This is the project's point 7: an MCP server executing in a cloud service rather
than as a local subprocess, added to the chatbot like any other server.

## Why this is TypeScript and not the Python server

The local server, `flora-mcp`, needs Pl@ntNet (an API key and multipart image
uploads) and the `mcp` Python SDK. Running that Python unchanged in the cloud
would need **Cloudflare Containers, which requires the Workers Paid plan**.
Cloudflare's free tier runs Workers, which are JavaScript/TypeScript.

So this server takes the half of the project that ports cleanly: the GBIF
lookups. GBIF is a public HTTP API with no key, so the whole server is `fetch`
calls, no secrets and no state -- which is exactly what a stateless Worker is
good at. The project spec allows the remote server's functionality to be
trivial; this is deliberately a bit more than that, and complements the local
server rather than duplicating it.

| | `flora-mcp` (local, Python) | `flora-remote-mcp` (cloud, TypeScript) |
| --- | --- | --- |
| Transport | stdio, or HTTP with `--http` | Streamable HTTP |
| Needs a key | Pl@ntNet | no |
| Answers | Is it native/introduced/invasive **here**? | What is this name, and where is it **from**? |

## Tools

| Tool | Purpose |
| --- | --- |
| `lookup_species` | Resolve a scientific name against GBIF's backbone: accepted name, family, and whether the name given was a synonym. |
| `native_range` | The countries where GBIF records the species as NATIVE -- where the plant actually comes from. |
| `occurrences_in_country` | How many observation records GBIF holds for a species in one country. Presence only, never status. |

## Requirements

- Node.js 18+
- A free Cloudflare account (no credit card needed for Workers)

## Local development

```bash
cd remote-server
npm install
npx wrangler dev --port 8787
```

The server is then at `http://127.0.0.1:8787/mcp`. Check it with the project's
own diagnostic, from the repo root:

```bash
.venv/Scripts/python.exe scripts/check_remote_mcp.py http://127.0.0.1:8787/mcp
```

```
[ok] TCP    127.0.0.1:8787 acepta conexiones
[ok] MCP    flora-remote -- 3 tools: lookup_species, native_range, occurrences_in_country
```

## Deploying

```bash
npx wrangler login      # opens a browser, once per machine
npx wrangler deploy
```

Wrangler prints the deployed URL. The MCP endpoint is that URL plus `/mcp`:

```
https://flora-remote-mcp.<tu-subdominio>.workers.dev/mcp
```

Verify the deployed server the same way you verified the local one:

```bash
.venv/Scripts/python.exe scripts/check_remote_mcp.py https://flora-remote-mcp.<tu-subdominio>.workers.dev/mcp
```

## Connecting it to the chatbot

Add the deployed URL to the repo root's `.env`:

```env
FLORA_REMOTE_MCP=flora-remoto=https://flora-remote-mcp.<tu-subdominio>.workers.dev/mcp
```

Start the chatbot and the server appears in the sidebar alongside the local
ones. To prove the model is using the remote one rather than a local
equivalent, ask for it by name:

```
Usando el servidor flora-remoto, de donde es originaria Pontederia crassipes?
```

## A note on access

The Worker is deployed **without authentication**: anyone who knows the URL can
call its tools. That is fine here -- every tool is a read-only query against a
public API, with no keys and no writes -- but it would not be fine for a server
that touched private data. Cloudflare Access or an OAuth provider is the
supported way to put a login in front of a Worker if that changes.

## Versions

The `agents` package and the MCP SDK move fast and their published guides can
lag behind the released packages. This combination is the one verified working:

| Package | Version | Why |
| --- | --- | --- |
| `agents` | ^0.22.0 | Provides `createMcpHandler` from `agents/mcp/server`. |
| `@modelcontextprotocol/server` | 2.0.0 | SDK v2, what the stateless factory form of `createMcpHandler` expects. |
| `@modelcontextprotocol/sdk` | 1.30.0 | Satisfies the `agents` peer dependency for its legacy path. |
| `zod` | ^4.0.0 | Required by `agents` 0.22; v3 fails to resolve. |
