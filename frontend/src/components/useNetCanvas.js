// useNetCanvas.js
import { useEffect } from 'react';
import { net_canvas, stopAnimation } from './netCanvas';

const useNetCanvas = () => {
  useEffect(() => {
    net_canvas();

    return () => {
      stopAnimation();
      const canvas = document.querySelector('canvas');
      if (canvas) {
        canvas.remove();
      }
    };
  }, []);
};

export default useNetCanvas;