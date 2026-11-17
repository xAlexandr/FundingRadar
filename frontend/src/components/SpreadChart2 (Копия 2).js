import React, { useRef, useEffect, useState } from 'react';

const SpreadChart2 = ({ entrySpread, exitSpread, time }) => {
  const canvasRef = useRef(null);
  const chartDataRef = useRef({
    entrySpreads: [],
    exitSpreads: [],
    times: [],
  });

  const [chartData, setChartData] = useState({
    entrySpreads: [],
    exitSpreads: [],
    times: [],
  });

  const [zoomLevel, setZoomLevel] = useState(144);
  const [offset, setOffset] = useState(0);
  const [initialZoomSet, setInitialZoomSet] = useState(false);
  const isDraggingRef = useRef(false);
  const startXRef = useRef(0);
  const startOffsetRef = useRef(0);

  useEffect(() => {
    if (entrySpread !== 'wait' && entrySpread !== 'Error') {
      chartDataRef.current = {
        entrySpreads: entrySpread,
        exitSpreads: exitSpread,
        times: time,
      };
      setChartData({ ...chartDataRef.current });
      
      if (!initialZoomSet) {
        setZoomLevel(time.length);
        setInitialZoomSet(true);
      } else {
        setZoomLevel((prevZoom) => Math.min(prevZoom, time.length));
      }
      setOffset(0);
    }
  }, [entrySpread, exitSpread, time]);

  useEffect(() => {
    if (!canvasRef.current) return;
    const ctx = canvasRef.current.getContext('2d');
    const width = 400;
    const height = 370;
    canvasRef.current.width = width;
    canvasRef.current.height = height;
    ctx.clearRect(0, 0, width, height);
    ctx.fillStyle = '#243036';
    ctx.fillRect(0, 0, width, height);

    const maxOffset = Math.max(0, chartData.times.length - zoomLevel);
    const adjustedOffset = Math.min(offset, maxOffset);
    setOffset(adjustedOffset);

    const displayedEntrySpreads = chartData.entrySpreads.slice(adjustedOffset, adjustedOffset + zoomLevel);
    const displayedExitSpreads = chartData.exitSpreads.slice(adjustedOffset, adjustedOffset + zoomLevel);
    const displayedTimes = chartData.times.slice(adjustedOffset, adjustedOffset + zoomLevel);

    const allSpreads = [...displayedEntrySpreads, ...displayedExitSpreads];
    const maxSpread = Math.max(...allSpreads);
    const minSpread = Math.min(...allSpreads);
    const padding = (maxSpread - minSpread) * 0.35;
    const lowerLimit = minSpread - padding;
    const upperLimit = maxSpread + padding;
    const graphHeight = height - 30;
    const graphWidth = width - 35;
    const scale = graphHeight / (upperLimit - lowerLimit);
    const step = graphWidth / (zoomLevel - 1);

    const drawLine = (spreads, color) => {
      ctx.beginPath();
      spreads.forEach((spread, i) => {
        const x = (i / (zoomLevel - 1)) * graphWidth;
        const y = graphHeight - (spread - lowerLimit) * scale;
        i === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y);
      });
      ctx.strokeStyle = color;
      ctx.lineWidth = 1.5;
      ctx.stroke();
    };
    

    // Рисуем градиент
    if (displayedEntrySpreads.length > 1) {
      ctx.beginPath();
      ctx.moveTo(0, graphHeight - (displayedExitSpreads[0] - lowerLimit) * scale);
      for (let i = 0; i < zoomLevel; i++) {
        const x = i * step;
        const y = graphHeight - (displayedExitSpreads[i] - lowerLimit) * scale;
        ctx.lineTo(x, y);
      }
      for (let i = zoomLevel - 1; i >= 0; i--) {
        const x = i * step;
        const y = graphHeight - (displayedEntrySpreads[i] - lowerLimit) * scale;
        ctx.lineTo(x, y);
      }
      ctx.closePath();

      const gradient = ctx.createLinearGradient(0, 0, 0, graphHeight);
      gradient.addColorStop(0, 'rgba(255, 107, 107, 0.3)');
      gradient.addColorStop(1, 'rgba(255, 107, 107, 0.0)');
      ctx.fillStyle = gradient;
      ctx.fill();
    }

    drawLine(displayedExitSpreads, '#FF6B6B');
    drawLine(displayedEntrySpreads, '#00C6A2');
  }, [chartData, zoomLevel, offset]);

  const handleWheel = (e) => {
    setZoomLevel((prevZoom) => {
      const newZoom = Math.min(Math.max(prevZoom + (e.deltaY > 0 ? 3 : -3), 2), chartData.times.length);
      setOffset((prevOffset) => Math.max(0, Math.min(prevOffset, chartData.times.length - newZoom)));
      return newZoom;
    });
  };

  const handleTouchStart = (e) => {
    isDraggingRef.current = true;
    startXRef.current = e.touches[0].clientX;
    startOffsetRef.current = offset;
  };

  const handleTouchMove = (e) => {
    if (isDraggingRef.current) {
      const deltaX = e.touches[0].clientX - startXRef.current;
      const step = Math.round(deltaX / 10);
      setOffset((prevOffset) => Math.max(0, Math.min(chartData.times.length - zoomLevel, startOffsetRef.current - step)));
    }
  };

  const handleTouchEnd = () => {
    isDraggingRef.current = false;
  };

  useEffect(() => {
    if (!canvasRef.current) return;
    const canvas = canvasRef.current;
    window.addEventListener('wheel', handleWheel);
    canvas.addEventListener('touchstart', handleTouchStart);
    canvas.addEventListener('touchmove', handleTouchMove);
    canvas.addEventListener('touchend', handleTouchEnd);

    return () => {
      window.removeEventListener('wheel', handleWheel);
      if (canvas) {
        canvas.removeEventListener('touchstart', handleTouchStart);
        canvas.removeEventListener('touchmove', handleTouchMove);
        canvas.removeEventListener('touchend', handleTouchEnd);
      }
    };
  }, [zoomLevel, offset]);

  return <canvas ref={canvasRef} width="400" height="370" />;
};

export default SpreadChart2;
