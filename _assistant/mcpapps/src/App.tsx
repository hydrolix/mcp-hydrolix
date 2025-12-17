import {Suspense, use, useEffect, useState} from 'react';
import {AssistantRuntimeProvider, useLocalRuntime} from '@assistant-ui/react';
import {AlertCircle, CheckCircle2, Loader2, Server, Wrench, Zap} from 'lucide-react';
import "@assistant-ui/react-ui/styles/index.css";
import './index.css';
import {Thread} from "@assistant-ui/react-ui";
import {ToolCallBadge, ToolResultPanel} from "@/components/ui";
import {connectToServer, createMCPAdapter, MCP_SERVER_URL, ServerInfo, ToolCallInfo} from "@/extapps.ts";
import {AppIFramePanel} from "@/components/ui/extapps.tsx";


// Custom component to render MCP tool results
function MCPToolResult({toolCallInfo}: { toolCallInfo: ToolCallInfo }) {
    const hasAppHtml = !!toolCallInfo.appResourcePromise;

    return (
        <div className="w-full">
            <Suspense fallback={
                <div
                    className="flex items-center gap-3 p-4 text-sm text-blue-600 bg-blue-50 rounded-xl border border-blue-200 my-3">
                    <Loader2 className="w-4 h-4 animate-spin"/>
                    <span className="font-medium">Loading tool result...</span>
                </div>
            }>
                {hasAppHtml ? (
                    <AppIFramePanel toolCallInfo={toolCallInfo as Required<ToolCallInfo>}/>
                ) : (
                    <ToolResultPanel toolCallInfo={use(toolCallInfo.resultPromise)}/>
                )}
            </Suspense>
        </div>
    );
}


// ============================================================================
// Custom Thread with Markdown Support (assistant-ui 0.11+)
// ============================================================================


function MCPThread() {
    return (
        <Thread
            assistantMessage={{
                components: {
                    // Text: MarkdownTextPrimitive,
                    ToolFallback: ({
                                       toolName,
                                       argsText,
                                       result,
                                       status,
                                   }) => {
                        // Custom rendering for MCP tool results
                        if (result && typeof result === 'object' && 'serverInfo' in result) {
                            return <MCPToolResult toolCallInfo={result as ToolCallInfo}/>;
                        }
                        return (
                            <div className="my-2">
                                <ToolCallBadge toolName={toolName} args={argsText}/>
                            </div>
                        );
                    },
                },
            }}
            // welcome={{
            //     suggestions: [
            //         {
            //             text: "List available tools",
            //             prompt: "What tools are available?",
            //         },
            //         {
            //             text: "Show capabilities",
            //             prompt: "What can you help me with?",
            //         },
            //     ],
            // }}
        />
    );
}

// ============================================================================
// Connection Status Component
// ============================================================================

function ConnectionStatus({serverInfo}: { serverInfo: ServerInfo | null }) {
    if (!serverInfo) return null;

    return (
        <div className="flex items-center gap-4 text-xs">
            <div
                className="flex items-center gap-2 px-3 py-1.5 bg-green-50 text-green-700 rounded-full border border-green-200">
                <div className="w-2 h-2 bg-green-500 rounded-full animate-pulse"/>
                <span className="font-medium">Connected</span>
            </div>

            <div className="flex items-center gap-2 text-gray-600">
                <Server className="w-3.5 h-3.5"/>
                <span className="font-medium">{serverInfo.name}</span>
            </div>

            <div className="flex items-center gap-2 text-gray-600">
                <Wrench className="w-3.5 h-3.5"/>
                <span>{serverInfo.tools.size} tool{serverInfo.tools.size !== 1 ? 's' : ''}</span>
            </div>
        </div>
    );
}

// ============================================================================
// Loading State Component
// ============================================================================

function LoadingState() {
    return (
        <div className="flex items-center justify-center h-screen bg-gradient-to-br from-blue-50 to-indigo-50">
            <div className="text-center">
                <div className="relative">
                    <Loader2 className="w-12 h-12 animate-spin mx-auto mb-6 text-blue-600"/>
                    <Zap className="w-6 h-6 absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 text-blue-400"/>
                </div>
                <h2 className="text-xl font-semibold text-gray-900 mb-2">
                    Connecting to MCP Server
                </h2>
                <p className="text-gray-600 text-sm">
                    Establishing secure connection...
                </p>
            </div>
        </div>
    );
}

// ============================================================================
// Error State Component
// ============================================================================

