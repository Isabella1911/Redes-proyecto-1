# Asistente de flora

A chatbot that acts as an MCP host: it talks to an LLM (Claude) over its API
and gives it tools exposed by multiple Model Context Protocol (MCP) servers, so
anyone can point at a plant, say where they are, and find out whether that
species is **native**, **introduced** or **invasive** in that country -- and
what to do about it if it is invasive.

The answer depends on the place, not just on the species: *Pontederia
crassipes* is native in the Amazon basin and an aggressive invasive in
Guatemala. That is exactly the kind of question a static model answer gets
wrong and a tool call gets right.

This is the coursework project for CC3067 - Redes (Universidad del Valle de
Guatemala).

## Features

- Connects to the Claude API and answers general questions from its own
  knowledge.
- Keeps conversational context across turns in a session.
- Logs every request/response exchanged with the connected MCP servers
  (console + `mcp_interactions.log`).
- Connects to the official **Filesystem** and **Git** MCP servers to list the
  photos in the working folder and version-control the reports it writes.
- Ships its own local MCP server, **`flora-mcp`**, which identifies plants from
  a photo (Pl@ntNet) and classifies their status per country against GBIF.
- Connects to two classmates' local MCP servers (a mock internal documentation
  search, and a library catalog backed by a real MySQL database) to demonstrate
  using and combining third-party MCP servers.
- Two front ends for the same chatbot: a console REPL (`flora-assistant`) and a
  browser chat UI (`flora-assistant-web`) with a live checklist of every
  connected tool, a photo gallery of the workspace, and drag-and-drop upload
  that identifies a photo the moment it lands.

## Architecture

