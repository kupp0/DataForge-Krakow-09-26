"""
Disneyland Hackathon: Visual Celebration & Impacted Cities Confetti Engine
Renders dynamic visual effects for the Closing Ceremony:
1. Impacted Cities Popping Confetti HUD: Animated neon city badges that pop up
   randomly across the viewport like celebratory confetti when an event occurs.
2. Grand Finale HTML5 Canvas Fireworks on winner reveal.
3. Zero audio dependencies.
"""
from typing import List
import random
import json

def get_celebration_audio_html(*args, **kwargs) -> str:
    """Audio disabled by user request: returns empty string."""
    return ""

def get_impacted_cities_popup_html(
    impacted_cities: List[str] = None,
    round_id: int = 1,
    event_icon: str = "💥",
    event_title: str = "Event Impact"
) -> str:
    """
    Cleans up any lingering city confetti animation overlay elements from the parent document DOM.
    """
    return """
    <script>
    (function() {
        try {
            const pDoc = window.parent.document;
            if (!pDoc) return;
            const oldOverlay = pDoc.getElementById("city-confetti-overlay");
            if (oldOverlay) oldOverlay.remove();
            const oldStyles = pDoc.getElementById("city-confetti-styles");
            if (oldStyles) oldStyles.remove();
        } catch (e) {}
    })();
    </script>
    """

def get_fireworks_canvas_html() -> str:
    """
    Renders high-visibility animated fireworks bursts on an HTML5 canvas overlay.
    Triggered during Round 5 Grand Finale podium celebration.
    """
    return """
    <div id="fireworks-container" style="
        position: fixed;
        top: 0;
        left: 0;
        width: 100vw;
        height: 100vh;
        pointer-events: none;
        z-index: 999998;
        overflow: hidden;
    ">
        <canvas id="fireworks-canvas" style="width: 100%; height: 100%; display: block;"></canvas>
    </div>

    <script>
    (function() {
        const pDoc = window.parent.document;
        let canvas = pDoc.getElementById('ceremony-fireworks-canvas');
        if (!canvas) {
            const container = pDoc.createElement('div');
            container.id = 'ceremony-fireworks-container';
            container.style.position = 'fixed';
            container.style.top = '0';
            container.style.left = '0';
            container.style.width = '100vw';
            container.style.height = '100vh';
            container.style.pointerEvents = 'none';
            container.style.zIndex = '999998';
            container.style.overflow = 'hidden';

            canvas = pDoc.createElement('canvas');
            canvas.id = 'ceremony-fireworks-canvas';
            canvas.style.width = '100%';
            canvas.style.height = '100%';
            canvas.style.display = 'block';
            container.appendChild(canvas);
            pDoc.body.appendChild(container);
        }

        const ctx = canvas.getContext('2d');
        let width = canvas.width = window.parent.innerWidth;
        let height = canvas.height = window.parent.innerHeight;

        const onResize = () => {
            width = canvas.width = window.parent.innerWidth;
            height = canvas.height = window.parent.innerHeight;
        };
        window.parent.addEventListener('resize', onResize);

        const particles = [];
        const colors = ['#ffd700', '#ff79c6', '#50fa7b', '#8be9fd', '#bd93f9', '#ff5555', '#ffb86c', '#ffffff'];

        function createBurst(x, y, count = 45) {
            for (let i = 0; i < count; i++) {
                const angle = Math.random() * Math.PI * 2;
                const speed = 2 + Math.random() * 6;
                particles.push({
                    x: x,
                    y: y,
                    vx: Math.cos(angle) * speed,
                    vy: Math.sin(angle) * speed,
                    color: colors[Math.floor(Math.random() * colors.length)],
                    radius: 2.5 + Math.random() * 3.5,
                    alpha: 1,
                    decay: 0.012 + Math.random() * 0.016,
                    gravity: 0.07
                });
            }
        }

        let timer = 0;
        let animId = null;

        function animate() {
            ctx.clearRect(0, 0, width, height);
            timer++;

            if (timer < 280 && timer % 45 === 0) {
                const burstX = width * (0.15 + Math.random() * 0.7);
                const burstY = height * (0.12 + Math.random() * 0.45);
                createBurst(burstX, burstY, 45);
            }

            for (let i = particles.length - 1; i >= 0; i--) {
                const p = particles[i];
                p.x += p.vx;
                p.y += p.vy;
                p.vy += p.gravity;
                p.alpha -= p.decay;

                if (p.alpha <= 0) {
                    particles.splice(i, 1);
                    continue;
                }

                ctx.save();
                ctx.globalAlpha = p.alpha;
                ctx.fillStyle = p.color;
                ctx.beginPath();
                ctx.arc(p.x, p.y, p.radius, 0, Math.PI * 2);
                ctx.fill();
                ctx.restore();
            }

            if (timer < 360 || particles.length > 0) {
                animId = requestAnimationFrame(animate);
            } else {
                const c = pDoc.getElementById('ceremony-fireworks-container');
                if (c) c.remove();
                window.parent.removeEventListener('resize', onResize);
            }
        }

        setTimeout(() => createBurst(width * 0.25, height * 0.28, 50), 200);
        setTimeout(() => createBurst(width * 0.75, height * 0.25, 50), 500);
        setTimeout(() => createBurst(width * 0.5, height * 0.2, 65), 850);

        animate();
    })();
    </script>
    """
