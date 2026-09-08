/**
 * Remote MCP server for the flora assistant, running on Cloudflare Workers.
 *
 * This is the counterpart to the local `flora-mcp` server: where that one
 * answers "is this species native, introduced or invasive *here*", this one
 * answers the taxonomy and origin questions that come before it -- what is this
 * name, really, and where in the world is the species actually from.
 *
 * Everything it needs is a public GBIF endpoint reached with `fetch`, so it has
 * no API keys, no database and no state: exactly what a stateless Worker is
 * good at, and why this half of the project is the half that can live at the
 * edge while the Pl@ntNet half stays local.
 */

import { McpServer } from "@modelcontextprotocol/server";
import { createMcpHandler } from "agents/mcp/server";
import { z } from "zod";

const GBIF = "https://api.gbif.org/v1";

type Json = Record<string, unknown>;

async function gbif(path: string, params: Record<string, string | number> = {}): Promise<Json> {
  const url = new URL(`${GBIF}/${path}`);
  for (const [key, value] of Object.entries(params)) {
    url.searchParams.set(key, String(value));
  }
  const response = await fetch(url, { headers: { accept: "application/json" } });
  if (!response.ok) {
    throw new Error(`GBIF respondio ${response.status} para ${path}`);
  }
  return (await response.json()) as Json;
}

/** Text content in the shape the MCP SDK expects. */
function json(payload: unknown) {
  return { content: [{ type: "text" as const, text: JSON.stringify(payload, null, 2) }] };
}

/**
 * Resolve a scientific name against the GBIF backbone.
 *
 * A synonym and its accepted name are different keys, and checklists are
 * indexed under whichever one their compiler used, so both are returned and
 * both are queried downstream -- the same reason the local Python server keeps
 * the pair. Eichhornia crassipes vs Pontederia crassipes is the usual case.
 */
async function matchSpecies(name: string) {
  const data = await gbif("species/match", { name });
  const usageKey = data.usageKey as number | undefined;
  if (usageKey === undefined) return null;

  return {
    usageKey,
    acceptedKey: (data.acceptedUsageKey as number | undefined) ?? usageKey,
    scientificName: data.scientificName as string,
    canonicalName: data.canonicalName as string,
    rank: data.rank as string,
    taxonomicStatus: data.status as string,
    family: data.family as string | undefined,
    kingdom: data.kingdom as string | undefined,
    matchConfidence: data.confidence as number | undefined,
  };
}

async function distributions(taxonKey: number) {
  const data = await gbif(`species/${taxonKey}/distributions`, { limit: 1000 });
  return (data.results ?? []) as Array<Json>;
}

function createServer() {
  const server = new McpServer({
    name: "flora-remote",
    version: "0.1.0",
  });

  server.registerTool(
    "lookup_species",
    {
      description:
        "Resolve a plant's scientific name against the GBIF backbone taxonomy. " +
        "Returns the accepted name, family and whether the name given was a synonym. " +
        "Use it when a name may be outdated or misspelled, before asking about its status.",
      inputSchema: { scientific_name: z.string() },
    },
    async ({ scientific_name }) => {
      const match = await matchSpecies(scientific_name);
      if (!match) {
        return json({ resolved: false, reason: `GBIF no reconoce '${scientific_name}'.` });
      }
      return json({
        resolved: true,
        input_name: scientific_name,
        ...match,
        note:
          match.taxonomicStatus === "SYNONYM"
            ? "El nombre dado es un sinonimo; el nombre aceptado es el que usan la mayoria de checklists."
            : undefined,
      });
    },
  );

  server.registerTool(
    "native_range",
    {
      description:
        "Countries where GBIF records a plant species as NATIVE, i.e. where it actually comes from. " +
        "Answers 'where is this plant originally from?'. An empty list means no checklist " +
        "publishes a native range for it, which is not the same as it having none.",
      inputSchema: { scientific_name: z.string() },
    },
    async ({ scientific_name }) => {
      const match = await matchSpecies(scientific_name);
      if (!match) {
        return json({ resolved: false, reason: `GBIF no reconoce '${scientific_name}'.` });
      }

      const keys = [...new Set([match.usageKey, match.acceptedKey])];
      const rows = (await Promise.all(keys.map(distributions))).flat();

      const native = [
        ...new Set(
          rows
            .filter((row) => row.establishmentMeans === "NATIVE" && row.country)
            .map((row) => row.country as string),
        ),
      ].sort();

      return json({
        resolved: true,
        species: match.scientificName,
        native_countries: native,
        total_distribution_records: rows.length,
        note: native.length === 0 ? "Ningun checklist publica un rango nativo para esta especie." : undefined,
      });
    },
  );

  server.registerTool(
    "occurrences_in_country",
    {
      description:
        "How many observation records GBIF holds for a plant species in one country. " +
        "Proves only that the species has been seen there -- it says nothing about whether " +
        "it is native or introduced. Country accepts an ISO 3166-1 alpha-2 code such as GT.",
      inputSchema: {
        scientific_name: z.string(),
        country_code: z.string().length(2),
      },
    },
    async ({ scientific_name, country_code }) => {
      const match = await matchSpecies(scientific_name);
      if (!match) {
        return json({ resolved: false, reason: `GBIF no reconoce '${scientific_name}'.` });
      }

      const country = country_code.toUpperCase();
      const keys = [...new Set([match.usageKey, match.acceptedKey])];
      const counts = await Promise.all(
        keys.map(async (key) => {
          const data = await gbif("occurrence/search", { taxonKey: key, country, limit: 0 });
          return (data.count as number) ?? 0;
        }),
      );

      return json({
        resolved: true,
        species: match.scientificName,
        country_code: country,
        occurrence_records: counts.reduce((a, b) => a + b, 0),
        caveat: "Presencia observada, no estatus. Para nativa/introducida/invasora use el servidor local flora.",
      });
    },
  );

  return server;
}

export default {
  fetch(request: Request, env: unknown, ctx: ExecutionContext) {
    return createMcpHandler(createServer)(request, env, ctx);
  },
};
