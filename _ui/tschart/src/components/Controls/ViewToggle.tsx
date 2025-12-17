import React from 'react';
import { BarChart3, Table } from 'lucide-react';
import { ViewType } from '../../types';
interface Props { currentView: ViewType; onViewChange: (view: ViewType) => void; }
export const ViewToggle: React.FC<Props> = ({ currentView, onViewChange }) => (
  <div className="flex bg-gray-800 rounded-lg p-1"><button onClick={() => onViewChange('chart')} className={`flex items-center gap-2 px-4 py-2 rounded-md text-sm font-medium transition-all ${currentView === 'chart' ? 'bg-indigo-600 text-white' : 'text-gray-400 hover:text-white'}`}><BarChart3 size={16}/> Chart</button><button onClick={() => onViewChange('table')} className={`flex items-center gap-2 px-4 py-2 rounded-md text-sm font-medium transition-all ${currentView === 'table' ? 'bg-indigo-600 text-white' : 'text-gray-400 hover:text-white'}`}><Table size={16}/> Table</button></div>
);