```
Chatbot (host)
 |- Claude API client        -> decides which tool(s) to call and in what order
 |- MCP client -> Filesystem MCP server (official, stdio)
 |- MCP client -> Git MCP server (official, stdio)
 |- MCP client -> flora-mcp (own server, stdio) -> Pl@ntNet + GBIF
 |- MCP client -> docfinder (classmate's server, stdio)
 `- MCP client -> library (classmate's server, stdio)
```

Each MCP client is a `ClientSession` from the official `mcp` SDK, owned by the
host. Tools from every connected server are aggregated and offered to Claude as
a single tool list; the host routes each `tool_use` response back to the client
for the server that owns that tool.

A server that fails to start is recorded in `MCPManager.startup_errors` and
skipped rather than taking the chatbot down: with five servers, two of them
other people's, one being unavailable is a normal Tuesday.

## How the status is decided

GBIF publishes no single "is this invasive here?" field, so `flora-mcp` combines
three public sources and always returns the evidence alongside the verdict:

| Source | What it contributes |
| --- | --- |
| `species/{key}/distributions` | A national checklist's `establishmentMeans` for that country: NATIVE, INTRODUCED, NATURALISED, MANAGED, INVASIVE. |
| GRIIS (per country) | The country's Global Register of Introduced and Invasive Species. Membership means the species is alien there. |
| GISD | The Global Invasive Species Database: species documented as invasive somewhere in the world. |

The precedence is:

1. A distribution row for that country wins -- a national checklist stating the
   establishment means directly. `INTRODUCED` + a GISD listing is reported as
   **invasora**; `INTRODUCED` alone as **introducida**; `NATIVE` as **nativa**.
2. Otherwise, presence in the country's GRIIS register means alien there;
   combined with GISD, invasive.
3. Otherwise, occurrence records only prove the species has been *seen* there,
   which is reported as **"presente, estatus no documentado"** rather than
   guessed at.

Coverage is genuinely uneven -- *Pinus oocarpa* is native to Guatemala but no
checklist says so on GBIF, so the tool says "present, status not documented"
instead of inventing an answer. The system prompt tells the model to report that
honestly.

Taxonomy has one trap worth knowing about: Pl@ntNet returns *Eichhornia
crassipes* while GBIF's backbone has moved to *Pontederia crassipes*, and each
checklist is indexed under whichever name its compiler used. Every lookup in
`gbif.py` tries both the matched key and the accepted key for this reason.

## Requirements

- Python >= 3.11
- [Node.js](https://nodejs.org/) (for `npx`, used to launch the official
  Filesystem MCP server)
- [uv](https://docs.astral.sh/uv/) (used to launch `mcp-server-git` via `uvx`)
- An Anthropic API key ([console.anthropic.com](https://console.anthropic.com))
- A free Pl@ntNet API key ([my.plantnet.org](https://my.plantnet.org/)) --
  500 identifications/day on the free plan

GBIF needs no key.

## Installation

```bash
git clone https://github.com/anthonylouschwank/Redes-proyecto-1.git
cd Redes-proyecto-1
uv venv .venv
.venv\Scripts\activate      # Windows; source .venv/bin/activate elsewhere
uv pip install -e .
```

Copy `.env.example` to `.env` and fill in the two keys:

```powershell
Copy-Item .env.example .env
```

When creating the Anthropic key in the Claude Console (Settings -> API keys),
scope it to a single workspace rather than "all workspaces". A key that is not
scoped to one workspace requires sending an `anthropic-workspace-id` header on
every request, which this project does not set.

## Usage

### Console

```bash
flora-assistant
```

Drop plant photos into `workspace/` and ask in natural language:

```
tu> que fotos hay en el workspace? identifica la primera, estoy en Guatemala
```

Type `reset` to clear the conversation context, `salir` to quit.

### Web UI

```bash
flora-assistant-web
```

Serves `http://127.0.0.1:8765`. The sidebar has two panels:

- **Fotos** -- a thumbnail grid of everything in `workspace/`. Click one to
  identify it. Photos can be uploaded by button or drag-and-drop; uploading a
  single photo identifies it immediately. The country field above is remembered
  between sessions (`localStorage`) and is appended to the identify request; if
  it is empty the assistant asks for the country instead of guessing.
- **Herramientas** -- every tool from every connected server, grouped, with a
  status dot. A server that failed to start shows in red with its error.

The main panel is a chat with the same assistant, showing which tools it used
for each answer.

Uploads are validated: the extension must be JPG, PNG or WebP, the file must be
under 10 MB, and its leading bytes must actually match one of those formats.
The stored extension comes from those bytes rather than from the uploaded name,
so a PNG someone renamed to `.jpg` is still filed correctly. Names are
sanitised and never overwrite an existing photo.

The photo endpoints, if you want to drive them directly:

| Route | Purpose |
| --- | --- |
| `GET /api/photos` | List the images in the workspace, newest first. |
| `GET /api/photos/{name}` | Serve one image. Refuses any path that escapes the workspace. |
| `POST /api/upload` | Upload one image (multipart, field `file`). |

### Classmates' servers (rubric item 6)

`config.py` connects to two classmates' MCP servers, cloned under
`../Proyecto1_Redes/`:

| Server | Setup |
| --- | --- |
| `../Proyecto1_Redes/CC3067-Proyecto1-docfinder` | `npm install` in its own repo; launched with `npx tsx`. |
| `../Proyecto1_Redes/CC3067-library-mcp` | Its own `.venv` plus a local MySQL instance -- its `docker-compose.yml` is the fastest way to get one. Follow its README. |

Neither is required to run this chatbot. If one is missing or its database is
down, the host reports it under `startup_errors`, the web UI shows it as failed,
and the other servers keep working. To drop them entirely, remove those two
entries from `STDIO_SERVERS`.

### Remote servers over HTTP (rubric item 7)

`flora-mcp` speaks Streamable HTTP as well as stdio, so it can be reached from
another machine:

```bash
flora-mcp --http --port 8100              # this machine only
flora-mcp --http --host 0.0.0.0 --port 8100   # reachable from the network
```

The server has no authentication, so only bind `0.0.0.0` on a network you trust.

Point a host at any remote MCP server with `FLORA_REMOTE_MCP` -- no code change,
which matters when the URL is only known at demo time:

```env
FLORA_REMOTE_MCP=flora-remoto=http://192.168.1.50:8100/mcp
FLORA_REMOTE_MCP=https://flora.example.com/mcp,compa=https://otro.example.com/mcp
```

Entries can also be hard-coded in `HTTP_SERVERS` in `config.py`. Either way
`MCPManager` connects to them through the same code path as the local ones, and
`tests/test_remote_http.py` proves it by starting the server on a loopback port
and consuming it over HTTP.

### Running the demo on a shared network

**[CONEXIONES.md](CONEXIONES.md) is the step-by-step runbook** for all five
connection types, with a demo checklist and a troubleshooting table. What
follows is the short version.

On a LAN full of classmates' laptops, peers come and go. Before starting the
chatbot, check what is actually reachable:

```bash
python scripts/check_remote_mcp.py                                  # my URLs, and whether I'm listening
python scripts/check_remote_mcp.py http://192.168.1.20:8100/mcp     # check a peer
```

It reports layer by layer -- name resolution, TCP, MCP handshake, tool list --
and distinguishes a *refused* connection (nothing listening there) from a
*dropped* one (a firewall eating the packets), which are the two failures worth
telling apart in a room full of laptops.

Windows blocks the port on its first use; allow it once, from an **admin**
PowerShell:

```powershell
New-NetFirewallRule -DisplayName "flora-mcp" -Direction Inbound -Protocol TCP -LocalPort 8100 -Action Allow -Profile Private
```

A VPN client (NordVPN and friends) usually breaks peer-to-peer traffic on the
local network -- turn it off for the demo.

The host tolerates all of this: a remote server is TCP-probed with a short
timeout before the MCP handshake, so an absent peer costs five seconds and is
reported under `startup_errors` instead of stalling startup. Each remote's
handshake also gets its own exit stack, so a peer that accepts the connection
and then fails cannot leave half-open streams in the shared one.

### Tool names

Tools are exposed to Claude as `server__tool` (`flora__classify_species_in_country`).
Two servers can legitimately publish the same tool name -- most obviously this
project's own server reached both locally over stdio *and* remotely over HTTP --
and without the namespace the second registration silently replaces the first,
handing the model a tool list with duplicate names. The UI and the interaction
log show the plain name, since the server is already named next to it.

## The `flora-mcp` server

It runs standalone, so it can also be driven by MCP Inspector, Claude Desktop or
anyone else's host:

```bash
.venv\Scripts\python.exe -m flora_mcp.server          # stdio
.venv\Scripts\python.exe -m flora_mcp.server --http   # Streamable HTTP, port 8100
```

The process stays silent and waits for JSON-RPC on stdin -- that is normal for
stdio transport, not a hang.

| Tool | Purpose | Needs a key |
| --- | --- | --- |
| `identify_plant_from_photo` | Identify a species from a local photo via Pl@ntNet, with confidence scores. | Pl@ntNet |
| `classify_species_in_country` | Native / introduced / invasive verdict for a species in a country, with its evidence. | No |
| `get_management_recommendations` | Curated control measures for a known invasive species. | No |
| `list_country_alien_species` | Plants in a country's GRIIS register of introduced species. | No |

`identify_plant_from_photo` accepts an absolute path or a file name relative to
`workspace/` (override with `FLORA_IMAGES_DIR`), so the model can pass a name it
saw in a Filesystem listing without knowing the server's working directory.

Inspect it with MCP Inspector:

```bash
npx -y @modelcontextprotocol/inspector .venv\Scripts\python.exe -m flora_mcp.server
```

## Project layout

```
src/flora_assistant/       # the host
├── main.py                # console entry point
├── web.py                 # browser chat UI entry point (Starlette + static/)
├── static/                # web UI: index.html, style.css, app.js (no build step)
├── chatbot.py             # conversation loop + Claude tool-use cycle
├── mcp_manager.py         # owns one MCP ClientSession per server, routes tool calls
├── logging_utils.py       # request/response logging for MCP interactions
└── config.py              # which MCP servers to connect to, and how

src/flora_mcp/             # the project's own MCP server
├── server.py              # tool definitions, stdio transport
├── plantnet.py            # photo -> candidate species
├── gbif.py                # species + country -> native/introduced/invasive
└── knowledge_base.py      # curated management measures (the local half)

scripts/
└── check_remote_mcp.py    # LAN connectivity diagnostic for the remote demo

tests/                     # offline unit tests + live-API tests marked `network`
workspace/                 # photos the assistant can read
```

## Tests

```bash
.venv\Scripts\python.exe -m pytest -m "not network"
```

That covers the classification heuristic against stubbed GBIF responses and
launches `flora-mcp` as a real subprocess to exercise it over JSON-RPC. Drop the
`-m` filter to also run the tests that hit the live GBIF API.

## Extending the knowledge base

`src/flora_mcp/knowledge_base.py` is the hand-written half of the server: GBIF
says *what* a species is, not what to do about it. Add entries keyed by
lowercase scientific name, and register any synonym Pl@ntNet might return in
`SYNONYMS` so both names reach the same advice.

## Status

Working end to end. The host connects to all five servers (38 tools: Filesystem
14, Git 12, flora 4, docfinder 4, library 4), logs every MCP interaction, keeps
context across turns, and has been exercised live through both the console REPL
and the web UI -- photo identification via Pl@ntNet, classification against
GBIF, and management recommendations, plus routing to both classmates' servers.

The remote path (rubric item 7) is working too: `flora-mcp --http` serves the
same tools over Streamable HTTP, and the host has been run with the local stdio
server and the remote HTTP one connected at the same time (6 servers, 42 tools),
with Claude routing a call to the remote one specifically. Deploying it is a
matter of changing the URL, not the code.
