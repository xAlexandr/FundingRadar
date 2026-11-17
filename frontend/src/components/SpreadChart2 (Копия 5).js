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
  const startDistanceRef = useRef(0);
  const startZoomRef = useRef(zoomLevel);
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


  const drawGrid = (ctx, graphWidth, graphHeight, lowerLimit, upperLimit) => {
    ctx.strokeStyle = 'rgba(255, 255, 255, 0.15)'; // Цвет сетки
    ctx.lineWidth = 1;
    ctx.setLineDash([4, 4]); // Пунктирные линии

    // Определяем шаг сетки
    const range = upperLimit - lowerLimit;
    const minSpreadCondition = Math.abs(lowerLimit) < 1 && Math.abs(upperLimit) < 1;
    const maxSteps = 10;
    
    let step = range / maxSteps;
    step = Math.ceil(step / 0.2) * 0.2; // Округляем шаг, чтобы был кратен 0.2
    if (minSpreadCondition) step = 0.2; // Фиксированный шаг для маленьких значений

    // Корректируем начальную точку, чтобы сетка начиналась с кратного 0.2
    let start = Math.floor(lowerLimit / 0.2) * 0.2;

    // Рисуем горизонтальные линии сетки и подписи
    ctx.font = '11px Arial';
    ctx.fillStyle = 'rgba(255, 255, 255, 0.8)';
    ctx.textAlign = 'left';

    while (start <= upperLimit) {
        let y = graphHeight - (start - lowerLimit) * (graphHeight / range);

        ctx.beginPath();
        ctx.moveTo(0, y);
        ctx.lineTo(graphWidth, y);
        ctx.stroke();

        // Подписи справа
        ctx.fillText(start.toFixed(1), graphWidth + 10, y + 4);

        // Переход к следующему значению, кратному 0.2
        start = Math.round((start + step) / 0.2) * 0.2;
    }

    ctx.setLineDash([]); // Убираем пунктир после сетки

    // Рисуем вертикальные разделители
const sections = 3; // Количество секций
const sectionWidth = graphWidth / sections;

ctx.strokeStyle = 'rgba(255, 255, 255, 0.15)';
ctx.lineWidth = 1;
ctx.setLineDash([4, 4]);

for (let i = 1; i < sections; i++) {
    const x = i * sectionWidth;
    ctx.beginPath();
    ctx.moveTo(x, 0);
    ctx.lineTo(x, graphHeight);
    ctx.stroke();
}

ctx.setLineDash([]); // Убираем пунктир после разделителей


};

  

  useEffect(() => {
    if (!canvasRef.current) return;
    const ctx = canvasRef.current.getContext('2d');
    const dpr = Math.max(window.devicePixelRatio || 1, 3);
    const width = 400;
    const height = 370;
    canvasRef.current.width = width * dpr;
    canvasRef.current.height = height * dpr;
    ctx.scale(dpr, dpr);
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

    drawGrid(ctx, graphWidth, graphHeight, lowerLimit, upperLimit);


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


    // Улучшенные подписи оси X
if (displayedTimes.length > 1) {
  ctx.fillStyle = 'rgba(255, 255, 255, 0.8)';
  ctx.font = '12px Arial';
  ctx.textAlign = 'center';
  ctx.textBaseline = 'top';

  // Динамический шаг для подписей
  const minLabels = 6; // Минимальное количество подписей
  const maxLabels = 14; // Максимальное количество подписей
  const labelStep = Math.max(1, Math.floor(displayedTimes.length / maxLabels));

  for (let i = 0; i < displayedTimes.length; i += labelStep) {
      const x = i * step;
      ctx.fillText(displayedTimes[i], x, graphHeight + 18);
  }
}



  }, [chartData, zoomLevel, offset]);

  const handleWheel = (e) => {
    e.preventDefault(); // Останавливаем скролл страницы

    setZoomLevel((prevZoom) => {
      const newZoom = Math.min(Math.max(prevZoom + (e.deltaY > 0 ? 3 : -3), 2), chartData.times.length);
      setOffset((prevOffset) => Math.max(0, Math.min(prevOffset, chartData.times.length - newZoom)));
      return newZoom;
    });
  };

  const handleTouchStart = (e) => {
    if (e.touches.length === 1) {
      // Перемещение (скролл)
      isDraggingRef.current = true;
      startXRef.current = e.touches[0].clientX;
      startOffsetRef.current = offset;
    } else if (e.touches.length === 2) {
      // Начало пинч-зума
      const dx = e.touches[0].clientX - e.touches[1].clientX;
      const dy = e.touches[0].clientY - e.touches[1].clientY;
      startDistanceRef.current = Math.sqrt(dx * dx + dy * dy);
      startZoomRef.current = zoomLevel;
    }
  };
  
  const handleTouchMove = (e) => {
    if (e.touches.length === 1 && isDraggingRef.current) {
      // Горизонтальный скролл
      const deltaX = e.touches[0].clientX - startXRef.current;
      const step = Math.round(deltaX / 10);
      setOffset((prevOffset) =>
        Math.max(0, Math.min(chartData.times.length - zoomLevel, startOffsetRef.current - step))
      );
    } else if (e.touches.length === 2) {
      // Пинч-зум
      const dx = e.touches[0].clientX - e.touches[1].clientX;
      const dy = e.touches[0].clientY - e.touches[1].clientY;
      const newDistance = Math.sqrt(dx * dx + dy * dy);
      const scaleFactor = newDistance / startDistanceRef.current;
  
      setZoomLevel((prevZoom) => {
        let newZoom = Math.round(startZoomRef.current / scaleFactor);
        return Math.max(2, Math.min(newZoom, chartData.times.length));
      });
    }
  };
  

  const handleTouchEnd = () => {
    isDraggingRef.current = false;
  };

  useEffect(() => {
    if (!canvasRef.current) return;
    const canvas = canvasRef.current;
    canvas.addEventListener('wheel', handleWheel, { passive: false });
    canvas.addEventListener('touchstart', handleTouchStart, { passive: false });
    canvas.addEventListener('touchmove', handleTouchMove, { passive: false });
    canvas.addEventListener('touchend', handleTouchEnd);

    return () => {
      if (canvas) {
        canvas.removeEventListener('wheel', handleWheel);
        canvas.removeEventListener('touchstart', handleTouchStart);
        canvas.removeEventListener('touchmove', handleTouchMove);
        canvas.removeEventListener('touchend', handleTouchEnd);
      }
    };
  }, [zoomLevel, offset]);

  return <canvas ref={canvasRef} width="400" height="370" />;
};

export default SpreadChart2;
