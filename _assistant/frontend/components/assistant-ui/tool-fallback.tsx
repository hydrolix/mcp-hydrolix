import type {ToolCallMessagePartComponent} from "@assistant-ui/react";
import {CheckIcon, ChevronDownIcon, ChevronUpIcon, XCircleIcon,} from "lucide-react";
import {useEffect, useMemo, useState} from "react";
import {Button} from "@/components/ui/button";
import {cn} from "@/lib/utils";
import {IFramePanel} from "./iframe-panel";
import {connectToServer, getUiResource, MCP_SERVER_URL, ServerInfo, ToolCallInfo,} from "@/app/extapps";
import {RESOURCE_URI_META_KEY} from "@modelcontextprotocol/ext-apps/app-bridge";
import {CallToolResult} from "@modelcontextprotocol/sdk/types.js";

export const ToolFallback: ToolCallMessagePartComponent = ({
                                                               toolName,
                                                               argsText,
                                                               result,
                                                               status,
                                                           }) => {
    const [isCollapsed, setIsCollapsed] = useState(true);
    const [serverInfo, setServerInfo] = useState<ServerInfo>();
    const [toolCallInfo, setToolCallInfo] = useState<ToolCallInfo>();

    const isCancelled =
        status?.type === "incomplete" && status.reason === "cancelled";
    const cancelledReason =
        isCancelled && status.error
            ? typeof status.error === "string"
                ? status.error
                : JSON.stringify(status.error)
            : null;

    // Parse result and check for UI - use useMemo to avoid recalculating on every render
    const parsedResult = useMemo(() => {
        if (!result) {
            return {hasUI: false, parsed: null, error: "", tool: {}, meta: {}};
        }

        const _result = typeof result === "string" ? JSON.parse(result) : result;
        const error = _result.error ?? "";
        const tool = _result.tool_info ?? {};
        const meta = tool.meta ?? {};
        const content = _result.content;

        const metaUri = meta?.[RESOURCE_URI_META_KEY];
        const hasUI = typeof metaUri === "string" && metaUri.startsWith("ui://");

        return {hasUI, parsed: content, error, tool, meta};
    }, [result]);

    // Load server info when we have UI
    useEffect(() => {
        if (!parsedResult.hasUI || isCollapsed || isCancelled) {
            setServerInfo(undefined);
            return;
        }

        const loadServerInfo = async () => {
            const data = await connectToServer(MCP_SERVER_URL);
            setServerInfo(data);
        };
        loadServerInfo();
    }, [parsedResult.hasUI, isCollapsed, isCancelled]);

    // Build toolCallInfo when we have serverInfo and result
    useEffect(() => {
        if (!parsedResult.hasUI || !serverInfo) {
            setToolCallInfo(undefined);
            return;
        }

        const {parsed, error, tool, meta} = parsedResult;
        const uri = meta?.[RESOURCE_URI_META_KEY];

        const toolCallResult: CallToolResult = {
            content: [
                {
                    type: "text",
                    text: error !== "" ? error : JSON.stringify(parsed),
                    _meta: meta,
                },
            ],
            structuredContent: parsed,
            isError: error !== "",
        };

        const _toolCallInfo: ToolCallInfo = {
            input: {},
            serverInfo: serverInfo,
            tool: tool,
            resultPromise: Promise.resolve(toolCallResult),
            appResourcePromise: getUiResource(serverInfo, uri),
        };

        setToolCallInfo(_toolCallInfo);
    }, [serverInfo, parsedResult.hasUI]);

    return (
        <div
            className={cn(
                "aui-tool-fallback-root mb-4 flex w-full flex-col gap-3 rounded-lg border py-3",
                isCancelled && "border-muted-foreground/30 bg-muted/30"
            )}
        >
            <div className="aui-tool-fallback-header flex items-center gap-2 px-4">
                {isCancelled ? (
                    <XCircleIcon className="aui-tool-fallback-icon size-4 text-muted-foreground"/>
                ) : (
                    <CheckIcon className="aui-tool-fallback-icon size-4"/>
                )}
                <p
                    className={cn(
                        "aui-tool-fallback-title grow",
                        isCancelled && "text-muted-foreground line-through"
                    )}
                >
                    {isCancelled ? "Cancelled tool: " : "Used tool: "}
                    <b>{toolName}</b>
                </p>
                <Button onClick={() => setIsCollapsed(!isCollapsed)}>
                    {isCollapsed ? <ChevronUpIcon/> : <ChevronDownIcon/>}
                </Button>
            </div>
            {!isCollapsed && (
                <div className="aui-tool-fallback-content flex flex-col gap-2 border-t pt-2">
                    {cancelledReason && (
                        <div className="aui-tool-fallback-cancelled-root px-4">
                            <p className="aui-tool-fallback-cancelled-header font-semibold text-muted-foreground">
                                Cancelled reason:
                            </p>
                            <p className="aui-tool-fallback-cancelled-reason text-muted-foreground">
                                {cancelledReason}
                            </p>
                        </div>
                    )}
                    <div
                        className={cn(
                            "aui-tool-fallback-args-root px-4",
                            isCancelled && "opacity-60"
                        )}
                    >
                        <pre className="aui-tool-fallback-args-value whitespace-pre-wrap">
                          {argsText}
                        </pre>
                    </div>
                    {!isCancelled && result !== undefined && (
                        <div className="aui-tool-fallback-result-root border-t border-dashed px-4 pt-2">
                            <p className="aui-tool-fallback-result-header font-semibold">
                                Result:
                            </p>
                            <pre className="aui-tool-fallback-result-content whitespace-pre-wrap" style={{
                                height: '200px', // Set a fixed height
                                overflow: 'auto', // Add scrollbars when content exceeds height
                                whiteSpace: 'pre-wrap', // Optional: ensures text wraps within the container
                                border: '1px solid #ccc', // Optional: for visibility
                                padding: '10px',
                                backgroundColor: '#f5f5f5'}}>
                                {typeof result === "string"
                                    ? JSON.stringify(JSON.parse(result.replace(/'/g, '"')), null, 2)
                                    : JSON.stringify(result, null, 2)}
                              </pre>
                        </div>
                    )}
                    {parsedResult.hasUI && serverInfo !== undefined && toolCallInfo !== undefined && (
                        <IFramePanel toolCallInfo={toolCallInfo as Required<ToolCallInfo>}/>
                    )}
                </div>
            )}
        </div>
    );
};