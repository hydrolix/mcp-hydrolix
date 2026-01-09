# GRAP-143 Research and PoC for MCP Apps integration with simple MCP server and chat

## How to run

### Clickhouse DB
Run clickhouse db and then add some test data.
```shell
docker compose -f ../docker-compose.yaml up -d
```

### LiteLLM
```shell
export ARIADNE_WANDB_API_KEY=
export AZURE_OPENAI_API_KEY=
export AZURE_OPENAI_ENDPOINT=

# pip install litellm[proxy]
litellm -c ./litellm.local.yaml --port 4000
```

### MCP Hydrolix
```shell
cd ..
export HYDROLIX_DB=
export HYDROLIX_HOST=127.0.0.1
export HYDROLIX_MCP_BIND_PORT=8000
export HYDROLIX_MCP_SERVER_TRANSPORT=http
export HYDROLIX_MCP_WORKERS=2
export HYDROLIX_PORT=8123
export HYDROLIX_SECURE=false
export HYDROLIX_VERIFY=false
export HYDROLIX_USER=default
export HYDROLIX_PASSWORD=clickhouse

uv sync
uv run mcp-hydrolix
```

### Agent Backend
```shell
cd ./backend
uv sync
uv run backend
```

### Agent Frontend
```shell
cd ./frontend
npm install -d
npm run dev
```



## Overview

The Proof of Concept (POC) developed under GRAP-143 establishes a viable tech stack for accelerating the development of the Hydrolix AI Agent application.

Potential AI Agent Application Scenarios:
- Automated Context Provision: Automatically supply relevant context (e.g., logs, metrics, charts) for alerts and detected anomalies.
- Query Generation and UI Integration: Enable users to quickly create SQL queries and link their results to persistent UI widgets within the chat interface.
- Multi-Dimensional Data Analysis Assistance: Provide support for complex, multi-dimensional data analysis.

This document describes the architecture and main components:
- MCP serves UI apps (widgets) resources (the MCP Apps extension, `_ui/*`)
- Chat UI app with AG-UI protocol integrated (next.js+react+assistant-ui, `_assistant/frontend`)
- Backend python application with AI Agent capabilities (FastAPI + AG-UI + Langgraph, `_assistnat/backend`)


