export interface TimeseriesDataPoint {
    date: string | number;

    [key: string]: string | number;
}

export interface MetricConfig {
    key: string;
    label: string;
    color: string;
    format?: (value: any) => string;
}

export type ViewType = 'chart' | 'table';

export interface ZoomArea {
    left: string | null;
    right: string | null;
}

export interface ChartMouseEvent {
    activeLabel?: string;
    activePayload?: Array<{
        payload: TimeseriesDataPoint;
        value: number;
        dataKey: string;
        color: string;
        name: string;
    }>;
}

export interface CustomTooltipProps {
    active?: boolean;
    payload?: Array<{ value: number; name: string; color: string; dataKey: string; }>;
    label?: string;
}

export interface UseChartZoomReturn {
    zoomedData: TimeseriesDataPoint[];
    zoomArea: ZoomArea;
    isSelecting: boolean;
    handleMouseDown: (e: ChartMouseEvent) => void;
    handleMouseMove: (e: ChartMouseEvent) => void;
    handleMouseUp: () => void;
    resetZoom: () => void;
}
