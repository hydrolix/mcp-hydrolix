import React, {useEffect, useState} from 'react';
import {TimeseriesChart} from './components/Chart/TimeseriesChart';
import {DataTable} from './components/Table/DataTable';
import {ViewToggle} from './components/Controls/ViewToggle';
import {MetricSelector} from './components/Controls/MetricSelector';
import {SelectedPointCard} from './components/SelectedPoint/SelectedPointCard';
import {useChartZoom} from './hooks/useChartZoom';
import {ChartMouseEvent, TimeseriesDataPoint, ViewType} from './types';
import {useApp} from "@modelcontextprotocol/ext-apps/react";
import {CallToolResult} from "@modelcontextprotocol/sdk/types.js";
import type {App} from "@modelcontextprotocol/ext-apps";
import {MetricConfig} from '@/types';

const IMPLEMENTATION = {name: "Time Series Viewer", version: "1.0.0"};
const log = {
    info: console.log.bind(console, "[APP]"),
    warn: console.warn.bind(console, "[APP]"),
    error: console.error.bind(console, "[APP]"),
};

const colors: string[] = []
for (let i = 0; i < 100; i++) {
    const randomColor = Math.floor(Math.random() * 16777215).toString(16);
    const paddedColor = randomColor.padStart(6, '0');
    colors[i]=`#${paddedColor}`
}

const McpApp: React.FC = () => {
    const [toolResult, setToolResult] = useState<CallToolResult | null>(null);
    const {app, error} = useApp({
        appInfo: IMPLEMENTATION,
        capabilities: {},
        onAppCreated: (app) => {
            app.ontoolinput = async (input) => {
                log.info("Received tool call input:", input);
            };

            app.ontoolresult = async (result) => {
                log.info("Received tool call result:", result);
                setToolResult(result);
            };

            app.onerror = log.error;
        },
    });

    if (error) return <div><strong>ERROR:</strong> {error.message}</div>;
    if (!app) return <div>Connecting...</div>;

    return <AppInner app={app} toolResult={toolResult}/>;
}

interface AppInnerProps {
    app: App;
    toolResult: CallToolResult | null;
}

const AppInner: React.FC = ({app, toolResult}: AppInnerProps) => {
    const [tsData, setTsData] = useState<TimeseriesDataPoint[]>([]);
    const [tsCols, setTsCols] = useState<string[]>([]);
    useEffect(() => {
        if (toolResult && Array.isArray(toolResult.structuredContent?.rows)) {
            const cols: string[] = toolResult.structuredContent.columns as string[];
            const ts = toolResult.structuredContent.rows.map((r) => {
                const res: TimeseriesDataPoint = {date: r[0]}
                for (let i = 1; i < r.length; i++) {
                    res[cols[i]] = r[i]
                }
                return res;
            })
            setTsCols(cols);
            setTsData(ts);
        }
    }, [toolResult]);

    const METRICS: MetricConfig[] = tsCols
        .filter((v, i) => i > 0)
        .map((col, i) => {

            return {
                key: col, label: col, color: colors[i],
                format: (v: any) => {
                    const str = v == undefined || typeof (v) == 'string' ? '' : v.toLocaleString()
                    return str
                }
            }
        })
    const DEFAULT_SELECTED_METRICS = [tsCols[1]];

    const [view, setView] = useState<ViewType>('chart');
    const [selectedMetrics, setSelectedMetrics] = useState<string[]>(DEFAULT_SELECTED_METRICS);
    const [selectedPoint, setSelectedPoint] = useState<TimeseriesDataPoint | null>(null);
    const toggleMetric = (key: string) => setSelectedMetrics(p => p.includes(key) ? p.filter(m => m !== key) : [...p, key]);
    const handleChartClick = (e: ChartMouseEvent) => {
        if (e?.activePayload?.[0]) setSelectedPoint(e.activePayload[0].payload);
    };
    const {
        zoomedData,
        zoomArea,
        isSelecting,
        handleMouseDown,
        handleMouseMove,
        handleMouseUp,
        resetZoom
    } = useChartZoom(tsData)

    return (
        <div className="min-h-screen bg-gradient-to-br from-gray-900 via-gray-800 to-gray-900 p-4 text-white">
            <div className="max-w-6xl mx-auto">
                <div className="mb-6"><h1
                    className="text-2xl font-bold bg-gradient-to-r from-indigo-400 to-purple-400 bg-clip-text text-transparent">Timeseries
                    SQL Results Viewer</h1><p className="text-gray-400 text-sm mt-1">Click and drag on chart to zoom •
                    Click data points for details</p></div>
                <div className="flex flex-wrap gap-3 mb-4">
                    <ViewToggle currentView={view} onViewChange={setView}/>
                    {view === 'chart' &&
                        <MetricSelector metrics={METRICS} selectedMetrics={selectedMetrics}
                                        onToggleMetric={toggleMetric}
                                        onResetZoom={resetZoom}/>}
                </div>
                {selectedPoint &&
                    <SelectedPointCard selectedPoint={selectedPoint} metrics={METRICS}
                                       onClose={() => setSelectedPoint(null)}/>}

                {view === 'chart' &&
                    <TimeseriesChart data={zoomedData} metrics={METRICS} selectedMetrics={selectedMetrics}
                                     zoomArea={zoomArea} isSelecting={isSelecting} onChartClick={handleChartClick}
                                     onMouseDown={handleMouseDown} onMouseMove={handleMouseMove}
                                     onMouseUp={handleMouseUp}/>}
                {view === 'table' &&
                    <DataTable data={zoomedData} metrics={METRICS} selectedPoint={selectedPoint}
                               onRowClick={setSelectedPoint}/>}
            </div>
        </div>
    );
};
export default McpApp;
