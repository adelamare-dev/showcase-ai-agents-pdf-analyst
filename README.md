# A2UI PDF Analyst

Chat with your PDF and watch the agent build the UI for each answer. Powered by **A2UI v0.9 (Agent-to-UI)** — the open protocol that lets an agent describe a surface as structured component operations your frontend renders against its own design system. Same chat input, two rendering strategies, one shared 21-component catalog. The UI, the agent's replies and the surfaces it draws are in French, with fr-FR number formats (`1 234,5`, `6,1 %`, `1,5 M`).

https://github.com/user-attachments/assets/c053d2e8-1d40-43cb-8c5a-8e5c121b851f

**Three routes:**

- **`/fixed`** — hand-authored JSON dashboard. The agent only extracts the data (KPIs, trend, segment splits, table rows) and fills the slots. Predictable layout, brand-locked, single LLM call per turn. Best when the shape of the answer is known up front.
- **`/dynamic`** — no pre-written layout. The agent reads the question, picks components from the catalog, and composes the surface on the fly. A net-income query lands as a single StatCard; a segment breakdown becomes a DonutChart; a research-paper summary composes Overline + Heading + Text + Callout + BulletList. Best when the right answer's _form_ varies with the question.
- **`/catalog`** — every component rendered live, filterable by group (Layout, Content, Data viz, Interactive). Doubles as a sanity check on the renderers and a reference for what the agent is allowed to draw from.

All three routes share the same brand tokens (`src/a2ui/theme.css`), the same React renderers (`src/a2ui/catalog/renderers.tsx`), and the same client-side PDF text extraction pipeline (`src/lib/pdf.ts`). Re-skin one stylesheet, every surface updates.

Each tool call shows up as a live step in the chat ("Lecture du document…", "Conception de l'interface…") with the name of the model that runs it, and turns into a failure line if the provider rejects the call.

## Prerequisites

