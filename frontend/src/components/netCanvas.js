let animationFrameId;

let w, h, ctx, canvas;
const ratio = window.devicePixelRatio || 1;

export function net_canvas() {
    canvas = document.createElement('canvas');
    canvas.classList.add('net-background-canvas');
    ctx = canvas.getContext('2d');

    const particles = [],
        properties = {
            bgColor: '#0a0f1f',
            particleColor: '#3db6f2',
            particleRadius: 3,
            particleCount: 70,
            particleMaxVelocity: 0.7,
            lineLength: 170,
            particleLife: 12
        };

    document.querySelector('.landing-container').appendChild(canvas);
    function updatePropertiesForScreenSize() {
    const width = window.innerWidth;

    if (width < 768) { // маленькие экраны
        properties.particleCount = 150;
        properties.lineLength = 180;
    } else if (width < 1200) { // средние экраны
        properties.particleCount = 200;
        properties.lineLength = 250;
    } else { // большие экраны
        properties.particleCount = 250;
        properties.lineLength = 350;
    }

    // Перезаполняем массив частиц, чтобы количество соответствовало новому значению
    while (particles.length && particles.length < properties.particleCount) {
        particles.push(new Particle());
    }
    while (particles.length && particles.length > properties.particleCount) {
        particles.pop();
    }
}
    function resizeCanvas() {
        w = (canvas.width = window.innerWidth * ratio) / ratio;
        h = (canvas.height = document.body.scrollHeight * ratio) / ratio; 
        ctx.setTransform(1, 0, 0, 1, 0, 0); // сбрасываем масштаб
        ctx.scale(ratio, ratio);
        updatePropertiesForScreenSize(); // обновляем свойства при ресайзе
    }
    
    resizeCanvas();
    window.addEventListener("resize", resizeCanvas);
        
    

    class Particle {
        constructor() {
            this.x = Math.random() * w;
            this.y = Math.random() * h;
            this.velocityX = (Math.random() * properties.particleMaxVelocity * 2) - properties.particleMaxVelocity;
            this.velocityY = (Math.random() * properties.particleMaxVelocity * 2) - properties.particleMaxVelocity;
            this.life = Math.random() * properties.particleLife * 60;
        }

        position() {
            if ((this.x + this.velocityX > w && this.velocityX > 0) || (this.x + this.velocityX < 0 && this.velocityX < 0)) {
                this.velocityX *= -1;
            }
            if ((this.y + this.velocityY > h && this.velocityY > 0) || (this.y + this.velocityY < 0 && this.velocityY < 0)) {
                this.velocityY *= -1;
            }
            this.x += this.velocityX;
            this.y += this.velocityY;
        }

        reDraw() {
            ctx.beginPath();
            ctx.arc(this.x, this.y, properties.particleRadius, 0, Math.PI * 2);
            ctx.closePath();
            ctx.fillStyle = properties.particleColor;
            ctx.fill();
        }

        reCalculateLife() {
            if (this.life < 1) {
                this.x = Math.random() * w;
                this.y = Math.random() * h;
                this.velocityX = (Math.random() * properties.particleMaxVelocity * 2) - properties.particleMaxVelocity;
                this.velocityY = (Math.random() * properties.particleMaxVelocity * 2) - properties.particleMaxVelocity;
                this.life = Math.random() * properties.particleLife * 60;
            }
            this.life--;
        }
    }

    function reDrawBackground() {
        ctx.fillStyle = properties.bgColor;
        ctx.fillRect(0, 0, w, h);
    }

    function drawLines() {
        for (let i = 0; i < particles.length; i++) {
            for (let j = i + 1; j < particles.length; j++) {
                const x1 = particles[i].x, y1 = particles[i].y,
                    x2 = particles[j].x, y2 = particles[j].y,
                    length = Math.sqrt((x2 - x1) ** 2 + (y2 - y1) ** 2);

                if (length < properties.lineLength) {
                    const opacity = 1 - length / properties.lineLength;
                    ctx.lineWidth = 0.5;
                    ctx.strokeStyle = `rgba(102,255,227,${opacity})`;
                    ctx.beginPath();
                    ctx.moveTo(x1, y1);
                    ctx.lineTo(x2, y2);
                    ctx.closePath();
                    ctx.stroke();
                }
            }
        }
    }

    function reDrawParticles() {
        for (let i = 0; i < particles.length; i++) {
            particles[i].reCalculateLife();
            particles[i].position();
            particles[i].reDraw();
        }
    }

    let lastTime = 0;
    function loop(timestamp) {
    if (timestamp - lastTime < 50) { // ~30fps
        animationFrameId = requestAnimationFrame(loop);
        return;
    }
    lastTime = timestamp;

    reDrawBackground();
    reDrawParticles();
    drawLines();
    animationFrameId = requestAnimationFrame(loop);
    }

    function init() {
        for (let i = 0; i < properties.particleCount; i++) {
            particles.push(new Particle());
        }
        loop();
    }

    init();
}

// Функция для остановки анимации
export function stopAnimation() {
    cancelAnimationFrame(animationFrameId);
  }