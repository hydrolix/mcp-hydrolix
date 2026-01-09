import {Client} from "@modelcontextprotocol/sdk/client";
import type {CallToolResult, Tool} from "@modelcontextprotocol/sdk/types.js";
import {StreamableHTTPClientTransport} from "@modelcontextprotocol/sdk/client/streamableHttp.js";
import {RESOURCE_MIME_TYPE, RESOURCE_URI_META_KEY} from "@modelcontextprotocol/ext-apps/app-bridge";


export const MCP_SERVER_URL = new URL((process.env["NEXT_PUBLIC_MCP_SERVER_URL"] as string | undefined) ?? "http://127.0.0.1:8000/mcp")
export const SANDBOX_PROXY_URL = new URL((process.env["NEXT_PUBLIC_SANDBOX_PROXY_URL"] as string | undefined) ?? "http://127.0.0.1:8000/ui/sandbox.html");
export const IMPLEMENTATION = {name: "MCP Assistant UI", version: "2.0.0"};

export interface ServerInfo {
    name: string;
    client: Client;
    tools: Map<string, Tool>;
    appHtmlCache: Map<string, string>;
}

export interface UiResourceData {
    html: string;
    csp?: {
        connectDomains?: string[];
        resourceDomains?: string[];
    };
}

export interface ToolCallInfo {
    serverInfo: ServerInfo;
    tool: Tool;
    input: Record<string, unknown>;
    resultPromise: Promise<CallToolResult>;
    appResourcePromise?: Promise<UiResourceData>;
}


// ============================================================================
// MCP Connection Functions
// ============================================================================

export async function connectToServer(serverUrl: URL): Promise<ServerInfo> {
    const client = new Client(IMPLEMENTATION);
    await client.connect(new StreamableHTTPClientTransport(serverUrl));

    const name = client.getServerVersion()?.name ?? serverUrl.href;
    const toolsList = await client.listTools();
    const tools = new Map<string, Tool>(toolsList.tools.map((tool: Tool) => [tool.name, tool]));

    console.log('[MCP] Connected to server:', name);
    console.log('[MCP] Available tools:', Array.from(tools.keys()));

    return {name, client, tools, appHtmlCache: new Map()};
}

function getUiResourceUri(tool: Tool): string | undefined {
    const uri = tool._meta?.[RESOURCE_URI_META_KEY];
    if (typeof uri === "string" && uri.startsWith("ui://")) {
        return uri;
    }
}

export async function getUiResource(serverInfo: ServerInfo, uri: string): Promise<UiResourceData> {
    const resource = await serverInfo.client.readResource({uri});
    if (!resource || resource.contents.length !== 1) {
        throw new Error(`Invalid resource: ${uri}`);
    }

    const content = resource.contents[0];
    if (content.mimeType !== RESOURCE_MIME_TYPE) {
        throw new Error(`Unsupported MIME type: ${content.mimeType}`);
    }

    const html = "blob" in content ? atob(content.blob) : content.text;
    const contentMeta = (content as any)._meta || (content as any).meta;
    const csp = contentMeta?.ui?.csp;

    return {html, csp};
}

export function callTool(serverInfo: ServerInfo, name: string, input: Record<string, unknown>): ToolCallInfo {
    console.log('[MCP] Calling tool:', name, input);
    const resultPromise = serverInfo.client.callTool({name, arguments: input}) as Promise<CallToolResult>;

    const tool = serverInfo.tools.get(name);
    if (!tool) throw new Error(`Unknown tool: ${name}`);

    const toolCallInfo: ToolCallInfo = {serverInfo, tool, input, resultPromise};

    const uiResourceUri = getUiResourceUri(tool);
    if (uiResourceUri) {
        toolCallInfo.appResourcePromise = getUiResource(serverInfo, uiResourceUri);
    }

    return toolCallInfo;
}
