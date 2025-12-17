import React from 'react';
import { TrendingUp, X } from 'lucide-react';
import { TimeseriesDataPoint, MetricConfig } from '../../types';
interface Props { selectedPoint: TimeseriesDataPoint; metrics: MetricConfig[]; onClose: () => void; }
export const SelectedPointCard: React.FC<Props> = ({ selectedPoint, metrics, onClose }) => (
  <div className="mb-4 bg-gray-800/50 border border-gray-700 rounded-lg p-4 animate-slide-up"><div className="flex items-center justify-between"><div className="flex items-center gap-3"><TrendingUp className="text-indigo-400" size={20}/><span className="font-medium text-white">Selected: {selectedPoint.date}</span></div><div className="flex gap-6">{metrics.map(m => (<div key={m.key} className="text-center"><p className="text-xs text-gray-400">{m.label}</p><p className="font-bold" style={{ color: m.color }}>{m.format ? m.format(selectedPoint[m.key] as number) : (selectedPoint[m.key] as number).toLocaleString()}</p></div>))}</div><button onClick={onClose} className="text-gray-400 hover:text-white transition-colors"><X size={20}/></button></div></div>
);
