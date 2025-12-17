import {useEffect, useRef, useState} from "react";
import {IMPLEMENTATION, SANDBOX_PROXY_URL, ServerInfo, ToolCallInfo} from "@/extapps.ts";
import {
    AppBridge,
    McpUiSandboxProxyReadyNotification,
    PostMessageTransport
} from "@modelcontextprotocol/ext-apps/app-bridge";
import {Button} from "@/components/ui/index.tsx";

// ============================================================================
// AppBridge Setup
// ============================================================================

function loadSandboxProxy(iframe: HTMLIFrameElement): Promise<boolean> {
    if (iframe.src) {
        if (iframe.getAttribute("mcp_apps_inited") === "true") {
            return Promise.resolve(false);
        }
        // return Promise.resolve(true);
    }

    iframe.setAttribute("sandbox", "allow-scripts allow-same-origin allow-forms");
    iframe.setAttribute("mcp_apps_inited", "false");

    const readyNotification: McpUiSandboxProxyReadyNotification["method"] =
        "ui/notifications/sandbox-proxy-ready";

    const readyPromise = new Promise<boolean>((resolve) => {
        const listener = ({source, data}: MessageEvent) => {
            if (source === iframe.contentWindow && data?.method === readyNotification) {
                iframe.setAttribute("mcp_apps_inited", "true");
                window.removeEventListener("message", listener);
                resolve(true);
            }
        };
        window.addEventListener("message", listener);
    });

    iframe.src = SANDBOX_PROXY_URL.href;
    return readyPromise;
}

async function initializeApp(
    iframe: HTMLIFrameElement,
    appBridge: AppBridge,
    {input, resultPromise, appResourcePromise}: Required<ToolCallInfo>,
): Promise<void> {
    const appInitializedPromise = new Promise<void>((resolve) => {
        const oninitialized = appBridge.oninitialized;
        appBridge.oninitialized = (...args) => {
            resolve();
            appBridge.oninitialized = oninitialized;
            appBridge.oninitialized?.(...args);
        };
    });

    await appBridge.connect(
        new PostMessageTransport(iframe.contentWindow!, iframe.contentWindow!),
    );

    const {html, csp} = await appResourcePromise;
    await appBridge.sendSandboxResourceReady({html, csp});
    await appInitializedPromise;

    appBridge.sendToolInput({arguments: input});
    resultPromise.then((result) => {
        appBridge.sendToolResult(result);
    });
}

function newAppBridge(serverInfo: ServerInfo, iframe: HTMLIFrameElement): AppBridge {
    const serverCapabilities = serverInfo.client.getServerCapabilities();
    const appBridge = new AppBridge(serverInfo.client, IMPLEMENTATION, {
        openLinks: {},
        serverTools: serverCapabilities?.tools,
        serverResources: serverCapabilities?.resources,
    });

    appBridge.onmessage = async (params) => ({});
    appBridge.onopenlink = async (params) => {
        window.open(params.url, "_blank", "noopener,noreferrer");
        return {};
    };
    appBridge.onloggingmessage = (params) => console.log('[MCP App]', params);

    appBridge.onsizechange = async ({width, height}) => {
        const style = getComputedStyle(iframe);
        const isBorderBox = style.boxSizing === "border-box";

        if (width !== undefined) {
            if (isBorderBox) {
                width += parseFloat(style.borderLeftWidth) + parseFloat(style.borderRightWidth);
            }
            iframe.style.minWidth = `min(${width}px, 100%)`;
        }
        if (height !== undefined) {
            if (isBorderBox) {
                height += parseFloat(style.borderTopWidth) + parseFloat(style.borderBottomWidth);
            }
            iframe.style.height = `${height}px`;
        }
    };

    return appBridge;
}


// ============================================================================
// Tool Result Rendering Components
// ============================================================================

export function AppIFramePanel({toolCallInfo}: { toolCallInfo: Required<ToolCallInfo> }) {
    const iframeRef = useRef<HTMLIFrameElement | null>(null);
    const [isExpanded, setIsExpanded] = useState(false);

    useEffect(() => {
        const iframe = iframeRef.current!;
        loadSandboxProxy(iframe).then((firstTime) => {
            if (firstTime) {
                const appBridge = newAppBridge(toolCallInfo.serverInfo, iframe);
                initializeApp(iframe, appBridge, toolCallInfo);
            }
        });
    }, [toolCallInfo]);

    return (
        <div
            style={isExpanded ? {
                position: 'fixed',
                top: 0, left: 0, right: 0, bottom: 0,
                zIndex: 9999,
                background: 'white'
            } : {height: '600px'}}
            className="w-full rounded-xl overflow-hidden bg-white border border-gray-200 shadow-sm my-3"
        >
            <Button onClick={() => setIsExpanded(!isExpanded)}>
                {isExpanded ? 'Exit' : 'Expand'}
            </Button>
            <iframe
                ref={iframeRef}
                className="w-full h-full border-0"
                title="MCP App UI"
            />
        </div>
    );
}
