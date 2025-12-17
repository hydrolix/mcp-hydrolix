import React from 'react';
import {RotateCcw} from 'lucide-react';
import {MetricConfig} from '../../types';

interface Props {
    metrics: MetricConfig[];
    selectedMetrics: string[];
    onToggleMetric: (key: string) => void;
    onResetZoom: () => void;
}

export const MetricSelector: React.FC<Props> = ({metrics, selectedMetrics, onToggleMetric, onResetZoom}) => (
    <>
        <div className="flex gap-2">
            {metrics.map(m => (<button key={m.key} onClick={() => onToggleMetric(m.key)}
                                       className={`px-3 py-2 rounded-lg text-sm font-medium transition-all border ${selectedMetrics.includes(m.key) ? 'border-transparent text-white' : 'border-gray-600 text-gray-400 hover:border-gray-500'}`}
                                       style={{backgroundColor: selectedMetrics.includes(m.key) ? m.color : 'transparent'}}>{m.label}</button>))}</div>
        <button onClick={onResetZoom}
                className="flex items-center gap-2 px-3 py-2 bg-gray-700 hover:bg-gray-600 rounded-lg text-sm transition-all text-white">
            <RotateCcw size={16}/> Reset Zoom
        </button>
    </>
);
