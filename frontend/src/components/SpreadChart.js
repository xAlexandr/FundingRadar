import { all } from 'axios';
import React, { useRef, useEffect, useState } from 'react';

const SpreadChart = ({ entrySpread, exitSpread, useEntrySpread, useExitSpread, time, coin }) => {

 // console.log(useEntrySpread, useExitSpread)
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

  // Очищаем график при изменении монеты
  useEffect(() => {
    const debounceTimeout = setTimeout(() => {
      chartDataRef.current = { entrySpreads: [], exitSpreads: [], times: [] };
      setChartData({ entrySpreads: [], exitSpreads: [], times: [] });
    }, 2000); // 300 мс для дебаунса

    return () => clearTimeout(debounceTimeout);
  }, [coin]);




  useEffect(() => {
   
    if (entrySpread != 'wait' && entrySpread != 'Error' && entrySpread != null)
    {
    // if (
    //   chartDataRef.current.entrySpreads.at(-1) !== entrySpread ||
    //   chartDataRef.current.exitSpreads.at(-1) !== exitSpread ||
    //   chartDataRef.current.times.at(-1) !== time
    // ) {
      chartDataRef.current.entrySpreads.push(entrySpread);
      chartDataRef.current.exitSpreads.push(exitSpread);
      chartDataRef.current.times.push(time);

      if (chartDataRef.current.entrySpreads.length > 36) {
        chartDataRef.current.entrySpreads.shift();
        chartDataRef.current.exitSpreads.shift();
        chartDataRef.current.times.shift();
      }

      setChartData({
        entrySpreads: [...chartDataRef.current.entrySpreads],
        exitSpreads: [...chartDataRef.current.exitSpreads],
        times: [...chartDataRef.current.times],
      });
 //   }
}
  }, [entrySpread, exitSpread, time]);

  useEffect(() => {
    const ctx = canvasRef.current.getContext('2d');
   // const dpr = window.devicePixelRatio || 1;
    const dpr = Math.max(window.devicePixelRatio || 1, 3);
    // Фиксированные размеры канваса в пикселях (на визуализацию)
    const width = 400;
    const height = 370;

    // Устанавливаем реальные размеры канваса с учетом devicePixelRatio
    canvasRef.current.width = width * dpr;
    canvasRef.current.height = height * dpr;

    // Масштабируем контекст с учетом devicePixelRatio
    ctx.scale(dpr, dpr);
    
    
    
    const marginBottom = 30;
   
    let marginRight = 35;
   

    const graphWidth = width - marginRight;
    const graphHeight = height - marginBottom;

    const allSpreads = [...chartData.entrySpreads,
       ...chartData.exitSpreads,
       useEntrySpread !== "" ? useEntrySpread : null,
       useExitSpread !== "" ? useExitSpread : null,
      ].filter(Boolean);

    let maxSpread = Math.max(...allSpreads) * (Math.max(...allSpreads) > 0 ? 1.1 : 0.9);
    let minSpread = Math.min(...allSpreads) * (Math.min(...allSpreads) < 0 ? 1.1 : 0.9);
    if (maxSpread - minSpread < 0.1) {
      maxSpread += 0.05;
      minSpread -= 0.05;
    }  
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
        const maxSteps = 10;
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
   
   //   const step = calculateStep(); // Динамически вычисляем шаг
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
        ctx.lineTo(graphWidth + 0, y);
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
     // ctx.fillStyle = '#243036';
     // ctx.fillStyle = '#1b2429';
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
      
      // gridLevels.forEach((y, i) => {
      //     let label = formatPercentBefore(gridValues[i]);
      //     ctx.fillText(label.text, graphWidth + label.offset - 15, y+3);
      // });

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
        gradient.addColorStop(0, 'rgba(255, 107, 107, 0.2)');
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
        ctx.lineWidth = 2;
        ctx.stroke();
      };

      drawLine(chartData.exitSpreads, '#c45850');
      drawLine(chartData.entrySpreads, '#3cba9f');

      const exitY = graphHeight - (exitSpread - lowerLimit) * scale;
      const entryY = graphHeight - (entrySpread - lowerLimit) * scale;


      // НОЛЬ
      // if (exitSpread > 0 && entrySpread < 0) {
      //   const zeroY = graphHeight - (0 - lowerLimit) * scale;
      //   ctx.setLineDash([5, 5]);
      //   ctx.strokeStyle = 'rgba(192, 192, 192, 0.8)';
      //   ctx.beginPath();
      //   ctx.moveTo(0, zeroY);
      //   ctx.lineTo(graphWidth, zeroY);
      //   ctx.stroke();
      //   ctx.setLineDash([]);
      //   ctx.fillStyle = 'rgba(192, 192, 192, 0.9)';
      //   ctx.fillRect(graphWidth + 70, zeroY - 10, 30, 20);
      //   ctx.fillStyle = '#FFF';
      //   ctx.fillText('0.00', graphWidth + 85, zeroY);
      // }

      ctx.setLineDash([5, 5]);
      ctx.strokeStyle = '#c45850';
     
      ctx.beginPath();
      ctx.moveTo(0, exitY);
     
        ctx.lineTo(graphWidth, exitY);
      
      
      ctx.stroke();

      ctx.strokeStyle = '#3cba9f';
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
        
       
        let offset = value_to_show.length >= 7 ? 28 : value_to_show.length >= 6 ? 25 : 22;
     


        return { text: value_to_show, offset };
      };



      const drawLine2 = (spread, color, label, yPosition, x, y, red_green) => {
        ctx.beginPath();
        ctx.moveTo(0, yPosition); // Начальная точка
        ctx.lineTo(graphWidth + 0, yPosition); // Конечная точка
        ctx.strokeStyle = color;
        ctx.lineWidth = 2;
        ctx.stroke();
        

        
        const padding = 5;
        const textWidth = ctx.measureText(label).width + padding * 2;
        let textHeight = 12
        // Добавляем подписи справа
     
        let labelOffset = label.length >= 7 ? 3 : label.length >= 6 ? 3 : 3;
 
        if (red_green == 'green') {
          ctx.fillStyle = 'rgba(72, 174, 72, 0.5)';
        } else {
          ctx.fillStyle = 'rgba(183, 93, 79, 0.5)';
        }
        
        ctx.fillRect(x - textWidth / 2, y - textHeight / 2, textWidth, textHeight);
        

        // Настраиваем обводку текста (обратный цвет для контраста)
        // ctx.strokeStyle = 'rgba(255, 255, 255, 0.8)';
        // ctx.lineWidth = 1;
        // ctx.strokeText(label, graphWidth + labelOffset, yPosition);

        // Настраиваем тень для текста
        ctx.shadowColor = 'rgba(0, 0, 0, 0.5)';
        ctx.shadowBlur = 4;
        ctx.shadowOffsetX = 2;
        ctx.shadowOffsetY = 2;
        
        ctx.fillStyle = color;
        ctx.font = 'bold 12px Arial';
        ctx.textAlign = 'left';
        ctx.fillText(label, graphWidth + labelOffset, yPosition);

        // Очищаем тень, чтобы она не мешала другим элементам
        ctx.shadowColor = 'transparent';
        ctx.shadowBlur = 0;
        ctx.shadowOffsetX = 0;
        ctx.shadowOffsetY = 0;


      };

      const entryY2 = graphHeight - (useEntrySpread - lowerLimit) * scale;
const exitY2 = graphHeight - (useExitSpread - lowerLimit) * scale;

// Форматирование текста для входа и выхода
let entryLabel2 = formatPercent(useEntrySpread);
let exitLabel2 = formatPercent(useExitSpread);

// Рисуем линии
if (entryLabel2.text != "NaN")
{
  drawLine2(useEntrySpread, '#66cc66', entryLabel2.text, entryY2, graphWidth + 22, entryY2, 'green'); // Линия входа (зеленая)
}
if (exitLabel2.text != "NaN") {
  drawLine2(useExitSpread, '#d57b6d', exitLabel2.text, exitY2, graphWidth + 20, exitY2, 'red');   // Линия выхода (красная)
}


      ctx.font = 'bold 14px Arial';
      ctx.textAlign = 'center';
      ctx.textBaseline = 'middle';

      let exitLabel = formatPercent(exitSpread);
      let entryLabel = formatPercent(entrySpread);
     
      const drawLabel = (text, x, y, bgColor) => {
        const padding = 5;
        const textWidth = ctx.measureText(text).width + padding * 2;
       
        let textHeight = 14;
   

        
        ctx.fillStyle = bgColor;
        ctx.fillRect(x - textWidth / 2, y - textHeight / 2, textWidth, textHeight);
      //  ctx.fillStyle = '#FFF';
        ctx.fillStyle = 'rgba(255, 255, 255, 0.9)'; // Полупрозрачный белый цвет
        ctx.fillText(text, x, y);
      };


      
      
      
//       ctx.fillStyle = 'rgba(255, 255, 255, 0.9)';
// ctx.font = '12px Arial';
// ctx.textAlign = 'left';

// gridLevels.forEach((y, i) => {
//     let label = formatPercent(gridValues[i]);
//     ctx.fillText(label.text, graphWidth + label.offset, y);
// });
//       const gridValues = [maxSpread, (maxSpread + minSpread) / 2, minSpread];

// gridLevels.forEach((y, i) => {
//     let label = formatPercent(gridValues[i]);
//     ctx.fillText(label.text, graphWidth + label.offset, y);
// });



      // const maxY = graphHeight - (maxSpread - lowerLimit) * scale;
      // const minY = graphHeight - (minSpread - lowerLimit) * scale;
      
      // ctx.fillStyle = 'rgba(255, 255, 255, 0.9)';
      // ctx.font = '12px Arial';
      // ctx.textAlign = 'left';
      
      // ctx.fillText(maxSpread.toFixed(2), graphWidth + 75, maxY);
      // ctx.fillText(minSpread.toFixed(2), graphWidth + 75, minY);


      // Отрисовка времени на оси X
      if (totalPoints > 1) {
        ctx.fillStyle = 'rgba(255, 255, 255, 0.8)';
        ctx.font = '12px Arial';
        ctx.textAlign = 'center';
        ctx.textBaseline = 'top';
    
        const timeStep = 4; // Подписывать каждую 4-ю точку
        const visibleTimes = chartData.times.slice(-36); // Отображаем последние 36 точек (двигаем окно)
        const visiblePoints = visibleTimes.length;
        const newStep = visiblePoints > 1 ? graphWidth / (visiblePoints - 1) : 0;
    
        for (let i = 0; i < visiblePoints; i += timeStep) {
            const x = i * newStep;
            ctx.fillText(visibleTimes[i].split(':').slice(-2).join(':'), x, graphHeight + 10);
        }
    }

   


    };

    updateChart();
  }, [chartData]);

  return <canvas className="first" ref={canvasRef} width="400" height="370" />;
};

export default SpreadChart;
