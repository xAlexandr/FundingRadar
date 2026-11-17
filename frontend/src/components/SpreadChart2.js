import React, { useRef, useEffect, useState } from 'react';

const SpreadChart2 = ({ entrySpread, exitSpread, time, useZoom }) => {
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
  const [useZoomGraph, setUseZoomGraph] = useState(useZoom);
  const [offset, setOffset] = useState(0);
  const [initialZoomSet, setInitialZoomSet] = useState(false);
  const isDraggingRef = useRef(false);
  const startDistanceRef = useRef(0);
  const startZoomRef = useRef(zoomLevel);
  const startXRef = useRef(0);
  const startOffsetRef = useRef(0);

  useEffect(() => {
    setUseZoomGraph(useZoom);
  }, [useZoom]);

  useEffect(() => {
    if (entrySpread !== 'wait' && entrySpread !== 'Error') {
      chartDataRef.current = {
        entrySpreads: entrySpread,
        exitSpreads: exitSpread,
        times: time,
      };
      setChartData({ ...chartDataRef.current });
      
      if (!initialZoomSet) {
        setZoomLevel(Math.min(time.length, 575)); // Ограничиваем зум на 144
        setInitialZoomSet(true);
      } else {
        setZoomLevel((prevZoom) => Math.min(prevZoom, time.length));
      }
      setOffset(Math.max(0, time.length - Math.min(time.length, 575)));
    } else {
      // Очищаем график
          chartDataRef.current = {
            entrySpreads: [],
            exitSpreads: [],
            times: [],
          };
          setChartData({ ...chartDataRef.current });
          setInitialZoomSet(false); // Сбрасываем флаг инициализации зума
          setZoomLevel(575);
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
        let y = graphHeight - (start - lowerLimit) * ((graphHeight - 10) / range);

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
    if (adjustedOffset !== offset) {
      setOffset(adjustedOffset);
    }

    const displayedEntrySpreads = chartData.entrySpreads.slice(adjustedOffset, adjustedOffset + zoomLevel);
    const displayedExitSpreads = chartData.exitSpreads.slice(adjustedOffset, adjustedOffset + zoomLevel);
    const displayedTimes = chartData.times.slice(adjustedOffset, adjustedOffset + zoomLevel);

    const allSpreads = [...displayedEntrySpreads, ...displayedExitSpreads];
    // Улучшенный расчет min и max с небольшим увеличением границ
    let maxSpread = Math.max(...allSpreads) * (Math.max(...allSpreads) > 0 ? 1.2 : 0.8);
    let minSpread = Math.min(...allSpreads) * (Math.min(...allSpreads) < 0 ? 1.2 : 0.8);

    // Если разница слишком мала (чтобы избежать плоской линии)
    if (maxSpread - minSpread < 0.1) {
      maxSpread += 0.05;
      minSpread -= 0.05;
    }
    const padding = (maxSpread - minSpread) * 0.35;
    const lowerLimit = minSpread - padding;
    const upperLimit = maxSpread + padding;
    const graphHeight = height - 40;
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
  ctx.font = '11px Arial';
  ctx.textAlign = 'center';
  ctx.textBaseline = 'top';

// ============ Плотные подписи (минимальные правки) ============
const paddingPx = 2;                 // уменьшили расстояние между метками
const showMinutes = step >= 30;      // порог как у тебя
// используем ширину одной цифры + небольшой запас, а не '22' — плотнее
const hourMaxWidth = ctx.measureText('2').width + 2;
let lastPlacedRight = -Infinity;

// подстроим maxLabels при сильном зуме, чтобы писать чаще
let maxLabels = 20;
if (step >= 30) maxLabels = 8;
const labelStep = Math.max(1, Math.floor(displayedTimes.length / maxLabels));

for (let i = 0; i < displayedTimes.length; i += labelStep) {
  const raw = displayedTimes[i] || '';

  // Формат метки
  let label = '';
  if (raw.includes(':')) {
    const [h, m] = raw.split(':');
    const hoursNum = Number.parseInt(h, 10);
    const minutes = (m || '00').padStart(2, '0');
    label = showMinutes ? `${hoursNum}:${minutes}` : `${hoursNum}`;
  } else {
    const hoursNum = Number.parseInt(raw || '0', 10);
    label = showMinutes ? `${hoursNum}:00` : `${hoursNum}`;
  }

  const x = i * step;
  const actualWidth = ctx.measureText(label).width;
  const usedWidth = showMinutes ? actualWidth : hourMaxWidth;

  let center = x;
  let left = center - usedWidth / 2;
  let right = center + usedWidth / 2;

  // Если полностью в графике и не перекрываем предыдущую метку — рисуем
  if (left >= 0 && right <= graphWidth && left >= lastPlacedRight + paddingPx) {
    ctx.textAlign = 'center';
    ctx.fillText(label, Math.round(center), graphHeight + 28);
    lastPlacedRight = right;
    continue;
  }

  // Если не помещается и мы в режиме только часов — пропускаем
  if (!showMinutes) {
    continue;
  }

  // В режиме минут — пробуем аккуратно сдвинуть внутрь, чтобы влезло
  const minCenter = Math.max(usedWidth / 2, lastPlacedRight + paddingPx + usedWidth / 2);
  let drawCenter = Math.max(minCenter, Math.min(center, graphWidth - usedWidth / 2));

  if (drawCenter - usedWidth / 2 < 0 || drawCenter + usedWidth / 2 > graphWidth) {
    continue;
  }

  if (drawCenter - usedWidth / 2 < lastPlacedRight + paddingPx) {
    drawCenter = lastPlacedRight + paddingPx + usedWidth / 2;
    if (drawCenter + usedWidth / 2 > graphWidth) continue;
  }

  ctx.textAlign = 'center';
  ctx.fillText(label, Math.round(drawCenter), graphHeight + 28);
  lastPlacedRight = drawCenter + usedWidth / 2;
}
}



  }, [chartData, zoomLevel, offset]);

  const handleWheel = (e) => {
  e.preventDefault(); // Останавливаем скролл страницы
  if (!chartData.times || chartData.times.length === 0) return;

  setZoomLevel((prevZoom) => {
    const zoomOut = e.deltaY > 0; // колесо вниз = отдаляемся (увеличиваем число точек)
    // скорость зависит от текущего prevZoom: берём процент от текущего
    // 0.03 = 3% от текущего zoom; можно подогнать (0.02 медленнее, 0.05 быстрее)
    // Шаг зависит от текущего zoom
    const proportionalStep = Math.max(1, Math.round(prevZoom * 0.2));
    const stepCandidate = Math.max(50, Math.round(chartData.times.length * 0.1));

    // Сохраняем округления, как было, но ограничиваем сверху 250
    const step = Math.min(proportionalStep, stepCandidate, 1000);

    const deltaZoom = zoomOut ? step : -step;
    const newZoom = Math.min(Math.max(prevZoom + deltaZoom, 2), chartData.times.length);

    // сохраняем центр/правый край похожим образом как раньше
    setOffset((prevOffset) => {
      const maxOffset = Math.max(0, chartData.times.length - newZoom);

      if (zoomOut) {
        // Зум наружу — фиксируем центр (как раньше)
        const center = prevOffset + prevZoom / 2;
        let newOffset = Math.round(center - newZoom / 2);

        if (newOffset < 0) newOffset = 0;
        if (newOffset > maxOffset) newOffset = maxOffset;
        return newOffset;
      } else {
        // Зум внутрь — если были у правого края — держим его, иначе центрируем
        if (prevOffset + prevZoom >= chartData.times.length - 1) {
          return maxOffset;
        } else {
          const center = prevOffset + prevZoom / 2;
          let newOffset = Math.round(center - newZoom / 2);

          if (newOffset < 0) newOffset = 0;
          if (newOffset > maxOffset) newOffset = maxOffset;
          return newOffset;
        }
      }
    });

    return newZoom;
  });
};

  const handlePointerDown = (e) => {
  if (e.pointerType !== 'mouse') return; // Только мышь
  isDraggingRef.current = true;
  startXRef.current = e.clientX;
  startOffsetRef.current = offset;
};

const handlePointerMove = (e) => {
  if (!isDraggingRef.current || e.pointerType !== 'mouse') return;

  const deltaX = e.clientX - startXRef.current;

  let speedFactor;
  if (zoomLevel < 50) speedFactor = 1;
  else if (zoomLevel < 100) speedFactor = 3;
  else if (zoomLevel < 300) speedFactor = 7;
  else if (zoomLevel < 600) speedFactor = 10;
  else if (zoomLevel < 800) speedFactor = 12;
  else if (zoomLevel < 1500) speedFactor = 25;
  else if (zoomLevel < 2000) speedFactor = 60;
  else if (zoomLevel < 2900) speedFactor = 80;

  const step = Math.round(deltaX / (10 / speedFactor));

  setOffset((prevOffset) =>
    Math.max(0, Math.min(chartData.times.length - zoomLevel, startOffsetRef.current - step))
  );
};

const handlePointerUp = (e) => {
  if (e.pointerType !== 'mouse') return;
  isDraggingRef.current = false;
};


  const handleTouchStart = (e) => {
    if (e.touches.length === 1) {
      // Перемещение (скролл)
      isDraggingRef.current = true;
      startXRef.current = e.touches[0].clientX;
      startOffsetRef.current = offset;
    } else if (e.touches.length === 2) {
      e.preventDefault();
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

      let speedFactor;

      if (zoomLevel < 50){
        speedFactor = 1;
      } else if (zoomLevel < 100) {
        speedFactor = 2;
      } else if (zoomLevel < 300) {
        speedFactor = 7 
      } else if (zoomLevel < 600) {
        speedFactor = 10
      } else if (zoomLevel < 800) {
        speedFactor = 12
      } else if (zoomLevel < 1500) {
        speedFactor = 25
      } else if (zoomLevel < 2000) {
        speedFactor = 50
      } else if (zoomLevel < 2900) {
        speedFactor = 70
      }

     // const speedFactor = zoomLevel < 50 ? 1 : zoomLevel < 100 ? 2 : 4; // Ускоряем при большем зуме
      const step = Math.round(deltaX / (10 / speedFactor)); // Чем больше zoomLevel, тем быстрее прокрутка

      setOffset((prevOffset) =>
        Math.max(0, Math.min(chartData.times.length - zoomLevel, startOffsetRef.current - step))
      );
    } else if (e.touches.length === 2) {
      e.preventDefault();
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
    if (!useZoomGraph) {
      if (canvas) {
        canvas.removeEventListener('wheel', handleWheel);
        canvas.removeEventListener('touchstart', handleTouchStart);
        canvas.removeEventListener('touchmove', handleTouchMove);
        canvas.removeEventListener('touchend', handleTouchEnd);

        canvas.removeEventListener('pointerdown', handlePointerDown);
        canvas.removeEventListener('pointermove', handlePointerMove);
        canvas.removeEventListener('pointerup', handlePointerUp);
        canvas.removeEventListener('pointerleave', handlePointerUp);

      }
    }
    if (useZoomGraph) {
    canvas.addEventListener('wheel', handleWheel, { passive: false });
    canvas.addEventListener('touchstart', handleTouchStart, { passive: false });
    canvas.addEventListener('touchmove', handleTouchMove, { passive: false });
    canvas.addEventListener('touchend', handleTouchEnd);

      // Новые pointer events для ПК и тачей
    canvas.addEventListener('pointerdown', handlePointerDown);
    canvas.addEventListener('pointermove', handlePointerMove);
    canvas.addEventListener('pointerup', handlePointerUp);
    canvas.addEventListener('pointerleave', handlePointerUp);

    }
    return () => {
      if (canvas) {
        canvas.removeEventListener('wheel', handleWheel);
        canvas.removeEventListener('touchstart', handleTouchStart);
        canvas.removeEventListener('touchmove', handleTouchMove);
        canvas.removeEventListener('touchend', handleTouchEnd);

        canvas.removeEventListener('pointerdown', handlePointerDown);
      canvas.removeEventListener('pointermove', handlePointerMove);
      canvas.removeEventListener('pointerup', handlePointerUp);
      canvas.removeEventListener('pointerleave', handlePointerUp);

      }
    };
  }, [zoomLevel, offset, useZoomGraph]);

  return <canvas ref={canvasRef} width="400" height="370" />;
};

export default SpreadChart2;
