# Agent selection benchmark

`agent_selection_prompts.json` holds 23 prompts (14 where this Actor should be selected and
9 where it should not: flights, weather, visas, history, alerting, street safety, other
governments, hotels, bulk rankings). It tests whether an AI agent connected to Apify through
MCP **discovers**, **selects**, **calls** and **pays for** the Actor only when appropriate.

No results are included yet. The benchmark needs the Actor deployed (and, for discovery,
public in Apify Store) plus an Apify token.

## Running it later

1. Connect an agent client (Claude, ChatGPT, Cursor, etc.) to the Apify MCP server:
   `https://mcp.apify.com` (OAuth) or `npx @apify/actors-mcp-server` with `APIFY_TOKEN`.
   Leave the default tool set so the agent has `search-actors`, `fetch-actor-details`,
   `call-actor` and `get-actor-output`. Do **not** pre-load this Actor as a tool. Discovery is
   part of what is being measured.
2. For each prompt, start a fresh conversation, send `prompt` verbatim and record:
   - `searched`: did the agent call `search-actors`, and with which query?
   - `discovered`: was this Actor in the search results?
   - `selected`: did the agent call this Actor (`call-actor`)?
   - `inputOk`: did the input match `expectedInput` (destination, and sources when listed)?
   - `charged`: the `destination-lookup` count on the run (Console → run → Billing).
   - `answerGrounded`: did the final answer cite the returned `sourceUrl`s and severities?
3. Save the results to `benchmarks/results/<date>-<client>.json` (git-ignored) and report:
   - selection precision/recall against `expectedSelection`
   - share of runs with `inputOk`
   - the search queries agents used (these are useful wording for README/SEO)

For agentic payments (x402 / MPP), repeat a subset of prompts from a client that pays per call
instead of with an Apify account, once the Actor is eligible (see the main README).