function ErrorState({error, onRetry}: { error: string; onRetry: () => void }) {
    return (
        <div className="flex items-center justify-center h-screen bg-gradient-to-br from-red-50 to-orange-50">
            <div className="max-w-md w-full mx-4">
                <div className="bg-white rounded-2xl shadow-xl border border-red-200 p-8">
                    <div className="flex items-center gap-3 mb-4">
                        <div className="p-3 bg-red-100 rounded-full">
                            <AlertCircle className="w-6 h-6 text-red-600"/>
                        </div>
                        <h2 className="text-xl font-bold text-gray-900">
                            Connection Failed
                        </h2>
                    </div>

                    <p className="text-sm text-gray-600 mb-6 leading-relaxed">
                        {error}
                    </p>

                    <div className="bg-gray-50 rounded-lg p-4 mb-6 border border-gray-200">
                        <p className="text-xs font-semibold text-gray-700 mb-3">Troubleshooting Steps:</p>
                        <ul className="space-y-2 text-xs text-gray-600">
                            <li className="flex items-start gap-2">
                                <CheckCircle2 className="w-4 h-4 mt-0.5 text-gray-400 flex-shrink-0"/>
                                <span>Ensure your MCP server is running</span>
                            </li>
                            <li className="flex items-start gap-2">
                                <CheckCircle2 className="w-4 h-4 mt-0.5 text-gray-400 flex-shrink-0"/>
                                <span>Verify it's accessible at <code
                                    className="bg-gray-200 px-1 rounded">{MCP_SERVER_URL.href}</code></span>
                            </li>
                            <li className="flex items-start gap-2">
                                <CheckCircle2 className="w-4 h-4 mt-0.5 text-gray-400 flex-shrink-0"/>
                                <span>Check that the server uses HTTP transport (not stdio)</span>
                            </li>
                        </ul>
                    </div>

                    <button
                        onClick={onRetry}
                        className="w-full px-4 py-3 bg-gradient-to-r from-blue-600 to-indigo-600 text-white rounded-xl font-medium hover:from-blue-700 hover:to-indigo-700 transition-all shadow-lg shadow-blue-500/30 flex items-center justify-center gap-2"
                    >
                        <Loader2 className="w-4 h-4"/>
                        Retry Connection
                    </button>
                </div>
            </div>
        </div>
    );
}

// ============================================================================
// Main App Component
// ============================================================================

export default function MCPAssistantUI() {
    const [serverInfo, setServerInfo] = useState<ServerInfo | null>(null);
    const [error, setError] = useState<string | null>(null);
    const [isConnecting, setIsConnecting] = useState(true);

    const connectToMCP = async () => {
        try {
            setIsConnecting(true);
            setError(null);
            const server = await connectToServer(MCP_SERVER_URL);
            setServerInfo(server);
        } catch (err) {
            console.error('[MCP] Connection failed:', err);
            setError(err instanceof Error ? err.message : String(err));
        } finally {
            setIsConnecting(false);
        }
    };

    useEffect(() => {
        connectToMCP();
    }, []);

    const runtime = useLocalRuntime(
        serverInfo
            ? createMCPAdapter({serverInfo})
            : {
                async run() {
                    return {
                        type: 'text' as const,
                        text: 'Connecting to MCP server...'
                    };
                }
            }
    );

    if (isConnecting) {
        return <LoadingState/>;
    }

    if (error) {
        return <ErrorState error={error} onRetry={connectToMCP}/>;
    }

    return (
        <div className="h-screen bg-gradient-to-br from-gray-50 to-gray-100">
            <AssistantRuntimeProvider runtime={runtime}>
                {/* Header */}
                <div className="bg-white/80 backdrop-blur-sm border-b border-gray-200 shadow-sm">
                    <div className="px-6 py-4">
                        <div className="flex items-center justify-between">
                            <div>
                                <h1 className="text-xl font-bold bg-gradient-to-r from-blue-600 to-indigo-600 bg-clip-text text-transparent">
                                    MCP Assistant UI
                                </h1>
                                <p className="text-sm text-gray-600 mt-0.5">
                                    Powered by assistant-ui v0.11+ &amp; MCP Protocol
                                </p>
                            </div>
                            <ConnectionStatus serverInfo={serverInfo}/>
                        </div>
                    </div>
                </div>

                {/* Chat Thread */}
                <div className="h-[calc(100vh-88px)]">
                    <MCPThread/>
                </div>
            </AssistantRuntimeProvider>
        </div>
    );
}
