/* Bank card fan: left / center / right / behind — shared by wallet and /?demo=cards */
(function () {
  const FAN_POSE = {
    center: { x: 0, y: 0, scale: 1, rz: 0 },
    left: { x: -0.52, y: 10, scale: 0.9, rz: -9 },
    right: { x: 0.52, y: 10, scale: 0.9, rz: 9 },
    behind: { x: 0, y: 14, scale: 0.86, rz: 0 },
  };
  const BEHIND_EDGE = 1.65;
  const DRAG_INERTIA = 0.94;
  const FLICK_VELOCITY = 0.42;

  function mod(value, total) {
    return ((value % total) + total) % total;
  }

  function smoothstep(t) {
    const k = Math.max(0, Math.min(1, t));
    return k * k * (3 - 2 * k);
  }

  function lerpPose(a, b, t) {
    const k = smoothstep(t);
    return {
      x: a.x + (b.x - a.x) * k,
      y: a.y + (b.y - a.y) * k,
      scale: a.scale + (b.scale - a.scale) * k,
      rz: a.rz + (b.rz - a.rz) * k,
    };
  }

  function wrapRel(index, active, total) {
    let rel = index - active;
    if (total <= 1) return 0;
    while (rel > total / 2) rel -= total;
    while (rel < -total / 2) rel += total;
    return rel;
  }

  /** Дуга: center → бок → задняя кромка, без раннего схлопывания в x=0 */
  function fanPoseForRel(rel, total) {
    const abs = Math.abs(rel);
    const sign = rel < 0 ? -1 : 1;
    const side = sign < 0 ? FAN_POSE.left : FAN_POSE.right;

    if (total === 1) return abs < 0.35 ? FAN_POSE.center : FAN_POSE.behind;

    if (total === 2) {
      if (abs >= BEHIND_EDGE) return FAN_POSE.behind;
      if (rel >= 1) {
        const t = Math.min(1, rel - 1);
        const tuck = { x: 0.34, y: 12, scale: 0.88, rz: 5 };
        return lerpPose(lerpPose(FAN_POSE.right, tuck, t), FAN_POSE.behind, t * t);
      }
      if (rel >= 0) return lerpPose(FAN_POSE.center, FAN_POSE.right, rel);
      if (rel >= -1) return lerpPose(FAN_POSE.left, FAN_POSE.center, rel + 1);
      const t = Math.min(1, -rel - 1);
      const tuck = { x: -0.34, y: 12, scale: 0.88, rz: -5 };
      return lerpPose(lerpPose(tuck, FAN_POSE.left, 1 - t), FAN_POSE.behind, t * t);
    }

    if (abs >= BEHIND_EDGE) return FAN_POSE.behind;

    if (abs <= 1) {
      if (rel >= 0) return lerpPose(FAN_POSE.center, FAN_POSE.right, rel);
      return lerpPose(FAN_POSE.left, FAN_POSE.center, rel + 1);
    }

    const t = (abs - 1) / (BEHIND_EDGE - 1);
    const tuck = {
      x: sign * (0.4 - t * 0.28),
      y: 10 + t * 5,
      scale: 0.9 - t * 0.06,
      rz: sign * (8 - t * 7),
    };
    return lerpPose(side, lerpPose(tuck, FAN_POSE.behind, smoothstep(t)), t);
  }

  function stackOpacity(rel) {
    const a = Math.abs(rel);
    if (a < 1.02) return 1;
    if (a < 1.42) return 1 - smoothstep((a - 1.02) / 0.4) * 0.92;
    if (a < BEHIND_EDGE) return 0.08;
    return 0;
  }

  function stackZ(rel) {
    const a = Math.abs(rel);
    return Math.round(108 - a * 30 + (rel > 0 ? 0 : 0.4));
  }

  function createCardCarousel({root, track, state: carouselPos, onChange, onOpen}) {
    const label = root.getAttribute('aria-label');
    let notifiedCard;
    function selected() {
      const cards = carouselPos.all;
      return cards[mod(Math.round(carouselPos.value), cards.length)];
    }
    function refresh() {
      if (!root.clientWidth) return;
      carouselPos.slotPx = carouselSlot();
      applyCarouselTransforms();
    }
    function carouselSlot() {
      return Math.min(152, root.clientWidth * 0.34);
    }

    function applyCarouselTransforms() {
      const cards = carouselPos.all;
      if (!cards.length) return;
      const total = cards.length;
      const active = carouselPos.value;
      carouselPos.slotPx = carouselPos.slotPx || carouselSlot();
      const slot = carouselPos.slotPx;

      for (const element of track.children) {
        if (!element.classList.contains('carousel-card')) continue;
        const index = Number(element.dataset.index);
        const rel = wrapRel(index, active, total);
        const pose = fanPoseForRel(rel, total);
        const opacity = stackOpacity(rel);
        const centerish = Math.abs(rel) < 0.14;

        element.style.transform = `translate3d(calc(-50% + ${pose.x * slot}px),${pose.y}px,0) scale(${pose.scale}) rotateZ(${pose.rz}deg)`;
        element.style.opacity = String(opacity);
        element.style.zIndex = String(stackZ(rel));
        element.style.pointerEvents = opacity < 0.2 ? 'none' : 'auto';
        element.setAttribute('aria-hidden', opacity < 0.2 ? 'true' : 'false');
        element.tabIndex = centerish ? 0 : -1;
        element.style.filter = 'none';
        element.classList.toggle('is-center', centerish);
        element.dataset.fanRole = centerish ? 'center' : rel < -0.18 ? 'left' : rel > 0.18 ? 'right' : 'behind';
      }

      const live = selected();
      root.setAttribute('aria-label', `${label}. Активна: ${live.cardName || live.name}`);
      if (Math.abs(active - Math.round(active)) < 0.02 && live !== notifiedCard) {
        notifiedCard = live;
        onChange(live);
      }
    }

    function easeOutCubic(t) {
      const k = Math.max(0, Math.min(1, t));
      return 1 - Math.pow(1 - k, 3);
    }

    function animateCarousel(to) {
      if (!carouselPos.all.length) return;
      const total = carouselPos.all.length;
      const reduced = matchMedia('(prefers-reduced-motion: reduce)').matches;
      let destination = mod(Math.round(to), total);
      carouselPos.target = destination;
      cancelAnimationFrame(carouselPos.raf);

      const from = carouselPos.value;
      let distance = destination - from;
      while (distance > total / 2) distance -= total;
      while (distance < -total / 2) distance += total;
      destination = from + distance;

      if (reduced) {
        carouselPos.value = destination;
        applyCarouselTransforms();
        return;
      }

      const duration = Math.max(400, Math.min(560, 460 + 55 * Math.abs(distance)));
      const started = performance.now();
      root.classList.add('is-animating');

      function frame(now) {
        const progress = Math.min(1, (now - started) / duration);
        carouselPos.value = from + distance * easeOutCubic(progress);
        applyCarouselTransforms();
        if (progress < 1) carouselPos.raf = requestAnimationFrame(frame);
        else {
          carouselPos.value = destination;
          carouselPos.target = destination;
          applyCarouselTransforms();
          root.classList.remove('is-animating');
        }
      }
      carouselPos.raf = requestAnimationFrame(frame);
    }

    function carouselStep(direction) {
      if (!carouselPos.all.length) return;
      animateCarousel(Math.round(carouselPos.target) + direction);
    }

    function snapCarousel(value, velocity) {
      let snap = Math.round(value);
      if (Math.abs(velocity) > FLICK_VELOCITY) {
        snap = Math.round(value + Math.sign(velocity) * 0.4);
      }
      return snap;
    }

    function carouselPointerDown(event) {
      if (!carouselPos.all.length || (carouselPos.all.length < 2 && !onOpen)) return;
      if (root.classList.contains('is-animating')) return;
      carouselPos.down = true;
      carouselPos.locked = false;
      carouselPos.dragged = false;
      carouselPos.suppressTap = false;
      carouselPos.startX = event.clientX;
      carouselPos.lastX = event.clientX;
      carouselPos.lastTime = performance.now();
      carouselPos.pos0 = carouselPos.value;
      carouselPos.velocity = 0;
      cancelAnimationFrame(carouselPos.raf);
      carouselPos.startY = event.clientY;
    }

    function carouselPointerMove(event) {
      if (!carouselPos.down) return;
      const dx = event.clientX - carouselPos.startX;
      const dy = event.clientY - (carouselPos.startY ?? event.clientY);
      if (carouselPos.all.length < 2 && Math.hypot(dx, dy) > 6) {
        carouselPos.down = false;
        return;
      }
      if (!carouselPos.locked && Math.abs(dy) > 12 && Math.abs(dy) > Math.abs(dx)) {
        carouselPos.down = false;
        return;
      }
      if (!carouselPos.locked && Math.abs(dx) > 6) {
        carouselPos.locked = true;
        carouselPos.dragged = true;
        root.setPointerCapture(event.pointerId);
        carouselPos.pos0 = carouselPos.value;
        carouselPos.startX = event.clientX;
        carouselPos.lastX = event.clientX;
        carouselPos.lastTime = performance.now();
        carouselPos.velocity = 0;
        root.classList.add('is-dragging');
      }
      if (!carouselPos.locked) return;
      const now = performance.now();
      const deltaX = event.clientX - carouselPos.lastX;
      const deltaT = Math.max(1, now - carouselPos.lastTime);
      const sample = -deltaX / (carouselPos.slotPx * DRAG_INERTIA) / deltaT;
      carouselPos.velocity = Math.abs(sample) < 0.00008 ? 0 : carouselPos.velocity * 0.6 + sample * 0.4;
      carouselPos.lastX = event.clientX;
      carouselPos.lastTime = now;
      carouselPos.value = carouselPos.pos0 - (event.clientX - carouselPos.startX) / (carouselPos.slotPx * DRAG_INERTIA);
      applyCarouselTransforms();
    }

    function carouselPointerUp(event) {
      if (!carouselPos.down) return;
      carouselPos.down = false;
      root.classList.remove('is-dragging');
      if (carouselPos.dragged) {
        carouselPos.suppressTap = true;
        animateCarousel(snapCarousel(carouselPos.value, carouselPos.velocity));
      } else if (onOpen && event.pointerType === 'touch' && event.type === 'pointerup') {
        const card = event.target.closest('.carousel-card');
        if (card) {
          carouselPos.suppressTap = true;
          onOpen(carouselPos.all[Number(card.dataset.index)]);
        }
      }
      if (event.pointerId != null && root.hasPointerCapture(event.pointerId)) {
        root.releasePointerCapture(event.pointerId);
      }
    }

    function carouselTap(event) {
      if (!carouselPos.all.length || root.classList.contains('is-animating')) return;
      if (carouselPos.suppressTap && event.detail !== 0) {
        carouselPos.suppressTap = false;
        return;
      }
      const card = event.target.closest('.carousel-card');
      if (onOpen && card) {
        onOpen(carouselPos.all[Number(card.dataset.index)]);
        return;
      }
      if (carouselPos.all.length < 2) return;
      const active = event.target.closest('.carousel-card.is-center');
      if (active) {
        const rect = active.getBoundingClientRect();
        const x = event.clientX - rect.left;
        if (x < rect.width * 0.38) carouselStep(-1);
        else carouselStep(1);
        return;
      }
      const rect = root.getBoundingClientRect();
      const ratio = (event.clientX - rect.left) / rect.width;
      if (ratio < 0.4) carouselStep(-1);
      else if (ratio > 0.6) carouselStep(1);
    }

    function renderCarousel() {
      cancelAnimationFrame(carouselPos.raf);
      root.classList.remove('is-animating', 'is-dragging');
      carouselPos.down = false;
      carouselPos.suppressTap = false;
      notifiedCard = undefined;
      track.replaceChildren();
      const cards = carouselPos.all;
      if (!cards.length) {
        root.setAttribute('aria-label', label);
        onChange(undefined);
        return;
      }
      carouselPos.value = mod(carouselPos.value, cards.length);
      carouselPos.target = carouselPos.value;
      carouselPos.slotPx = carouselSlot();
      cards.forEach((card, index) => {
        const paint = carouselCardPaint(card);
        const element = document.createElement(onOpen ? 'button' : 'article');
        if (onOpen) element.type = 'button';
        element.className = 'carousel-card';
        element.dataset.index = String(index);
        element.style.backgroundColor = paint.color;
        element.style.setProperty('--bank-ink', paint.ink);
        element.style.setProperty('--bank-accent', paint.accent || paint.ink);
        element.setAttribute('aria-label', (onOpen ? 'Открыть карту ' : '') + (card.cardName || card.name));
        const logo =
          typeof carouselCardLogoMarkup === 'function'
            ? carouselCardLogoMarkup(card)
            : `<span class="carousel-card-logo" aria-hidden="true">${escapeHtml((card.cardName || card.name || '?').charAt(0))}</span>`;
        element.innerHTML = `<span class="carousel-card-content"><span class="carousel-card-top"><span><span class="carousel-card-bank">${escapeHtml(card.cardName || card.name)}</span><span class="carousel-card-type">${card.kind === 'manual' ? 'Моя карта' : 'Карта в кошельке'}</span></span>${logo}</span><span class="carousel-card-number-row"><span class="carousel-card-chip" aria-hidden="true"></span><span class="carousel-card-number" aria-hidden="true">•••• 0000</span></span></span>`;
        track.append(element);
      });
      applyCarouselTransforms();
    }

    function bindCarousel() {
      const carousel = root;
      carousel.addEventListener('click', carouselTap);
      carousel.addEventListener('pointerdown', carouselPointerDown);
      carousel.addEventListener('pointermove', carouselPointerMove);
      carousel.addEventListener('pointerup', carouselPointerUp);
      carousel.addEventListener('pointercancel', carouselPointerUp);
      carousel.addEventListener('keydown', (event) => {
        if (event.key === 'ArrowLeft') {
          event.preventDefault();
          carouselStep(-1);
        }
        if (event.key === 'ArrowRight') {
          event.preventDefault();
          carouselStep(1);
        }
      });
      new ResizeObserver(refresh).observe(root);
    }

    bindCarousel();
    return { render: renderCarousel, refresh, step: carouselStep, selected: selected };
  }

  window.mod = mod;
  window.createCardCarousel = createCardCarousel;
})();
