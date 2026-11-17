import React, { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";

const Testimonials = () => {
  const { t } = useTranslation();
  const items = [
    { img: "/images/close-chat.png", imgAltKey: "testimonials.items.0.imgAlt", titleKey: "testimonials.items.0.title", textKey: "testimonials.items.0.text", authorKey: "testimonials.items.0.author" },
    { img: "/images/close-chat.png", imgAltKey: "testimonials.items.1.imgAlt", titleKey: "testimonials.items.1.title", textKey: "testimonials.items.1.text", authorKey: "testimonials.items.1.author" },
    { img: "/images/close-chat.png", imgAltKey: "testimonials.items.2.imgAlt", titleKey: "testimonials.items.2.title", textKey: "testimonials.items.2.text", authorKey: "testimonials.items.2.author" },
  ];

  const AUTOPLAY = 6000;
  const [index, setIndex] = useState(0);             // canonical index
  const [activeIndex, setActiveIndex] = useState(0); // for dots (follows drag)
  const [paused, setPaused] = useState(false);

  const startXRef = useRef(0);
  const prevTranslateRef = useRef(0);
  const currentTranslateRef = useRef(0);
  const isDraggingRef = useRef(false);
  const viewportRef = useRef(null);
  const trackRef = useRef(null);
  const autoplayRef = useRef(null);
  const movedRef = useRef(false);

  // autoplay (interval)
  useEffect(() => {
    if (paused) {
      if (autoplayRef.current) { clearInterval(autoplayRef.current); autoplayRef.current = null; }
      return;
    }
    if (autoplayRef.current) clearInterval(autoplayRef.current);
    autoplayRef.current = setInterval(() => setIndex(i => (i + 1) % items.length), AUTOPLAY);
    return () => { if (autoplayRef.current) { clearInterval(autoplayRef.current); autoplayRef.current = null; } };
  }, [paused, items.length]);

  // When canonical index changes (by buttons/autoplay/dots), snap (unless dragging)
  useEffect(() => {
    if (!isDraggingRef.current) {
      setActiveIndex(index);
      snapToIndex(index, true);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [index]);

  // helpers
  function getSlideWidth() {
    return viewportRef.current ? viewportRef.current.clientWidth : 0;
  }
  function setSliderTransform(xPx, transition = true) {
    const el = trackRef.current;
    if (!el) return;
    el.style.transition = transition ? "transform 420ms cubic-bezier(.22,.9,.25,1)" : "none";
    el.style.transform = `translateX(${xPx}px)`;
  }
  function snapToIndex(i, withTransition = true) {
    const slideW = getSlideWidth();
    const clamped = Math.max(0, Math.min(items.length - 1, i));
    const x = -clamped * slideW;
    prevTranslateRef.current = x;
    currentTranslateRef.current = x;
    setSliderTransform(x, withTransition);
  }

  // touch / drag handlers
  function touchStart(clientX) {
    setPaused(true);
    isDraggingRef.current = true;
    startXRef.current = clientX;
    prevTranslateRef.current = currentTranslateRef.current;
    movedRef.current = false;
    // cancel transition while dragging
    setSliderTransform(prevTranslateRef.current, false);
  }

  function touchMove(clientX) {
    if (!isDraggingRef.current) return;
    const dx = clientX - startXRef.current;
    if (Math.abs(dx) > 6) movedRef.current = true;

    const slideW = getSlideWidth();
    const maxTranslate = 0;
    const minTranslate = - (items.length - 1) * slideW;

    let newTranslate = prevTranslateRef.current + dx;

    // резиновый эффект за краями
    if (newTranslate > maxTranslate) {
      const over = newTranslate - maxTranslate;
      newTranslate = maxTranslate + over / 3;
    } else if (newTranslate < minTranslate) {
      const over = newTranslate - minTranslate;
      newTranslate = minTranslate + over / 3;
    }

    currentTranslateRef.current = newTranslate;
    setSliderTransform(currentTranslateRef.current, false);

    // live update active dot: ближайший слайд
    if (slideW > 0) {
      const nearest = Math.max(0, Math.min(items.length - 1, Math.round(-currentTranslateRef.current / slideW)));
      if (nearest !== activeIndex) setActiveIndex(nearest);
    }
  }

  function touchEnd() {
    if (!isDraggingRef.current) return;
    isDraggingRef.current = false;

    const slideW = getSlideWidth();
    if (slideW === 0) { snapToIndex(index, true); setTimeout(() => setPaused(false), 300); return; }

    const movedPx = currentTranslateRef.current - prevTranslateRef.current; // дельта
    const threshold = Math.max(slideW * 0.18, 50); // 18% или минимум 50px

    const minTranslate = - (items.length - 1) * slideW;

    // если слишком утащили за левую границу — snap к 0
    if (currentTranslateRef.current > 0) {
      const desired = 0;
      prevTranslateRef.current = desired;
      currentTranslateRef.current = desired;
      setSliderTransform(desired, true);
      setIndex(0);
      setActiveIndex(0);
      setTimeout(() => setPaused(false), 300);
      return;
    }

    // если утащили за правую границу — snap к последнему
    if (currentTranslateRef.current < minTranslate) {
      const desired = minTranslate;
      prevTranslateRef.current = desired;
      currentTranslateRef.current = desired;
      setSliderTransform(desired, true);
      setIndex(items.length - 1);
      setActiveIndex(items.length - 1);
      setTimeout(() => setPaused(false), 300);
      return;
    }

    // обычная логика: если прошёл порог — переключаемся, иначе snap к ближайшему
    if (movedPx > threshold && index > 0) {
      const target = index - 1;
      const desired = -target * slideW;
      prevTranslateRef.current = desired;
      currentTranslateRef.current = desired;
      setSliderTransform(desired, true);
      setIndex(target);
      setActiveIndex(target);
    } else if (movedPx < -threshold && index < items.length - 1) {
      const target = index + 1;
      const desired = -target * slideW;
      prevTranslateRef.current = desired;
      currentTranslateRef.current = desired;
      setSliderTransform(desired, true);
      setIndex(target);
      setActiveIndex(target);
    } else {
      // not enough move — snap to nearest (по позиции), чтобы не оставалось между
      const nearest = Math.max(0, Math.min(items.length - 1, Math.round(-currentTranslateRef.current / slideW)));
      const desired = -nearest * slideW;
      prevTranslateRef.current = desired;
      currentTranslateRef.current = desired;
      setSliderTransform(desired, true);
      setIndex(nearest);
      setActiveIndex(nearest);
    }

    setTimeout(() => { movedRef.current = false; }, 250);
    setTimeout(() => setPaused(false), 500);
  }

  // DOM handlers
  const onTouchStart = (e) => touchStart(e.touches ? e.touches[0].clientX : e.clientX);
  const onTouchMove = (e) => touchMove(e.touches ? e.touches[0].clientX : e.clientX);
  const onTouchEnd = () => touchEnd();

  // mouse drag (desktop)
  useEffect(() => {
    const onMouseMove = (e) => { if (!isDraggingRef.current) return; touchMove(e.clientX); };
    const onMouseUp = () => { if (!isDraggingRef.current) return; touchEnd(); };
    window.addEventListener("mousemove", onMouseMove);
    window.addEventListener("mouseup", onMouseUp);
    return () => { window.removeEventListener("mousemove", onMouseMove); window.removeEventListener("mouseup", onMouseUp); };
  }, []);

  useEffect(() => { setTimeout(() => snapToIndex(index, true), 0); /* initial */ }, []); // initial snap

  // keyboard navigation
  useEffect(() => {
    const onKey = (e) => { if (e.key === "ArrowLeft") setIndex(i => Math.max(0, i - 1)); if (e.key === "ArrowRight") setIndex(i => Math.min(items.length - 1, i + 1)); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [items.length]);

  // prevent img drag
  useEffect(() => {
    const imgs = trackRef.current ? trackRef.current.querySelectorAll("img") : [];
    imgs.forEach(img => img.setAttribute("draggable", "false"));
  });

  // controls
  const prev = () => { setIndex(i => Math.max(0, i - 1)); setPaused(true); setTimeout(() => setPaused(false), 1500); };
  const next = () => { setIndex(i => Math.min(items.length - 1, i + 1)); setPaused(true); setTimeout(() => setPaused(false), 1500); };

  // click protection (to prevent link click after drag)
  const startRef = useRef({ x: 0, y: 0 });
  const onPointerDown = (e) => { const p = e.touches?.[0] ?? e; startRef.current = { x: p.clientX, y: p.clientY || 0 }; };
  const onClickPreventIfDrag = (e) => { if (movedRef.current) { e.preventDefault(); e.stopPropagation(); return; } };

  return (
    <section className="landing-testimonials" aria-label={t("testimonials.title")}>
      <div className="container">
        <h2>{t("testimonials.title")}</h2>

        <div className="testimonials-wrap" onMouseEnter={() => setPaused(true)} onMouseLeave={() => setPaused(false)}>
          <button className="testimonials-nav prev" onClick={prev} aria-label={t("testimonials.prev")} type="button">‹</button>

          <div className="testimonials-viewport"
               ref={viewportRef}
               onTouchStart={onTouchStart}
               onTouchMove={onTouchMove}
               onTouchEnd={onTouchEnd}
               onMouseDown={(e) => { e.preventDefault(); touchStart(e.clientX); }}
          >
            <div className="testimonials-track" ref={trackRef} style={{ width: `${items.length * 100}%` }}>
              {items.map((it, i) => (
                <article key={i} className="testimonials-slide" role="group" aria-roledescription="slide" aria-label={t(it.titleKey)} style={{ flex: `0 0 ${100 / items.length}%` }}>
                  <div className="testimonials-left">
                    <a href="https://t.me/+Mycm8zll7VJkMDVi" target="_blank" rel="noopener noreferrer" className="testimonials-image-link" onPointerDown={onPointerDown} onTouchStart={onPointerDown} onClick={onClickPreventIfDrag}>
                      <img src={it.img} alt={t(it.imgAltKey)} draggable="false" className="testimonials-image" />
                    </a>
                    <div className="testimonials-chat">{t("testimonials.chatLabel")}</div>
                  </div>
                  <div className="testimonials-right">
                    <h3 className="testimonials-quote-title">{t(it.titleKey)}</h3>
                    <p className="testimonials-text">{t(it.textKey)}</p>
                    <div className="testimonials-author">{t(it.authorKey)}</div>
                  </div>
                </article>
              ))}
            </div>
          </div>

          <button className="testimonials-nav next" onClick={next} aria-label={t("testimonials.next")} type="button">›</button>

          <div className="testimonials-dots" role="tablist" aria-label={t("testimonials.dotsLabel")}>
            {items.map((_, i) => (
              <button key={i} type="button" className={`testimonials-dot ${i === activeIndex ? "active" : ""}`}
                      onClick={() => { setIndex(i); setActiveIndex(i); setPaused(true); setTimeout(() => setPaused(false), 1200); }}
                      aria-label={t("testimonials.dotAria", { i: i + 1 })} aria-pressed={i === activeIndex} role="tab" />
            ))}
          </div>
        </div>
      </div>
    </section>
  );
};

export default Testimonials;
