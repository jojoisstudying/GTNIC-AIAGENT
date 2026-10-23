/* Auto-fit teks + laporan layout. Dipanggil renderer lewat window.__run(). */
(function () {
  function rectOf(el) {
    const r = el.getBoundingClientRect();
    return { x: r.left, y: r.top, w: r.width, h: r.height };
  }

  // Blok judul: tiap baris .fl diskalakan agar lebar = lebar kotak (skala tipografi ekstrem).
  function fitLines(box) {
    const maxF = +box.dataset.maxFont || 260;
    const maxH = +box.dataset.maxHeight || 0;
    const W = box.clientWidth;
    const lines = Array.from(box.querySelectorAll('.fl'));
    let sizes = lines.map((l) => {
      l.style.fontSize = '100px';
      const w = l.getBoundingClientRect().width || 1;
      return Math.min(maxF, (W / w) * 100);
    });
    const apply = () => lines.forEach((l, i) => { l.style.fontSize = sizes[i].toFixed(2) + 'px'; });
    apply();
    // Ukur ulang tinggi nyata (marker/em bisa menambah tinggi baris) dan skalakan sampai muat.
    for (let k = 0; maxH && k < 5; k++) {
      const h = box.getBoundingClientRect().height;
      if (h <= maxH + 0.5) break;
      const f = maxH / h;
      sizes = sizes.map((s) => s * f);
      apply();
    }
    box._lineSizes = sizes;
    box._fits = lines.every((l) => l.getBoundingClientRect().width <= W + 1) &&
      (!maxH || box.getBoundingClientRect().height <= maxH + 1);
  }

  // Paragraf: kecilkan bertahap sampai tinggi muat.
  function fitText(el) {
    const maxF = +el.dataset.maxFont || 40;
    const minF = +el.dataset.minFont || 24;
    const maxH = +el.dataset.maxHeight || 0;
    let size = maxF;
    el.style.fontSize = size + 'px';
    const over = () => (maxH && el.getBoundingClientRect().height > maxH + 1) || el.scrollWidth > el.clientWidth + 1;
    while (over() && size > minF) { size -= 2; el.style.fontSize = size + 'px'; }
    el._fits = !over();
    el._fontPx = size;
  }

  // Kata dekoratif: lebar target tertentu (boleh keluar kanvas).
  function fitWidth(el) {
    const target = +el.dataset.fitwidth || 1000;
    const maxF = +el.dataset.maxFont || 560;
    const minF = +el.dataset.minFont || 200;
    el.style.fontSize = '100px';
    const w = el.getBoundingClientRect().width || 1;
    el.style.fontSize = Math.max(minF, Math.min(maxF, (target / w) * 100)).toFixed(1) + 'px';
  }

  function runsOf(el) {
    const runs = [];
    const tw = document.createTreeWalker(el, NodeFilter.SHOW_TEXT);
    let n;
    while ((n = tw.nextNode())) {
      if (!n.nodeValue.trim()) continue;
      const range = document.createRange();
      range.selectNodeContents(n);
      const cs = getComputedStyle(n.parentElement);
      for (const r of range.getClientRects()) {
        if (r.width < 1) continue;
        runs.push({ x: r.left, y: r.top, w: r.width, h: r.height, color: cs.color, font_px: parseFloat(cs.fontSize) });
      }
    }
    return runs;
  }

  function collect() {
    const out = [];
    document.querySelectorAll('[data-q]').forEach((el) => {
      const kind = el.dataset.kind || 'text';
      const base = {
        slot: el.dataset.slot || null, kind,
        min_font: +el.dataset.minFont || 0,
        bleed: el.hasAttribute('data-bleed'),
        behind: el.hasAttribute('data-behind'),
      };
      if (el.hasAttribute('data-fitlines')) {
        const lines = Array.from(el.querySelectorAll('.fl'));
        lines.forEach((l, i) => {
          out.push(Object.assign({}, base, {
            id: el.dataset.q + '#' + (i + 1), bbox: rectOf(l),
            font_px: el._lineSizes[i], fits: el._fits, runs: runsOf(l),
          }));
        });
        return;
      }
      out.push(Object.assign({}, base, {
        id: el.dataset.q, bbox: rectOf(el),
        font_px: el._fontPx || parseFloat(getComputedStyle(el).fontSize),
        fits: el._fits !== undefined ? el._fits : el.scrollWidth <= el.clientWidth + 1,
        runs: runsOf(el),
      }));
    });
    return out;
  }

  window.__run = async function () {
    await document.fonts.ready;
    document.querySelectorAll('[data-fitwidth]').forEach(fitWidth);
    document.querySelectorAll('[data-fitlines]').forEach(fitLines);
    document.querySelectorAll('[data-autofit]').forEach(fitText);
    // Grup font: elemen sekelompok memakai ukuran terkecil agar tampak seragam.
    const groups = {};
    document.querySelectorAll('[data-fit-group]').forEach((el) => { (groups[el.dataset.fitGroup] = groups[el.dataset.fitGroup] || []).push(el); });
    Object.values(groups).forEach((els) => {
      const size = Math.min.apply(null, els.map((e) => e._fontPx));
      els.forEach((e) => { e.style.fontSize = size + 'px'; e._fontPx = size; });
    });
    return collect();
  };
})();
