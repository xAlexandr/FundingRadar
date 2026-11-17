import { all } from 'axios';
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
  
    useEffect(() => {
     
      if (entrySpread != 'wait' && entrySpread != 'Error')
      {
      if (
        chartDataRef.current.entrySpreads !== entrySpread ||
        chartDataRef.current.exitSpreads !== exitSpread ||
        chartDataRef.current.times !== time
      ) {
        chartDataRef.current.entrySpreads = entrySpread;
        chartDataRef.current.exitSpreads = exitSpread;
        chartDataRef.current.times = time;
  
        // if (chartDataRef.current.entrySpreads.length > 24) {
        //   chartDataRef.current.entrySpreads.shift();
        //   chartDataRef.current.exitSpreads.shift();
        //   chartDataRef.current.times.shift();
        // }
  
        setChartData({
          entrySpreads: [...chartDataRef.current.entrySpreads],
          exitSpreads: [...chartDataRef.current.exitSpreads],
          times: [...chartDataRef.current.times],
        });
      }
  }
    }, [entrySpread, exitSpread, time]);
  
    useEffect(() => {
      const ctx = canvasRef.current.getContext('2d');
      const dpr = Math.max(window.devicePixelRatio || 1, 3);

    // Фиксированные размеры канваса в пикселях (на визуализацию)
    const width = 400;
    const height = 370;

    // Устанавливаем реальные размеры канваса с учетом devicePixelRatio
    canvasRef.current.width = width * dpr;
    canvasRef.current.height = height * dpr;

    // Масштабируем контекст с учетом devicePixelRatio
    ctx.scale(dpr, dpr);
  
      const marginRight = 35;
      const marginBottom = 30;
      const graphWidth = width - marginRight;
      const graphHeight = height - marginBottom;
  
      const allSpreads = [...chartData.entrySpreads, ...chartData.exitSpreads];
      let maxSpread = Math.max(...allSpreads);
      const minSpread = Math.min(...allSpreads);
      const padding = (maxSpread - minSpread) * 0.35; // Делаем график более центрированным
      const minStep = 0.1;
  
      const minSpreadCondition = Math.abs(minSpread) < 1 && Math.abs(maxSpread) < 1;
    let lowerLimit, upperLimit, step;
    
    
    if (minSpreadCondition) {
    //  console.log('yeah')
      // Для значений, меньше 0.3 и больше -0.3, устанавливаем лимиты 0.5
      lowerLimit = -1;
      upperLimit = 1;
      step = 0.2;  // Устанавливаем шаг 0.1
   } else {
      // В остальных случаях рассчитываем лимиты как раньше
      lowerLimit = minSpread - padding;
      upperLimit = maxSpread + padding;
      // Динамически вычисляем сдвиг вверх для верхнего предела
      // const dynamicShift = (upperLimit - lowerLimit) * 0.05;  // 5% от диапазона

      // upperLimit += 0.1 + dynamicShift;  // Приопускаем график добавляя 0.1 и динамический сдвиг
      const calculateStep = () => {
        const range = upperLimit - lowerLimit;
        // Ограничиваем количество шагов, чтобы не было больше 10 значений по оси Y
        const maxSteps = 12;
        const steps = Math.min(Math.floor(graphHeight / range), maxSteps);
      
        // Исходный шаг
        let step = range / steps;
      
        // Округляем шаг до ближайшего числа, кратного 0.2
        step = Math.ceil(step / 0.2) * 0.2;
      
        // Используем минимальный шаг, если он больше, чем вычисленный
        if (step < minStep) {
          step = minStep;
        }
      
        return step;
      };
      step = calculateStep();  // Динамически вычисляем шаг
   }

// Расчет масштаба на основе установленного диапазона
const scale = graphHeight / (upperLimit - lowerLimit);  // Масштаб по оси Y
let gridLevels = [];
let gridValues = [];
let start = lowerLimit;

// Проверяем, что значения сетки начинаются с числа, кратного 0.2
while (start <= upperLimit) {
  let y = graphHeight - (start - lowerLimit) * scale;  // Масштабирование по оси Y
  gridLevels.push(y);
  gridValues.push(start);

  // Округление и шаг, кратный 0.2
  if (minSpreadCondition)
  {
    start = Math.round((start + step) / 0.1) * 0.1;
  } else {
    start = Math.round((start + step) / 0.2) * 0.2;
  }
  
}

     const drawGrid = () => {
      ctx.strokeStyle = 'rgba(255, 255, 255, 0.15)'; // Еле видимый цвет
      ctx.lineWidth = 1;
      ctx.setLineDash([4, 4]); // Пунктирная линия
  
     

      gridLevels.forEach(y => {
          ctx.beginPath();
          ctx.moveTo(0, y);
          ctx.lineTo(graphWidth, y);
          ctx.stroke();
      });
  
      // Вертикальные линии (делим график на 3 части)
      for (let i = 1; i <= 2; i++) {
          let x = (graphWidth / 3) * i;
          ctx.beginPath();
          ctx.moveTo(x, 0);
          ctx.lineTo(x, graphHeight);
          ctx.stroke();
      }
  
      ctx.setLineDash([]); // Убираем пунктир после сетки
  };

  
      const updateChart = () => {
        ctx.clearRect(0, 0, width, height);
        ctx.fillStyle = '#243036';
        ctx.fillRect(0, 0, width, height);
        
        drawGrid(); // Рисуем сетку перед графиком

      const formatPercentBefore = (value) => {
        let value_to_show = parseFloat(value).toFixed(1);
        if (value_to_show >= 0) {
            value_to_show = ' ' + value_to_show;
        }
        

        let offset = value_to_show.length >= 7 ? 98 : value_to_show.length >= 6 ? 95 : 92;


        return { text: value_to_show, offset };
      };

      ctx.fillStyle = 'rgba(255, 255, 255, 0.8)';
      ctx.font = '12px Arial';
      ctx.textAlign = 'left';

      gridLevels.forEach((y, i) => {
          let label = formatPercentBefore(gridValues[i]);
          let yOffset = i === (gridLevels.length - 1) ? y + 10 : y + 3; // Только для первого уровня
          ctx.fillText(label.text, graphWidth + label.offset - 85, yOffset);
      });


        const totalPoints = chartData.entrySpreads.length;
        const step = totalPoints > 1 ? graphWidth / (totalPoints - 1) : 0;
  
        if (totalPoints > 1) {
          ctx.beginPath();
          ctx.moveTo(0, graphHeight - (chartData.exitSpreads[0] - lowerLimit) * scale);
          for (let i = 0; i < totalPoints; i++) {
            const x = i * step;
            const y = graphHeight - (chartData.exitSpreads[i] - lowerLimit) * scale;
            ctx.lineTo(x, y);
          }
          for (let i = totalPoints - 1; i >= 0; i--) {
            const x = i * step;
            const y = graphHeight - (chartData.entrySpreads[i] - lowerLimit) * scale;
            ctx.lineTo(x, y);
          }
          ctx.closePath();
  
          const gradient = ctx.createLinearGradient(0, 0, 0, graphHeight);
          gradient.addColorStop(0, 'rgba(255, 107, 107, 0.3)');
          gradient.addColorStop(1, 'rgba(255, 107, 107, 0.0)');
          ctx.fillStyle = gradient;
          ctx.fill();
        }
  
        const drawLine = (spreads, color) => {
          ctx.beginPath();
          spreads.forEach((spread, i) => {
            const x = i * step;
            const y = graphHeight - (spread - lowerLimit) * scale;
            if (i === 0) ctx.moveTo(x, y);
            else ctx.lineTo(x, y);
          });
          ctx.strokeStyle = color;
          ctx.lineWidth = 1.5;
          ctx.stroke();
        };
  
        drawLine(chartData.exitSpreads, '#FF6B6B');
        drawLine(chartData.entrySpreads, '#00C6A2');
  
        const exitY = graphHeight - (exitSpread.at(-1) - lowerLimit) * scale;
        const entryY = graphHeight - (entrySpread.at(-1) - lowerLimit) * scale;
  
        ctx.strokeStyle = '#FFF';
        ctx.lineWidth = 1;
        ctx.beginPath();
        ctx.moveTo(graphWidth, 0);
        ctx.lineTo(graphWidth, graphHeight);
        ctx.lineTo(0, graphHeight);
        ctx.stroke();
  
        if (exitSpread.at(-1) > 0 && entrySpread.at(-1) < 0) {
          const zeroY = graphHeight - (0 - lowerLimit) * scale;
       //   ctx.setLineDash([5, 5]);
          ctx.strokeStyle = 'rgba(192, 192, 192, 0.8)';
          ctx.beginPath();
          ctx.moveTo(0, zeroY);
          ctx.lineTo(graphWidth, zeroY);
          ctx.stroke();
          ctx.setLineDash([]);
          ctx.fillStyle = 'rgba(192, 192, 192, 0.9)';
          ctx.fillRect(graphWidth, zeroY - 10, 30, 18);
          ctx.fillStyle = '#FFF';
          ctx.fillText('0.00', graphWidth + 3, zeroY + 3);
        }
  
        ctx.setLineDash([5, 5]);
        ctx.strokeStyle = '#FF6B6B';
        ctx.beginPath();
        ctx.moveTo(0, exitY);
        ctx.lineTo(graphWidth, exitY);
        ctx.stroke();
  
        ctx.strokeStyle = '#00C6A2';
        ctx.beginPath();
        ctx.moveTo(0, entryY);
        ctx.lineTo(graphWidth, entryY);
        ctx.stroke();
        ctx.setLineDash([]);
  
        ctx.font = 'bold 14px Arial';
        ctx.textAlign = 'center';
        ctx.textBaseline = 'middle';
  
        const formatPercent = (value) => {
          let value_to_show = parseFloat(value).toFixed(2);
          if (value_to_show >= 0) {
              value_to_show = ' ' + value_to_show;
          }
          
  
          let offset = value_to_show.length >= 7 ? 98 : value_to_show.length >= 6 ? 95 : 92;
  
  
          return { text: value_to_show, offset };
        };
  
        let exitLabel = formatPercent(exitSpread.at(-1));
        let entryLabel = formatPercent(entrySpread.at(-1));
       
        const drawLabel = (text, x, y, bgColor) => {
          const padding = 5;
          const textWidth = ctx.measureText(text).width + padding * 2;
          const textHeight = 24;
          ctx.fillStyle = bgColor;
          ctx.fillRect(x - textWidth / 2, y - textHeight / 2, textWidth, textHeight);
         // ctx.fillStyle = '#FFF';
          ctx.fillStyle = 'rgba(255, 255, 255, 0.9)'; // Полупрозрачный белый цвет
          ctx.fillText(text, x, y);
        };
  
        // drawLabel('Выход', graphWidth + 41, exitY, 'rgba(255, 90, 90, 0.9)');
        // drawLabel('Вход', graphWidth + 47, entryY, 'rgba(0, 180, 162, 0.9)');
        drawLabel(exitLabel.text, graphWidth + exitLabel.offset, exitY, 'rgba(255, 90, 90, 0.9)');
        drawLabel(entryLabel.text, graphWidth + entryLabel.offset, entryY, 'rgba(0, 180, 162, 0.9)');
  
        // Отрисовка времени на оси X
        // if (totalPoints > 1) {
        //   ctx.fillStyle = 'rgba(255, 255, 255, 0.8)'; // Полупрозрачный белый цвет
        //   ctx.font = ' bold 12px Arial';
        //   ctx.textAlign = 'center';
        //   ctx.textBaseline = 'top';
  
        //   const timeStep = Math.ceil(totalPoints / 6); // Подписываем каждую 6-ю точку
        //   for (let i = 0; i < totalPoints; i += timeStep) {
        //     const x = i * step;
        //     ctx.fillText(chartData.times[i], x+30, graphHeight + 5);
        //   }
        // }
        if (totalPoints > 1) {
          ctx.fillStyle = 'rgba(255, 255, 255, 0.8)';
          ctx.font = '12px Arial';
          ctx.textAlign = 'center';
          ctx.textBaseline = 'top';
      
          const timeStep = 6; // Подписывать каждую 4-ю точку
          const visibleTimes = chartData.times; // Отображаем последние 36 точек (двигаем окно)
          const visiblePoints = visibleTimes.length;
          const newStep = visiblePoints > 1 ? graphWidth / (visiblePoints - 1) : 0;
      
          for (let i = 0; i < visiblePoints; i += timeStep) {
              const x = i * newStep;
              ctx.fillText(visibleTimes[i], x, graphHeight + 10);
          }
      }
     
  
  
      };
  
      updateChart();
    }, [chartData]);
  
    return <canvas ref={canvasRef} width="400" height="370" />;
  };
  
  export default SpreadChart2;