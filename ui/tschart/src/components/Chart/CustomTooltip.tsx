import React from 'react';
import { CustomTooltipProps } from '../../types';
export const CustomTooltip: React.FC<CustomTooltipProps> = ({ active, payload, label }) => {
  if (!active || !payload?.length) return null;
  return (<div className="bg-gray-900 border border-gray-700 rounded-lg p-3 shadow-xl animate-fade-in"><p className="text-gray-300 text-sm font-medium mb-2">{label}</p>{payload.map((e, i) => (<p key={i} style={{ color: e.color }} className="text-sm">{e.name}: <span className="font-bold">{e.value.toLocaleString()}</span></p>))}</div>);
};