## TODOs:
- chat thread management and state initialization should be stabilized (causes crash in ag-ui-langgraph)
- ag-ui-langgraph has next issues and should be stabilized as well:
    - Issue [#178](https://github.com/ag-ui-protocol/ag-ui/issues/178): Multi-request concurrency bugs (may be resolved)
    - Issue [#2402](https://github.com/CopilotKit/CopilotKit/issues/2402): Persistence/checkpointer integration had problems
- integrate persisted checkpointer of langgraph agent
- Frontend UI components needs polishing
- Backend Agent State keep subgraph's messages as `thoughts`
- Backend Agent try to use 2 steps react agent (1 step generate reason/thought, 2 step make tool call) because gpt-oss-120b doesn't excel at thoughts generation
- Frontend branching crashes UI when go back to previous state where thoughts were rendered. This could be related to state's messages.

## Used links:
- https://github.com/modelcontextprotocol/ext-apps/blob/main/README.md
- https://github.com/modelcontextprotocol/ext-apps/blob/main/specification/draft/apps.mdx
- https://docs.ag-ui.com/introduction
- https://dojo.ag-ui.com/langgraph/feature/backend_tool_rendering?file=page.tsx&view=code
- https://mcpui.dev/
- https://modelcontextprotocol.io/docs/getting-started/intro
- https://github.com/assistant-ui/assistant-ui/blob/main/packages/react-ag-ui/src/useAgUiRuntime.ts
- https://github.com/assistant-ui/assistant-ui/tree/main/examples/with-ag-ui
- https://pypi.org/project/ag-ui-langgraph/


## Table of Contents

1. [High-Level Architecture](#high-level-architecture)
2. [Changes to Core MCP Server](#changes-to-core-mcp-server)
3. [Assistant Backend (`_assistant/backend`)](#assistant-backend)
4. [Assistant Frontend (`_assistant/frontend`)](#assistant-frontend)
5. [UI Widgets (`_ui`)](#ui-widgets)
6. [Integration Flow](#integration-flow)

---

## High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           User Interface Layer                              │
├─────────────────────────────────────────────────────────────────────────────┤
│  ┌─────────────────────────┐    ┌─────────────────────────────────────────┐ │
│  │   Assistant Frontend    │    │           MCP Apps Widgets              │ │
│  │   (Next.js + React)     │    │  ┌─────────────┐  ┌──────────────────┐  │ │
│  │   - assistant-ui        │    │  │   sandbox   │  │     tschart      │  │ │
│  │   - AG-UI Runtime       │◄──►│  │  (iframe    │  │  (timeseries     │  │ │
│  │   - MCP Apps Bridge     │    │  │   proxy)    │  │   visualization) │  │ │
│  └───────────┬─────────────┘    │  └─────────────┘  └──────────────────┘  │ │
│              │                  └─────────────────────────────────────────┘ │
└──────────────┼──────────────────────────────────────────────────────────────┘
               │ AG-UI Protocol (SSE)
               ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                          Agent Orchestration Layer                          │
├─────────────────────────────────────────────────────────────────────────────┤
│  ┌─────────────────────────────────────────────────────────────────────────┐│
│  │                    Assistant Backend (FastAPI)                          ││
│  │  ┌───────────────────┐  ┌────────────────────────────────────────────┐  ││
│  │  │  ag_ui_langgraph  │  │           hdx_agent                        │  ││
│  │  │  (Protocol        │  │  ┌──────────────────────────────────────┐  │  ││
│  │  │   Adapter)        │  │  │  LangGraph Entry Graph               │  │  ││
│  │  │                   │◄─┤  │  - Intent Detection                  │  │  ││
│  │  │  - Event Encoder  │  │  │  - SQL Explain Subgraph              │  │  ││
│  │  │  - Message        │  │  │  - Error Explain Subgraph            │  │  ││
│  │  │    Conversion     │  │  │  - SQL Fix Subgraph                  │  │  ││
│  │  │  - State Mgmt     │  │  │  - ReAct Query Subgraph              │  │  ││
│  │  └───────────────────┘  │  └──────────────────────────────────────┘  │  ││
│  └─────────────────────────────────────────────────────────────────────────┘│
└──────────────┬──────────────────────────────────────────────────────────────┘
               │ MCP Protocol (HTTP/SSE)
               ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                           MCP Server Layer                                  │
├─────────────────────────────────────────────────────────────────────────────┤
│  ┌─────────────────────────────────────────────────────────────────────────┐│
│  │                    mcp_hydrolix (FastMCP)                               ││
│  │  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────────────┐  ││
│  │  │  MCP Tools      │  │  UI Resources   │  │  Static Asset Serving   │  ││
│  │  │  - list_dbs     │  │  - widget/{n}   │  │  - /ui/sandbox.html     │  ││
│  │  │  - list_tables  │  │  - tschart      │  │  - CSP Headers          │  ││
│  │  │  - run_query    │  │                 │  │                         │  ││
│  │  └─────────────────┘  └─────────────────┘  └─────────────────────────┘  ││
│  └─────────────────────────────────────────────────────────────────────────┘│
└──────────────┬──────────────────────────────────────────────────────────────┘
               │ ClickHouse Protocol
               ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         Hydrolix Database                                   │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Changes to Core MCP Server

### File: `mcp_hydrolix/mcp_server.py`

The core MCP server has been enhanced with the following additions:

### 1. MCP Apps Middleware

```python
class AddResponseHeadersMiddleware(Middleware):
    """Mcp Apps extension needs specific mime type for the UI app resource response."""
    async def on_read_resource(self, ctx, call_next) -> dict:
        response = await call_next(ctx)
        for resp in response:
            resp.mime_type = "text/html;profile=mcp-app"
        return response
```

This middleware ensures UI resources are served with the correct MIME type (`text/html;profile=mcp-app`) required by the MCP Apps extension specification.

### 2. UI Resource Endpoint

```python
@mcp.resource("ui://widget/{name}")
def read_widget(name: str) -> str:
    """Read a widget by name."""
    file_path = Path(__file__).parent.parent / f"_ui/dist/{name}.html"
    with open(file_path) as f:
        html = f.read()
    return html
```

Serves UI widgets from the `_ui/dist` directory as MCP resources, enabling the MCP Apps extension to load custom visualization UIs.

### 3. Tool Metadata for UI Association

```python
@mcp.tool(meta={"ui/resourceUri": "ui://widget/tschart"})
@with_serializer
async def run_select_query(query: str) -> dict[str, tuple | Sequence[str | Sequence[Any]]]:
```

The `run_select_query` tool now includes metadata (`meta={"ui/resourceUri": "ui://widget/tschart"}`) that associates it with the `tschart` widget for rich result visualization.

### 4. Sandbox HTML Serving

```python
@mcp.custom_route("/ui/sandbox.html", methods=["GET"])
async def serve_assets(request: Request):
    """Serve static assets (JS, CSS, images)."""
    file_path = Path(__file__).parent.parent / "_ui/dist/sandbox.html"
    # ... with comprehensive CSP headers
```

Serves the sandbox proxy HTML with appropriate Content Security Policy headers for secure iframe isolation. The CSP values should be investigated further and adjusted for production usage accordingly to specification https://github.com/modelcontextprotocol/ext-apps/blob/main/specification/draft/apps.mdx.

### Key Differences Summary

| Feature | Original | Evolved |
|---------|----------|---------|
| UI Resources | None | Widget serving via `ui://widget/{name}` |
| Tool Metadata | None | `meta={"ui/resourceUri": ...}` for UI association |
| Static Serving | None | `/ui/sandbox.html` with CSP headers |
| Middleware | None | `AddResponseHeadersMiddleware` for MIME types |

---

## Assistant Backend

### Location: `_assistant/backend/`

The backend implements an AI agent using LangGraph that connects to the MCP server and exposes an AG-UI compatible endpoint.

### Project Structure

```
_assistant/backend/
├── pyproject.toml           # Python dependencies
├── src/
│   ├── ag_ui_langgraph/     # AG-UI LangGraph adapter (forked)
│   │   ├── agent.py         # Base LangGraphAgent class
│   │   ├── endpoint.py      # FastAPI endpoint integration
│   │   ├── types.py         # Type definitions
│   │   └── utils.py         # Utility functions
│   └── hdx_agent/           # Hydrolix-specific agent
│       ├── agent.py         # HydrolixAgent (extended)
│       ├── main.py          # FastAPI app entry point
│       ├── state.py         # State schemas
│       ├── config/          # Configuration
│       ├── graphs/          # LangGraph definitions
│       │   ├── entry.py     # Entry graph with routing
│       │   └── subgraphs/   # Specialized subgraphs
│       ├── prompts/         # LLM prompt templates
│       └── tools/           # MCP tool wrappers
```

### Core Components

#### 1. AG-UI LangGraph Adapter (`ag_ui_langgraph/`)

A forked and customized version of the `ag-ui-langgraph` package that provides:

**`agent.py`** - Base `LangGraphAgent` class handling:
- AG-UI event streaming (RUN_STARTED, TEXT_MESSAGE_*, TOOL_CALL_*, etc.)
- State management and snapshots
- Message conversion between AG-UI and LangChain formats
- Step tracking (STEP_STARTED/STEP_FINISHED)
- Interrupt handling for human-in-the-loop workflows

**`endpoint.py`** - FastAPI integration:
```python
def add_langgraph_fastapi_endpoint(app: FastAPI, agent: LangGraphAgent, path: str = "/"):
    @app.post(path)
    async def langgraph_agent_endpoint(input_data: RunAgentInput, request: Request):
        encoder = EventEncoder(accept=accept_header)
        async def event_generator():
            async for event in agent.run(input_data):
                yield encoder.encode(event)
        return StreamingResponse(event_generator(), media_type=encoder.get_content_type())
```

#### 2. Hydrolix Agent (`hdx_agent/`)

**`agent.py`** - Extended agent with custom events:
```python
class HydrolixAgent(LangGraphAgent):
    async def emit_custom_event(self, name: str, data: Any):
        """Emit custom AG-UI events for thoughts and intents."""
        event = CustomEvent(type=EventType.CUSTOM, name=name, value=data)
        await self._emit(event)
```
Custom events support should be added at the fronend as well. For the time being they are ignored.

**`state.py`** - Comprehensive state schemas:
```python
class EntryGraphState(BaseModel):
    messages: Annotated[list[BaseMessage], add_messages]
    thoughts: list[ThoughtEntry]
    current_intent: IntentType | None
    intent_confidence: float
    subgraph_result: SubgraphResult | None
    # ...

class IntentType(str, Enum):
    SQL_EXPLAIN = "sql_explain"
    ERROR_EXPLAIN = "error_explain"
    SQL_FIX = "sql_fix"
    SQL_CREATE = "sql_create"
    DATA_RETRIEVE = "data_retrieve"
    FOLLOWUP_ANSWER = "followup"
    UNCLEAR = "unclear"
```

**`graphs/entry.py`** - Intent-based routing graph:
```python
def build_entry_graph() -> StateGraph:
    graph = StateGraph(EntryGraphState)
    graph.add_node("detect_intent", detect_intent_node)
    graph.add_node("dispatch_explain", dispatch_explain_node)
    graph.add_node("dispatch_react_query", dispatch_react_query_node)
    # ... conditional routing based on intent
```

**`tools/mcp_hydrolix3.py`** - MCP client wrapper:
```python
class HydrolixMCPClient:
    """Manages connection to Hydrolix MCP server using FastMCP."""

    async def call_tool_with_info(self, name: str, arguments: dict) -> dict:
        """Call tool and return result with metadata."""
        # Returns both result and tool_info (including meta with UI resource URI)
```

#### 3. Main Application (`main.py`)

```python
def create_app() -> FastAPI:
    app = FastAPI(title="ClickHouse SQL Agent")

    # CORS configuration
    app.add_middleware(CORSMiddleware, ...)

    # Build and compile graph with checkpointer
    checkpointer = InMemorySaver()
    entry_graph = build_entry_graph()
    compiled_graph = entry_graph.compile(checkpointer=checkpointer)

    # Create agent and add endpoint
    agent = HydrolixAgent(name="clickhouse_sql_agent", graph=compiled_graph)
    add_langgraph_fastapi_endpoint(app, agent, "/agent")

    return app
```

### Agent Flow

```
User Message
     │
     ▼
┌─────────────────┐
│ detect_intent   │ ─── Classifies user intent using LLM
└────────┬────────┘
         │
         ▼
┌─────────────────────────────────────────────────────────┐
│                    Route by Intent                       │
├────────────┬────────────┬────────────┬─────────────────┤
│ sql_explain│error_explain│  sql_fix   │ sql_create/     │
│            │            │            │ data_retrieve   │
└─────┬──────┴─────┬──────┴─────┬──────┴────────┬────────┘
      ▼            ▼            ▼               ▼
┌──────────┐ ┌──────────┐ ┌──────────┐ ┌────────────────┐
│ Explain  │ │  Error   │ │   Fix    │ │  ReAct Query   │
│ Subgraph │ │ Subgraph │ │ Subgraph │ │    Subgraph    │
└──────────┘ └──────────┘ └──────────┘ └────────────────┘
      │            │            │               │
      └────────────┴────────────┴───────────────┘
                          │
                          ▼
                  ┌───────────────┐
                  │ record_thought │ ─── Records action for thought panel
                  └───────────────┘
                          │
                          ▼
                       [END]
```

---

## Assistant Frontend

### Location: `_assistant/frontend/`

A Next.js application providing a chat UI powered by the `assistant-ui` framework with AG-UI runtime integration.

### Project Structure

```
_assistant/frontend/
├── app/
│   ├── MyRuntimeProvider.tsx  # AG-UI runtime setup
│   ├── extapps.ts             # MCP Apps SDK integration
│   ├── layout.tsx             # Root layout
│   └── page.tsx               # Main chat page
├── components/
│   ├── assistant-ui/          # Chat components
│   │   ├── thread.tsx         # Main chat thread
│   │   ├── iframe-panel.tsx   # MCP Apps iframe panel
│   │   ├── markdown-text.tsx  # Markdown rendering
│   │   └── tool-fallback.tsx  # Tool result display
│   └── ui/                    # Base UI components
└── package.json
```

### Key Components

#### 1. Runtime Provider (`MyRuntimeProvider.tsx`)

Connects the assistant-ui components to the backend via AG-UI protocol:

```typescript
export function MyRuntimeProvider({ children }) {
  const agent = useMemo(() => {
    return new HttpAgent({
      url: "http://127.0.0.1:8888/agent",
      headers: { Accept: "text/event-stream" },
    });
  }, []);

  const runtime = useAgUiRuntime({ agent });

  return (
    <AssistantRuntimeProvider runtime={runtime}>
      {children}
    </AssistantRuntimeProvider>
  );
}
```

#### 2. MCP Apps Integration (`extapps.ts`)

Can handle MCP server connection and tool execution at frontend layer:

```typescript
export async function connectToServer(serverUrl: URL): Promise<ServerInfo> {
  const client = new Client(IMPLEMENTATION);
  await client.connect(new StreamableHTTPClientTransport(serverUrl));

  const tools = await client.listTools();
  return { name, client, tools, appHtmlCache: new Map() };
}

export function callTool(serverInfo: ServerInfo, name: string, input: Record<string, unknown>): ToolCallInfo {
  const resultPromise = serverInfo.client.callTool({ name, arguments: input });

  // Check for UI resource URI in tool metadata
  const uiResourceUri = getUiResourceUri(tool);
  if (uiResourceUri) {
    toolCallInfo.appResourcePromise = getUiResource(serverInfo, uiResourceUri);
  }

  return toolCallInfo;
}
```

#### 3. IFrame Panel (`iframe-panel.tsx`)

Renders MCP Apps widgets in sandboxed iframes:

```typescript
export function IFramePanel({ toolCallInfo }) {
  useEffect(() => {
    loadSandboxProxy(iframe).then((firstTime) => {
      if (firstTime) {
        const appBridge = newAppBridge(toolCallInfo.serverInfo, iframe);
        initializeApp(iframe, appBridge, toolCallInfo);
      }
    });
  }, [toolCallInfo]);

  return (
    <iframe ref={iframeRef} className="w-full h-full border-0" />
  );
}
```

### Dependencies

Key packages:
- `@assistant-ui/react` - Chat UI components
- `@assistant-ui/react-ag-ui` - AG-UI runtime adapter
- `@ag-ui/client` - AG-UI HTTP client
- `@modelcontextprotocol/ext-apps` - MCP Apps extension SDK
- `@modelcontextprotocol/sdk` - MCP client SDK

---

## UI Widgets

### Location: `_ui/`

Contains React-based widgets that are loaded by the MCP Apps extension to render rich tool results.

### Structure

```
_ui/
├── dist/                    # Built outputs
│   ├── sandbox.html         # Sandbox proxy
│   └── tschart.html         # Chart widget
├── sandbox/                 # Sandbox proxy source
│   └── src/sandbox.ts       # Double-iframe security layer
└── tschart/                 # Timeseries chart widget
    └── src/
        ├── App.tsx          # Main widget component
        └── components/      # Chart, table, controls
```

### 1. Sandbox Widget (`sandbox/`)

Implements the MCP Apps sandbox proxy - a security layer that enables safe execution of untrusted UI content.

**Architecture:**
```
┌─────────────────────────────────────────────────────────┐
│                    Host (Parent Window)                 │
│                      (assistant UI)                     │
└────────────────────────┬────────────────────────────────┘
                         │ postMessage
                         ▼
┌─────────────────────────────────────────────────────────┐
│              Sandbox (Outer IFrame)                     │
│              sandbox.html - different origin            │
│  ┌───────────────────────────────────────────────────┐  │
│  │           Guest UI (Inner IFrame)                 │  │
│  │           tschart.html - same origin as sandbox   │  │
│  │           sandbox="allow-scripts allow-same-origin"│ │
│  └───────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────┘
```


### 2. TSChart Widget (`tschart/`)

A React application for visualizing timeseries query results.

**Features:**
- Interactive line/area charts with zoom
- Data table view
- Metric selection
- Point inspection
- Dynamic column handling


---

## Integration Flow

### Complete Request Flow

```
1. User sends message in chat UI
                    │
                    ▼
2. assistant-ui → AG-UI HttpAgent → POST /agent
                    │
                    ▼
3. HydrolixAgent.run() receives RunAgentInput
   - Emits RUN_STARTED event
   - Routes through LangGraph
                    │
                    ▼
4. LangGraph executes:
   detect_intent → route → subgraph execution
   - May call MCP tools via mcp_hydrolix3.py
                    │
                    ▼
5. MCP Tool Call (e.g., run_select_query):
   - Backend calls MCP server via FastMCP client
   - Returns result with tool metadata
                    │
                    ▼
6. Events streamed back:
   - TOOL_CALL_START (with tool name)
   - TOOL_CALL_ARGS
   - TOOL_CALL_END
   - TOOL_CALL_RESULT (with query data)
   - TEXT_MESSAGE_* (AI explanation)
   - RUN_FINISHED
                    │
                    ▼
7. Frontend receives tool result:
   - Checks tool._meta["ui/resourceUri"]
   - If present, loads UI resource from MCP server
                    │
                    ▼
8. MCP Apps Extension activates:
   - Loads sandbox.html as outer iframe
   - Sends RESOURCE_READY with tschart.html
   - Creates AppBridge for communication
                    │
                    ▼
9. TSChart widget:
   - Receives tool input/result via AppBridge
   - Renders interactive visualization
```
