import {Client} from "@modelcontextprotocol/sdk/client";
import type {CallToolResult, Tool} from "@modelcontextprotocol/sdk/types.js";
import {StreamableHTTPClientTransport} from "@modelcontextprotocol/sdk/client/streamableHttp.js";
import {RESOURCE_MIME_TYPE, RESOURCE_URI_META_KEY} from "@modelcontextprotocol/ext-apps/app-bridge";
import {ChatModelAdapter} from "@assistant-ui/react";
import {ChatModelRunResult} from "@assistant-ui/react";


export const MCP_SERVER_URL = new URL('http://localhost:8000/mcp')
export const SANDBOX_PROXY_URL = new URL("http://localhost:8000/ui/sandbox.html");
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

async function getUiResource(serverInfo: ServerInfo, uri: string): Promise<UiResourceData> {
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


// ============================================================================
// MCP Chat Adapter for assistant-ui
// ============================================================================


function selectToolFromPrompt(prompt: string, tools: Map<string, Tool>): string {
    const lower = prompt.toLowerCase();

    // Try exact match first
    for (const [name] of tools) {
        if (lower.includes(name.toLowerCase())) {
            return name;
        }
    }

    // Try description match
    for (const [name, tool] of tools) {
        if (tool.description && lower.includes(tool.description.toLowerCase())) {
            return name;
        }
    }

    // Return first tool if only one exists
    if (tools.size === 1) {
        return Array.from(tools.keys())[0];
    }

    return '';
}

function extractArgsFromPrompt(prompt: string): Record<string, unknown> {
    const args: Record<string, unknown> = {};

    // Extract quoted strings
    const quotedMatch = prompt.match(/["']([^"']+)["']/);
    if (quotedMatch) {
        // args.text = quotedMatch[1];
        args.query = quotedMatch[1];
        // args.title = quotedMatch[1];
        // args.message = quotedMatch[1];
    }

    return args;
}


interface MCPChatAdapterOptions {
    serverInfo: ServerInfo;
}

export function createMCPAdapter({serverInfo}: MCPChatAdapterOptions): ChatModelAdapter {
    return {
        async run({messages, abortSignal}): Promise<ChatModelRunResult> {
            const lastMessage = messages[messages.length - 1];
            if (lastMessage.role !== 'user') return;

            const userText = lastMessage.content
                .filter(c => c.type === 'text')
                .map(c => c.text)
                .join(' ');

            // Tool selection
            const toolName = selectToolFromPrompt(userText, serverInfo.tools);
            const toolArgs = extractArgsFromPrompt(userText);

            if (!toolName) {
                const toolList = Array.from(serverInfo.tools.entries())
                    .map(([name, tool]) => `• **${name}**${tool.description ? `: ${tool.description}` : ''}`)
                    .join('\n');

                return {
                    content: [{
                        type: 'text' as const,
                        text: `I couldn't determine which tool to use. Here are the available tools:\n\n${toolList}\n\nPlease specify which tool you'd like to use.`
                    }]
                };
            }

            try {
                const toolCallInfo = callTool(serverInfo, toolName, toolArgs);

                // Wait for result
                await toolCallInfo.resultPromise;
                if (toolCallInfo.appResourcePromise)
                    await toolCallInfo.appResourcePromise

                // Yield the tool call with custom data
                return {
                    content: [{
                        type: 'tool-call' as const,
                        toolCallId: `mcp-${Date.now()}`,
                        toolName: toolName,
                        args: toolArgs,
                        result: toolCallInfo,
                    }]
                };

            } catch (error) {
                return {
                    content: [{
                        type: 'text' as const,
                        text: `\n\n❌ **Error**: ${error instanceof Error ? error.message : String(error)}`
                    }]
                };
            }

            if (abortSignal?.aborted) {
                throw new Error('Aborted');
            }
        },
        // async *run({ messages, abortSignal }) {
        //     const lastMessage = messages[messages.length - 1];
        //     if (lastMessage.role !== 'user') return;
        //
        //     const userText = lastMessage.content
        //         .filter(c => c.type === 'text')
        //         .map(c => c.text)
        //         .join(' ');
        //
        //     // Tool selection
        //     const toolName = selectToolFromPrompt(userText, serverInfo.tools);
        //     const toolArgs = extractArgsFromPrompt(userText);
        //
        //     if (!toolName) {
        //         const toolList = Array.from(serverInfo.tools.entries())
        //             .map(([name, tool]) => `• **${name}**${tool.description ? `: ${tool.description}` : ''}`)
        //             .join('\n');
        //
        //         yield {content:[{
        //             type: 'text' as const,
        //             text: `I couldn't determine which tool to use. Here are the available tools:\n\n${toolList}\n\nPlease specify which tool you'd like to use.`
        //         }]};
        //         return;
        //     }
        //
        //     // Yield tool call indicator
        //     yield {content:[{
        //         type: 'text' as const,
        //         text: `🔧 Executing **${toolName}**...\n\n`
        //     }]};
        //
        //     try {
        //         const toolCallInfo = callTool(serverInfo, toolName, toolArgs);
        //
        //         // Wait for result
        //         await toolCallInfo.resultPromise;
        //         if (toolCallInfo.appResourcePromise)
        //             await toolCallInfo.appResourcePromise
        //
        //         // Yield the tool call with custom data
        //         yield {content:[{
        //             type: 'tool-call' as const,
        //             toolCallId: `mcp-${Date.now()}`,
        //             toolName: toolName,
        //             args: toolArgs,
        //             result: toolCallInfo,
        //         }]};
        //
        //
        //         yield {content:[{
        //             type: 'text' as const,
        //             text: `\n✅ **Tool completed successfully**`
        //         }]};
        //
        //     } catch (error) {
        //         yield {content:[{
        //             type: 'text' as const,
        //             text: `\n\n❌ **Error**: ${error instanceof Error ? error.message : String(error)}`
        //         }]};
        //     }
        //
        //     if (abortSignal?.aborted) {
        //         throw new Error('Aborted');
        //     }
        // },
    };
}
