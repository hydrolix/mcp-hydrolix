import {useCallback, useMemo, useState} from 'react';
import {ChartMouseEvent, TimeseriesDataPoint, UseChartZoomReturn, ZoomArea} from '../types';

export const useChartZoom = (originalData: TimeseriesDataPoint[]): UseChartZoomReturn => {
    const [zoomedData, setZoomedData] = useState<TimeseriesDataPoint[]>(originalData);
    const [zoomArea, setZoomArea] = useState<ZoomArea>({left: null, right: null});
    const [isSelecting, setIsSelecting] = useState(false);
    useMemo(()=>setZoomedData(originalData), [originalData]);
    const handleMouseDown = useCallback((e: ChartMouseEvent) => {
        if (e?.activeLabel) {
            setIsSelecting(true);
            setZoomArea({left: e.activeLabel, right: null});
        }
    }, []);
    const handleMouseMove = useCallback((e: ChartMouseEvent) => {
        if (isSelecting && e?.activeLabel) setZoomArea(p => ({...p, right: e.activeLabel ? e.activeLabel : null}));
    }, [isSelecting]);
    const handleMouseUp = useCallback(() => {
        if (zoomArea.left && zoomArea.right) {
            const l = originalData.findIndex(d => d.date === zoomArea.left);
            const r = originalData.findIndex(d => d.date === zoomArea.right);
            const [s, e] = l < r ? [l, r] : [r, l];
            if (e - s > 1) setZoomedData(originalData.slice(s, e + 1));
        }
        setIsSelecting(false);
        setZoomArea({left: null, right: null});
    }, [zoomArea, originalData]);
    const resetZoom = useCallback(() => setZoomedData(originalData), [originalData]);
    return {zoomedData, zoomArea, isSelecting, handleMouseDown, handleMouseMove, handleMouseUp, resetZoom};
};
