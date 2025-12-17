import React from 'react';
import {MetricConfig, TimeseriesDataPoint} from '../../types';

interface Props {
    data: TimeseriesDataPoint[];
    metrics: MetricConfig[];
    selectedPoint: TimeseriesDataPoint | null;
    onRowClick: (row: TimeseriesDataPoint) => void;
}

export const DataTable: React.FC<Props> = ({data, metrics, selectedPoint, onRowClick}) => (
    <div className="bg-gray-800/50 border border-gray-700 rounded-xl overflow-hidden animate-fade-in">
        <div className="overflow-x-auto">
            <table className="w-full">
                <thead>
                <tr className="bg-gray-900/50">
                    <th className="px-6 py-4 text-left text-xs font-semibold text-gray-400 uppercase tracking-wider">Date</th>
                    {metrics.map(m => (
                        <th key={m.key} className="px-6 py-4 text-right text-xs font-semibold uppercase tracking-wider"
                            style={{color: m.color}}>{m.label}</th>))}</tr>
                </thead>
                <tbody className="divide-y divide-gray-700">{data.map((row, i) => (
                    <tr key={i} onClick={() => onRowClick(row)}
                        className={`hover:bg-gray-700/50 transition-colors cursor-pointer ${selectedPoint?.date === row.date ? 'bg-indigo-900/30' : ''}`}>
                        <td className="px-6 py-4 text-sm font-medium text-white">{row.date}</td>
                        {metrics.map(m => (<td key={m.key}
                                               className="px-6 py-4 text-sm text-right tabular-nums text-gray-300">{row[m.key]}{m.format ? m.format(row[m.key]) : (row[m.key] as number).toLocaleString()}</td>))}
                    </tr>))}</tbody>
            </table>
        </div>
    </div>
);
