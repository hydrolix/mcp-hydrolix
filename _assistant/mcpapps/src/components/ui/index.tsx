import * as React from "react";
import {cn} from "@/lib/utils.ts";
import {CheckCircle2, Wrench} from "lucide-react";
import type {CallToolResult} from "@modelcontextprotocol/sdk/types.js";

// // ============================================================================
// // Utility function for className merging
// // ============================================================================
//
// export function cn(...inputs: any[]) {
//     return inputs.filter(Boolean).join(' ');
// }

// ============================================================================
// Simple Card Component (for error displays)
// ============================================================================

export const Card = React.forwardRef<
    HTMLDivElement,
    React.HTMLAttributes<HTMLDivElement>
>(({className, ...props}, ref) => (
    <div
        ref={ref}
        className={cn(
            "rounded-lg border bg-card text-card-foreground shadow-sm",
            className
        )}
        {...props}
    />
));
Card.displayName = "Card";

// ============================================================================
// Simple Button Component (for error retry)
// ============================================================================

interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
    variant?: 'default' | 'outline';
}

export const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
    ({className, variant = 'default', ...props}, ref) => {
        const variantStyles = {
            default: "bg-primary text-primary-foreground hover:bg-primary/90",
            outline: "border border-input bg-background hover:bg-accent",
        };

        return (
            <button
                className={cn(
                    "inline-flex items-center justify-center rounded-md px-4 py-2 text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 disabled:pointer-events-none disabled:opacity-50",
                    variantStyles[variant],
                    className
                )}
                ref={ref}
                {...props}
            />
        );
    }
);
Button.displayName = "Button";

// Tool call badge component
export function ToolCallBadge({toolName, args}: { toolName: string; args: any }) {
    return (
        <div
            className="inline-flex items-center gap-2 px-3 py-1.5 bg-gradient-to-r from-purple-500 to-blue-500 text-white rounded-lg text-sm font-medium shadow-sm my-2">
            <Wrench className="w-3.5 h-3.5"/>
            <span>Calling: {toolName}</span>
            {args && Object.keys(args).length > 0 && (
                <span className="text-xs opacity-90">
          ({Object.keys(args).length} arg{Object.keys(args).length !== 1 ? 's' : ''})
        </span>
            )}
        </div>
    );
}

export function ToolResultPanel({result}: CallToolResult) {
    return (
        <div
            className="my-3 rounded-xl border border-gray-200 bg-gradient-to-br from-gray-50 to-gray-100 overflow-hidden">
            <div className="px-4 py-2 bg-gray-800 text-gray-100 font-mono text-xs flex items-center gap-2">
                <CheckCircle2 className="w-3.5 h-3.5 text-green-400"/>
                Tool Result
            </div>
            <pre className="text-xs p-4 overflow-auto max-h-96 bg-white/50">
        <code className="text-gray-800">{JSON.stringify(result, null, 2)}</code>
      </pre>
        </div>
    );
}