- Node.js 20+ and [pnpm](https://pnpm.io/) (pnpm only)
- Python 3.12
- [uv](https://docs.astral.sh/uv/) for the Python agent
- A Mistral API key (a free one from [console.mistral.ai](https://console.mistral.ai/) is enough)

## Run locally

```bash
git clone https://github.com/adelamare-dev/showcase-ai-agents-pdf-analyst.git
cd showcase-ai-agents-pdf-analyst
cp agent/.env.example agent/.env    # then put your MISTRAL_API_KEY in agent/.env
pnpm install                         # installs Next.js + runs `uv sync` for the agent
pnpm dev                             # boots web on :3000, agent on :8123
```

Open <http://localhost:3000>. On `/fixed` and `/dynamic`, the "Essayer un exemple" buttons load a bundled sample PDF in one click. Optionally, run installs through [Socket Firewall](https://socket.dev/): `sfw pnpm i`.

**Windows:** keep the clone path short (around 100 characters or less). pnpm's
store paths under `node_modules/.pnpm` add up to ~135 characters, and Turbopack
fails with `Module not found` once a resolved path exceeds 260 characters
(`MAX_PATH`) while Windows long paths are disabled.

Originally published in [CopilotKit/CopilotKit](https://github.com/CopilotKit/CopilotKit/tree/main/examples/showcases/a2ui-pdf-analyst) (MIT, see `LICENSE`).

## Environment variables

`agent/.env`:

| Variable          | Required | Notes                                                                                 |
| ----------------- | -------- | ------------------------------------------------------------------------------------- |
| `MISTRAL_API_KEY` | yes      | used by the main agent and by the secondary LLMs inside `query_pdf` / `generate_a2ui` |

## Architecture

```
a2ui-pdf-analyst/
├── package.json              → Next.js manifest + concurrently runs the agent alongside
├── next.config.ts
├── postcss.config.mjs
├── tsconfig.json
├── public/                   → static assets (brand SVGs) + samples/ (open-licensed demo PDFs)
├── src/                      → Next.js 16 · React 19 · Tailwind v4
│   ├── app/
│   │   ├── api/copilotkit/   → CopilotKit V2 runtime endpoint (HttpAgent → Python)
│   │   ├── fixed/            → fixed-schema route: pre-authored dashboard
│   │   ├── dynamic/          → dynamic-schema route: agent invents the layout
│   │   ├── catalog/          → live showcase of all 21 components
│   │   ├── globals.css       → app-wide tokens, fonts
│   │   ├── layout.tsx        → root layout + Providers
│   │   └── page.tsx          → overview
│   ├── a2ui/
│   │   ├── catalog/
│   │   │   ├── definitions.ts → Zod prop schemas + agent-facing descriptions
│   │   │   ├── renderers.tsx  → React renderers (Recharts charts, tables, cards)
│   │   │   └── index.ts       → createCatalog() (definitions + renderers, catalogId)
│   │   ├── theme.css          → brand tokens, scoped to .a2ui-surface
│   │   ├── surface-bus.ts     → per-agent A2UI op stream the canvas subscribes to
│   │   └── MirrorRenderer.tsx → activity renderer that forwards ops to the canvas
│   ├── components/
│   │   ├── SurfaceCanvas.tsx        → mounts A2UIProvider + renders surfaces
│   │   ├── FilteredUserMessage.tsx  → strips inlined PDF text from chat
│   │   ├── PdfChatChrome.tsx        → truncation status bar + confidentiality note
│   │   ├── ToolStep.tsx             → live chat step for each tool call
│   │   ├── SampleBar.tsx            → "Essayer un exemple" + suggested questions
│   │   ├── FilteredAssistantMessage.tsx → suppresses JSON-shaped agent replies, drops images
│   │   ├── Split.tsx                → VS-Code-style resizable chat/canvas split
│   │   ├── Providers.tsx            → <CopilotKit> + activity renderers
│   │   └── Brand.tsx                → SiteNav + PageHeader
│   └── lib/
│       ├── agent-steps.ts          → chat step labels per tool, model names, tool-failure check
│       ├── chat-labels.ts          → French labels for the chat chrome
│       ├── format.ts               → fr-FR number formatting and amount parsing
│       ├── upload-errors.ts        → French messages for attachment errors
│       ├── pdf.ts                  → client-side PDF text extraction (pdfjs-dist) + text cap
│       ├── use-pdf-attachments.ts  → attachment handling, truncation note
│       └── samples.ts              → sample catalogue and French suggested questions
└── agent/                    → Python · LangChain · LangGraph · FastAPI · AG-UI
    ├── main.py               → /fixed and /dynamic FastAPI endpoints (server-to-server only)
    ├── pyproject.toml
    ├── uv.lock
    ├── scripts/measure.py    → latency and token measurement
    └── src/
        ├── models.py         → model IDs, temperature, retry and timeout (single home); stream adapter for the agent model
        ├── locale.py         → output-language rule shared by the agent prompts (French, fr-FR formats)
        ├── catalog.py        → CATALOG_ID + system-prompt fragment listing components
        ├── fixed_agent.py    → render_dashboard backend tool
        ├── dynamic_agent.py  → query_pdf + generate_a2ui tools
        ├── pdf_tools.py      → query_pdf: question → structured JSON answer, document read from state
        ├── multimodal_middleware.py → ag-ui-langgraph patch so PDF text survives the trip to the model API
        └── a2ui/schemas/dashboard.json → the fixed dashboard layout (Stack / Grid / charts / table)
```

## How it works

**PDF attachment** — CopilotKit's multimodal attachment support lets the user attach a PDF directly in the chat input. The frontend extracts the text client-side via `pdfjs-dist` and inlines it into the user message under a `[Document: <filename>]` header. Text items are regrouped by their position on the page (`pageTextFromItems`, `src/lib/pdf.ts`), one line per row with cells separated by ` | `, because a PDF can draw a table's header after its values; pages laid out in several columns and rotated pages keep the order of the PDF. `multimodal_middleware.py` patches `ag-ui-langgraph` so this text block survives serialization and arrives intact at the model. The `query_pdf` tool itself reads the most recent `[Document: ...]` block from the graph state (the agent only checks that a document exists before calling it) — attach once, ask many questions.

**Text cap** — extraction is capped in the browser at `PDF_TEXT_MAX_CHARS` (60 000 characters, `src/lib/pdf.ts`), cut at a page boundary. When a document is truncated, the status bar shows "Document tronqué : pages 1 à N sur M" and the agent receives the same note. Reading also stops once the cap is passed, and after `PDF_MAX_PAGES` (1 000) pages, so a huge PDF cannot freeze the tab. The agent keeps a slightly higher per-document guard (`DOCUMENT_MAX_CHARS`, 61 000 characters, `agent/src/multimodal_middleware.py`) against a client that bypasses the browser; it never cuts a normal upload. A PDF with no extractable text (a scan) is refused with an error message. A confidentiality line under the composer reminds users that this is a free-tier demo.

**Live steps** — each tool call renders as a one-line step in the chat (`src/components/ToolStep.tsx`, labels in `src/lib/agent-steps.ts`) showing the model that runs it. Mistral sends a whole tool call in a single chunk, which `ag-ui-langgraph` would drop; the agent model is therefore built by `agent_chat_model()` in `agent/src/models.py`, a stream adapter that splits the call into start, arguments and end so the step appears while the tool runs.

**Local hardening** — the agent listens on `127.0.0.1` and refuses any request that carries an `Origin` header, so a web page open in your browser cannot run it and spend your Mistral quota; only the Next.js runtime, server to server, calls it. A Content-Security-Policy (`next.config.ts`) only lets the browser load images from the app itself, and chat replies are rendered without images, so a prompt-injected PDF cannot leak data through an image URL. pdf.js parses PDFs with `isEvalSupported: false`, and its worker is served by the app, so an upload contacts no third party. A turn is bounded too: on `/dynamic` the code imposes its one valid course instead of asking the model (`PdfTurnRoutingMiddleware`, `agent/src/dynamic_agent.py`), so a document cannot talk the agent into looping, tool calls run one at a time, `query_pdf` runs at most twice even if the provider ignored that routing, and the agent keeps at most 32 conversations in memory.

**Language** — the agent answers and writes surface text in French; the rule lives in `agent/src/locale.py`. Numbers are shown fr-FR by `src/lib/format.ts`.

**Samples** — on `/fixed` and `/dynamic`, "Essayer un exemple" loads a bundled PDF and shows clickable French suggested questions that send the question together with the document. Suggestions appear only before the first message and only while the sample is the loaded document.

**Fixed schema (`/fixed`)** — `agent/src/a2ui/schemas/dashboard.json` is a static A2UI component tree the agent never touches. The `render_dashboard` tool takes typed arguments (KPIs, trend, share, rows, scope chips), packages them as A2UI `update_data_model` ops, and the existing tree picks them up via `{path}` bindings. One LLM pass, one tool call, surface streams in.

**Dynamic schema (`/dynamic`)** — five steps per turn. Once a document is attached, each model call has its tool imposed by `tool_choice`; without one, no tool is allowed and the agent asks for a PDF.

1. User attaches a PDF and asks a question. Frontend inlines the PDF text into the message.
2. Agent calls `query_pdf(question)` → the tool reads the latest attached document from the graph state, and a sub-LLM returns structured JSON: `shape_hint`, `title`, `summary`, `data`. If its answer is unusable, the surface says so instead of guessing.
3. Agent calls `generate_a2ui` (no arguments; it re-reads the message history without the document text, so `query_pdf` is the only source of numbers) → spawns a second sub-LLM bound to a no-op `render_a2ui` shim with `tool_choice` forced to that shim.
4. The second LLM's tool-call arguments (surfaceId, catalogId, components, data) become A2UI `create_surface` + `update_components` + `update_data_model` operations.
5. The JS-side A2UI middleware detects `a2ui_operations` in the tool result and emits the snapshot events the canvas listens for. Surface renders, and the turn ends there.

## Sample PDFs

The one-click "Essayer un exemple" buttons use open-licensed PDFs bundled in `public/samples/`; titles, licences and attribution are in [`public/samples/SOURCES.md`](public/samples/SOURCES.md). The documents below are not bundled (no open licence): they are plain links.

These work well for the dynamic-schema demo:

- Apple Q4 FY24 Consolidated Financial Statements ([download](https://www.apple.com/newsroom/pdfs/fy2024-q4/FY24_Q4_Consolidated_Financial_Statements.pdf)) — structured tables, multiple categorical breakdowns
- Tesla Q3 2024 Update ([download](https://www.tesla.com/sites/default/files/downloads/TSLA-Q3-2024-Update.pdf)) — multi-quarter time-series + production / delivery pairs
- Anthropic's _Constitutional AI: Harmlessness from AI Feedback_ ([download](https://arxiv.org/pdf/2212.08073)) — research paper, mostly prose, for text-heavy explainer surfaces

## Prompts to try

The prompts are in French, like the UI. On `/dynamic` after attaching a PDF:

| Ask the agent                                                                                 | Expected surface                      |
| --------------------------------------------------------------------------------------------- | ------------------------------------- |
| `Quel a été le résultat net du dernier trimestre ?`                                           | one StatCard                          |
| `Répartis iPhone, Mac, iPad, Wearables et Services dans un graphique en anneau.`              | DonutChart                            |
| `Montre le chiffre d'affaires du T4 par catégorie en barres horizontales.`                    | HorizontalBarChart                    |
| `Trace la production face aux livraisons sur les 5 derniers trimestres en nuage de points.`    | ScatterChart                          |
| `Explique l'idée principale de cet article en termes simples.`                                | Heading + Text + Callout + BulletList |
| `Montre l'évolution du chiffre d'affaires sur les 6 derniers trimestres.`                     | LineChart                             |

On `/fixed` after attaching a PDF:

| Ask the agent                               | What happens                                                           |
| ------------------------------------------- | ---------------------------------------------------------------------- |
| `Affiche le tableau de bord.`               | full dashboard with KPIs, trend chart, share donut, table, scope chips |
| `Passe à l'exercice 2024.` (or click the chip "Exercice 2024") | re-renders the same dashboard with fiscal-year data |

## Development

Model IDs, temperature (0), a single attempt per call (no retry) and a 45 s timeout live in `agent/src/models.py`; the timeout was set from a measurement.

```bash
pnpm test:web                         # front pure logic (node --test): PDF cap, formats, upload errors, agent steps
pnpm lint
pnpm exec tsc --noEmit
cd agent
uv run pytest                         # fake models, no network
uv run --with "pyright[nodejs]" pyright src tests scripts
uv run python scripts/measure.py --dry-run   # no network
```

Without `--dry-run`, `scripts/measure.py` makes real Mistral calls (at most 12 turns per run) and reports latency and tokens per call. Options: `--agent-model`, `--extractor-model`, `--render-model`, `--repeat`, `--extra ROUTE PDF_PATH QUESTION`, `--cap`.

## Tech stack

| Layer          | Stack                                                                                                                                  |
| -------------- | -------------------------------------------------------------------------------------------------------------------------------------- |
| Frontend       | Next.js 16 · React 19 · Tailwind v4 · TypeScript · `@copilotkit/react-core/v2` · `@copilotkit/a2ui-renderer` · `pdfjs-dist` · Recharts |
| Runtime bridge | `@copilotkit/runtime/v2` · `@ag-ui/client` (HttpAgent)                                                                                 |
| Backend        | Python 3.12 · FastAPI · `ag-ui-langgraph` · `copilotkit` (Python SDK) · `langchain` agents + LangGraph · `langchain-mistralai`        |
| Model          | Ministral 3 3B (`ministral-3b-2512`) for the main agents; Ministral 3 8B (`ministral-8b-2512`) for `query_pdf` and `generate_a2ui`     |
