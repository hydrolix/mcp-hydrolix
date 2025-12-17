import React from 'react';
import {
    Area,
    AreaChart,
    Brush,
    CartesianGrid,
    Legend,
    ReferenceArea,
    ResponsiveContainer,
    Tooltip,
    XAxis,
    YAxis
} from 'recharts';
import {CustomTooltip} from './CustomTooltip';
import {ChartMouseEvent, MetricConfig, TimeseriesDataPoint, ZoomArea} from '../../types';
import {CHART_COLORS} from '../../constants/metrics';

interface Props {
    data: TimeseriesDataPoint[];
    metrics: MetricConfig[];
    selectedMetrics: string[];
    zoomArea: ZoomArea;
    isSelecting: boolean;
    onChartClick: (e: ChartMouseEvent) => void;
    onMouseDown: (e: ChartMouseEvent) => void;
    onMouseMove: (e: ChartMouseEvent) => void;
    onMouseUp: () => void;
}

export const TimeseriesChart: React.FC<Props> = ({
                                                     data,
                                                     metrics,
                                                     selectedMetrics,
                                                     zoomArea,
                                                     isSelecting,
                                                     onChartClick,
                                                     onMouseDown,
                                                     onMouseMove,
                                                     onMouseUp
                                                 }) => {
    const active = metrics.filter(m => selectedMetrics.includes(m.key));
    return (<div className="bg-gray-800/50 border border-gray-700 rounded-xl p-4 animate-fade-in">
        <ResponsiveContainer
            width="100%" height={400}>
            <AreaChart data={data} onClick={onChartClick} onMouseDown={onMouseDown}
                       onMouseMove={onMouseMove} onMouseUp={onMouseUp} onMouseLeave={onMouseUp}>
                <defs>{metrics.map(m => (
                    <linearGradient key={m.key} id={`gradient-${m.key}`} x1="0" y1="0" x2="0" y2="1">
                        <stop offset="5%" stopColor={m.color} stopOpacity={0.3}/>
                        <stop offset="95%" stopColor={m.color} stopOpacity={0}/>
                    </linearGradient>))}</defs>
                <CartesianGrid strokeDasharray="3 3" stroke={CHART_COLORS.grid}/>
                <XAxis dataKey="date" type="number" scale="time"
                       stroke={CHART_COLORS.axis}
                       tick={{
                           fill: CHART_COLORS.axis,
                           fontSize: 12
                       }}
                       domain={['auto', 'auto']}
                       tickFormatter={(t) => new Date(t).toISOString()}/>
                <YAxis stroke={CHART_COLORS.axis}
                       tick={{fill: CHART_COLORS.axis, fontSize: 12}}
                       domain={['auto', 'auto']}
                />
                <Tooltip
                    content={<CustomTooltip/>}/>
                <Legend wrapperStyle={{paddingTop: 20}}/>{active.map(m => (
                <Area key={m.key} type="monotone" dataKey={m.key} name={m.label} stroke={m.color} strokeWidth={2}
                      fill={`url(#gradient-${m.key})`} dot={{fill: m.color, strokeWidth: 2, r: 4}}
                      activeDot={{r: 6, strokeWidth: 0}}/>))}
                {isSelecting && zoomArea.left && zoomArea.right && (
                    <ReferenceArea x1={zoomArea.left} x2={zoomArea.right} strokeOpacity={0.3}
                                   fill={CHART_COLORS.zoomOverlay}
                                   fillOpacity={0.3}/>)}
                <Brush dataKey="date" height={30} stroke={CHART_COLORS.brush}
                       fill={CHART_COLORS.brushFill}
                       tickFormatter={(t) => new Date(t).toISOString()}/>
            </AreaChart>
        </ResponsiveContainer>
        <p className="text-center text-gray-500 text-xs mt-2">💡 Drag to zoom • Use brush to navigate • Click for
            details</p></div>);
};
