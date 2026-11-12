// Saint Seiya: Sacro Imperio — motore avventura grafica (prototipo)
// Schermo logico 320x240: scena 320x180 + pannello comandi 60 px.
(() => {
"use strict";
const W = 320, H = 240, SH = 180, K = 320 / 1376;
const FONT = '8px "Tiny5", monospace';
const cv = document.getElementById("schermo");
const ctx = cv.getContext("2d");
ctx.imageSmoothingEnabled = false;

const COL = {
  oro: "#c9a227", oroChiaro: "#f3d36b", navy: "#0e1020", navy2: "#171a30",
  testo: "#f4e7b2", dim: "#8d86a8", ciano: "#6fd3ff", verde: "#8fe08a", rosso: "#ff5a5a"
};
const VERBI = [["guarda","Guarda"],["parla","Parla"],["usa","Usa"],["prendi","Prendi"],
               ["apri","Apri"],["chiudi","Chiudi"],["spingi","Spingi"],["tira","Tira"]];
const NOMI_VERBO = Object.fromEntries(VERBI);
const DEF = {
  guarda: "Non c'è niente di particolare.", parla: "Non mi risponde.",
  usa: "Non saprei come usarlo.", prendi: "Non mi serve.", apri: "Non si apre.",
  chiudi: "È già chiuso.", spingi: "Non si muove.", tira: "Non si muove."
};

// ---------- stato ----------
const S = {
  scena: null, px: 0, py: 0, verso: 1, costume: "civile",
  cosmo: 120, cosmoMax: 163, stamina: 80, staminaMax: 100, settimana: 12, anno: 1,
  verbo: null, mouse: { x: 0, y: 0, dentro: false }, hover: null,
  camm: null, camminaT: 0, anim: null, timer: [],
  testo: null, coda: [], fade: { v: 0, dir: 0, cb: null }, banner: { s: "", t: 0 },
  debug: false, caricato: false, occupato: false
};

// ---------- conversione dati scene ----------
const MONDO = {};
for (const [id, d] of Object.entries(SCENE)) {
  const conv = p => [p[0] * K, p[1] * K];
  MONDO[id] = {
    id, nome: d.nome, img: d.img,
    walk: d.walk.map(conv),
    scala: [d.scala[0] * K, d.scala[1], d.scala[2] * K, d.scala[3]],
    hotspot: d.hotspot.map(h => ({
      ...h, rl: h.r.map(v => v * K),
      appr: h.approach ? conv(h.approach) : null,
      exitL: h.exit ? { a: h.exit.a, pos: conv(h.exit.pos) } : null
    }))
  };
}

// ---------- caricamento ----------
const IMG = { scene: {}, sprite: {} };
function carica(src) {
  return new Promise((ok, ko) => { const i = new Image(); i.onload = () => ok(i); i.onerror = () => ko(src); i.src = src; });
}
async function caricaTutto() {
  disegnaCaricamento("Caricamento…");
  try { await document.fonts.load(FONT); } catch (e) {}
  const lavori = [];
  for (const sc of Object.values(MONDO)) lavori.push(carica("assets/scene/" + sc.img).then(i => IMG.scene[sc.id] = i));
  for (const nome of ["civile", "pegaso"]) {
    lavori.push(fetch(`assets/sprite/${nome}/atlante.json`).then(r => r.json()).then(async at => {
      const frames = await Promise.all(at.fotogrammi.map(f => carica(`assets/sprite/${nome}/${f.file}`).then(img => ({ img, w: f.w, h: f.h, pivot: f.pivot }))));
      IMG.sprite[nome] = { pose: at.pose, frames };
    }));
  }
  await Promise.all(lavori);
}
function disegnaCaricamento(t) {
  ctx.fillStyle = "#05060d"; ctx.fillRect(0, 0, W, H);
  ctx.font = FONT; ctx.fillStyle = COL.testo; ctx.textBaseline = "top"; ctx.fillText(t, 118, 112);
}

// ---------- geometria ----------
function inPoly(x, y, P) {
  let d = false;
  for (let i = 0, j = P.length - 1; i < P.length; j = i++) {
    const [xi, yi] = P[i], [xj, yj] = P[j];
    if ((yi > y) !== (yj > y) && x < (xj - xi) * (y - yi) / (yj - yi) + xi) d = !d;
  }
  return d;
}
function vicino(x, y, P) {
  if (inPoly(x, y, P)) return [x, y];
  let best = null, bd = 1e9;
  for (let i = 0; i < P.length; i++) {
    const a = P[i], b = P[(i + 1) % P.length];
    const dx = b[0] - a[0], dy = b[1] - a[1];
    let t = ((x - a[0]) * dx + (y - a[1]) * dy) / (dx * dx + dy * dy); t = Math.max(0, Math.min(1, t));
    const qx = a[0] + t * dx, qy = a[1] + t * dy, d = (qx - x) ** 2 + (qy - y) ** 2;
    if (d < bd) { bd = d; best = [qx, qy]; }
  }
  return best;
}
function scalaA(y) {
  const [yf, sf, yn, sn] = S.scena.scala;
  const t = Math.max(0, Math.min(1, (y - yf) / (yn - yf)));
  return sf + t * (sn - sf);
}
function hotspotA(x, y) {
  const L = S.scena.hotspot;
  for (let i = L.length - 1; i >= 0; i--) {
    const h = L[i], [rx, ry, rw, rh] = h.rl;
    if (x >= rx && x <= rx + rw && y >= ry && y <= ry + rh) {
      if (h.floor && !S.verbo) continue;
      return h;
    }
  }
  return null;
}

// ---------- scene ----------
function entraScena(id, pos, senzaBanner) {
  S.scena = MONDO[id];
  S.px = pos[0]; S.py = pos[1]; S.camm = null; S.hover = null;
  [S.px, S.py] = vicino(S.px, S.py, S.scena.walk);
  if (!senzaBanner) S.banner = { s: S.scena.nome, t: 2.4 };
  salva();
}
function vaiScena(ex) {
  S.occupato = true;
  S.fade = { v: 0, dir: 1, cb: () => { entraScena(ex.a, ex.pos); S.occupato = false; } };
}
function dissolvenza(cb) {
  S.occupato = true;
  S.fade = { v: 0, dir: 1, cb: () => { cb(); S.occupato = false; } };
}

// ---------- salvataggio locale ----------
function salva() {
  try {
    localStorage.setItem("ss_proto", JSON.stringify({ scena: S.scena.id, px: S.px, py: S.py, costume: S.costume,
      cosmo: S.cosmo, stamina: S.stamina, settimana: S.settimana, anno: S.anno }));
  } catch (e) {}
}
function leggi() {
  try {
    if (location.search.includes("nuovo")) { localStorage.removeItem("ss_proto"); return null; }
    return JSON.parse(localStorage.getItem("ss_proto") || "null");
  } catch (e) { return null; }
}

// ---------- testo / dialoghi ----------
function parla(s, chi) {
  (Array.isArray(s) ? s : [s]).forEach(x => S.coda.push({ s: x, chi: chi || "SEIYA" }));
  if (!S.testo) prossimoTesto();
}
function prossimoTesto() {
  const n = S.coda.shift();
  S.testo = n ? { s: n.s, chi: n.chi, t: 0 } : null;
}
function testoClick() {
  const t = S.testo; if (!t) return false;
  const tipo = t.s.length / 45;
  if (t.t < tipo) { t.t = tipo; return true; }
  prossimoTesto(); return true;
}
function dopo(sec, fn) { S.timer.push({ t: sec, fn }); }

// ---------- azioni ----------
function animazione(tipo, dur) { S.anim = { tipo, fino: now() + dur, t0: now() }; }
const now = () => performance.now() / 1000;

const EFFETTI = {
  __riposa__() {
    parla("Mi stendo sul letto e chiudo gli occhi.");
    dopo(1.6, () => dissolvenza(() => {
      S.stamina = S.staminaMax; S.cosmo = S.cosmoMax; S.settimana++;
      if (S.settimana > 52) { S.settimana = 1; S.anno++; }
      salva();
      parla("Mi sveglio riposato. Cosmo e forze sono al massimo.");
    }));
  },
  __armatura__() {
    if (S.costume === "civile") {
      S.costume = "pegaso"; animazione("carica", 1.4);
      parla(["Apro il baule. Dentro c'è la Pandora Box di Pegaso.", "L'armatura si ricompone su di me. Il Cosmo risponde!"]);
    } else {
      S.costume = "civile";
      parla("Ripongo l'armatura nel baule. Per oggi basta.");
    }
    salva();
  },
  __colpisci__() {
    if (S.stamina < 5) { parla("Sono troppo stanco per allenarmi."); return; }
    S.stamina = Math.max(0, S.stamina - 5); S.cosmo = Math.max(0, S.cosmo - 2);
    S.occupato = true;
    for (let k = 0; k < 3; k++) dopo(k * 0.45, () => animazione("attacco", 0.3));
    dopo(1.45, () => {
      S.occupato = false;
      parla(S.costume === "pegaso" ? "Fulmine di Pegasus! Il manichino è ridotto in pezzi." : "Colpisco il manichino. Non è male, per un principiante.");
    });
  },
  __pesi__() {
    if (S.stamina < 10) { parla("Sono troppo stanco per i pesi."); return; }
    S.stamina -= 10; parla("Sollevo i pesi. Sento i muscoli che bruciano.");
  },
  __carica__() {
    S.occupato = true; animazione("carica", 1.6);
    S.cosmo = Math.min(S.cosmoMax, S.cosmo + 8);
    dopo(1.7, () => { S.occupato = false; parla("Concentro il Cosmo. Lo sento crescere dentro di me."); });
  },
  __scalda__() {
    S.stamina = Math.min(S.staminaMax, S.stamina + 15);
    parla("Mi scaldo davanti al camino. Le forze tornano.");
  },
  __sfida__() {
    S.cosmo = Math.max(0, S.cosmo - 3);
    S.occupato = true;
    for (let k = 0; k < 2; k++) dopo(k * 0.45, () => animazione("attacco", 0.3));
    dopo(1.1, () => { S.occupato = false; parla("Qui si combatte per davvero. Per ora mi alleno a vuoto: gli scontri arriveranno presto."); });
  }
};

function camminaA(x, y, fine) {
  const [tx, ty] = vicino(x, y, S.scena.walk);
  S.camm = { tx, ty, fine: fine || null };
  if (Math.abs(tx - S.px) > 0.5) S.verso = tx >= S.px ? 1 : -1;
}
function puntoApproccio(h) {
  if (h.appr) return h.appr;
  const [x, y, w, hh] = h.rl;
  return [x + w / 2, y + hh];
}
function eseguiVerbo(h, v) {
  if (v === "guarda") {
    const [x] = h.rl; S.verso = (x + h.rl[2] / 2) >= S.px ? 1 : -1;
    parla(h.guarda || DEF.guarda); return;
  }
  const [ax, ay] = puntoApproccio(h);
  camminaA(ax, ay, () => azione(h, v));
}
function azione(h, v) {
  const [x, , w] = h.rl; S.verso = (x + w / 2) >= S.px ? 1 : -1;
  if (h.exitL && ["vai", "apri", "spingi", "usa"].includes(v)) { vaiScena(h.exitL); return; }
  let r = h[v];
  if (typeof r === "string" && r.startsWith("__")) { EFFETTI[r](); return; }
  parla(r || DEF[v]);
}

// ---------- input ----------
const PANNELLO = {
  verbi: VERBI.map((v, i) => ({ id: v[0], nome: v[1], x: 8 + Math.floor(i / 4) * 50, y: 184 + (i % 4) * 13, w: 48, h: 12 }))
};
function posMouse(e) {
  const r = cv.getBoundingClientRect();
  return { x: (e.clientX - r.left) * W / r.width, y: (e.clientY - r.top) * H / r.height };
}
cv.addEventListener("contextmenu", e => e.preventDefault());
cv.addEventListener("pointermove", e => {
  const p = posMouse(e); S.mouse = { x: p.x, y: p.y, dentro: true };
});
cv.addEventListener("pointerleave", () => { S.mouse.dentro = false; });
cv.addEventListener("pointerdown", e => {
  e.preventDefault();
  if (!S.caricato) return;
  const p = posMouse(e); S.mouse = { x: p.x, y: p.y, dentro: true };
  if (e.button === 2) { S.verbo = null; return; }
  if (S.fade.dir !== 0) return;
  if (S.debug) console.log("click", Math.round(p.x / K), Math.round(p.y / K), "(sorgente)", p.x.toFixed(1), p.y.toFixed(1));
  if (testoClick()) return;
  if (S.occupato) return;
  if (p.y < SH) {
    const h = hotspotA(p.x, p.y);
    if (h) { const v = S.verbo || (h.exitL ? "vai" : "guarda"); S.verbo = null; eseguiVerbo(h, v); }
    else { S.verbo = null; camminaA(p.x, p.y); }
  } else {
    for (const b of PANNELLO.verbi) {
      if (p.x >= b.x && p.x <= b.x + b.w && p.y >= b.y && p.y <= b.y + b.h) { S.verbo = S.verbo === b.id ? null : b.id; return; }
    }
  }
});
addEventListener("keydown", e => { if (e.key === "d" || e.key === "D") S.debug = !S.debug; });

function adattaSchermo() {
  const iw = innerWidth, ih = innerHeight;
  let s = Math.floor(Math.min(iw / W, ih / H));
  if (s < 1) s = Math.min(iw / W, ih / H); // schermi molto piccoli: scala frazionaria
  cv.style.width = Math.round(W * s) + "px"; cv.style.height = Math.round(H * s) + "px";
}
addEventListener("resize", adattaSchermo); adattaSchermo();

// ---------- aggiornamento ----------
function sequenzaCamminata(set) {
  const fermo = set.pose.fermo[0], c = set.pose.cammina;
  return c.length >= 4 ? c : [fermo, c[0], fermo, c[1]];
}
function frameCorrente() {
  const set = IMG.sprite[S.costume], t = now();
  if (S.anim && t < S.anim.fino) {
    const L = set.pose[S.anim.tipo] || set.pose.fermo;
    return set.frames[L[Math.floor((t - S.anim.t0) * 6) % L.length]];
  }
  if (S.camm) { const seq = sequenzaCamminata(set); return set.frames[seq[Math.floor(S.camminaT * 8) % seq.length]]; }
  return set.frames[set.pose.fermo[0]];
}
function aggiorna(dt) {
  if (S.fade.dir !== 0) {
    S.fade.v += S.fade.dir * dt * 4.2;
    if (S.fade.dir > 0 && S.fade.v >= 1) { S.fade.v = 1; const cb = S.fade.cb; S.fade.dir = -1; S.fade.cb = null; if (cb) cb(); }
    else if (S.fade.dir < 0 && S.fade.v <= 0) { S.fade.v = 0; S.fade.dir = 0; }
  }
  for (let i = S.timer.length - 1; i >= 0; i--) { S.timer[i].t -= dt; if (S.timer[i].t <= 0) { const f = S.timer[i].fn; S.timer.splice(i, 1); f(); } }
  if (S.camm) {
    const sc = scalaA(S.py), v = Math.max(34, 85 * sc), c = S.camm;
    const dx = c.tx - S.px, dy = c.ty - S.py, d = Math.hypot(dx, dy), passo = v * dt;
    S.camminaT += dt;
    if (d <= passo) { S.px = c.tx; S.py = c.ty; S.camm = null; S.camminaT = 0; if (c.fine) c.fine(); }
    else { S.px += dx / d * passo; S.py += dy / d * passo; if (Math.abs(dx) > 0.3) S.verso = dx >= 0 ? 1 : -1; }
  }
  if (S.testo) {
    S.testo.t += dt;
    const tipo = S.testo.s.length / 45, tot = tipo + 1.1 + S.testo.s.length * 0.03;
    if (S.testo.t > tot) prossimoTesto();
  }
  if (S.banner.t > 0) S.banner.t -= dt;
  // hover
  S.hover = null;
  if (S.mouse.dentro && S.mouse.y < SH && !S.occupato && S.fade.dir === 0) S.hover = hotspotA(S.mouse.x, S.mouse.y);
}

// ---------- disegno ----------
function box(x, y, w, h, fill) {
  ctx.fillStyle = fill || COL.navy; ctx.fillRect(x, y, w, h);
  ctx.fillStyle = COL.oro;
  ctx.fillRect(x, y, w, 1); ctx.fillRect(x, y + h - 1, w, 1); ctx.fillRect(x, y, 1, h); ctx.fillRect(x + w - 1, y, 1, h);
}
function testo(s, x, y, col) { ctx.fillStyle = col || COL.testo; ctx.fillText(s, Math.round(x), Math.round(y)); }
function righe(s, maxw) {
  const out = []; let cur = "";
  for (const w of s.split(" ")) {
    const prova = cur ? cur + " " + w : w;
    if (ctx.measureText(prova).width <= maxw) cur = prova; else { if (cur) out.push(cur); cur = w; }
  }
  if (cur) out.push(cur); return out;
}
function barra(x, y, w, h, frac, c1, c2) {
  ctx.fillStyle = "#07080f"; ctx.fillRect(x, y, w, h);
  const n = Math.floor(w / 6), pieni = Math.round(n * Math.max(0, Math.min(1, frac)));
  for (let i = 0; i < n; i++) { ctx.fillStyle = i < pieni ? (i < n / 2 ? c1 : c2) : "#1b1d33"; ctx.fillRect(x + 1 + i * 6, y + 1, 5, h - 2); }
}
function disegnaSprite() {
  const f = frameCorrente(), s = scalaA(S.py);
  const dw = Math.round(f.w * s), dh = Math.round(f.h * s);
  ctx.fillStyle = "rgba(0,0,0,.28)"; ctx.beginPath(); ctx.ellipse(Math.round(S.px), Math.round(S.py), 9 * s + 2, 2.2 * s + 0.6, 0, 0, 7); ctx.fill();
  ctx.save(); ctx.translate(Math.round(S.px), Math.round(S.py)); ctx.scale(S.verso, 1);
  ctx.drawImage(f.img, -Math.round(f.pivot[0] * s), -dh, dw, dh); ctx.restore();
}
function disegnaHUD() {
  box(4, 4, 128, 27); ctx.font = FONT;
  testo("COSMO", 9, 7, COL.ciano); barra(46, 7, 80, 7, S.cosmo / S.cosmoMax, "#6a5acd", "#b9b4f2");
  testo("STAMINA", 9, 18, COL.verde); barra(46, 18, 80, 7, S.stamina / S.staminaMax, "#3da35d", "#a6e68a");
  box(238, 4, 78, 27);
  ctx.fillStyle = COL.ciano; ctx.fillRect(245, 11, 12, 2); ctx.fillRect(246, 14, 10, 1);
  for (let i = 0; i < 4; i++) ctx.fillRect(247 + i * 3, 15, 2, 9);
  ctx.fillRect(245, 24, 12, 2);
  testo("SETT. " + S.settimana, 263, 8, COL.testo); testo("ANNO " + S.anno, 263, 18, COL.dim);
}
function disegnaPannello() {
  ctx.fillStyle = COL.navy; ctx.fillRect(0, SH, W, H - SH);
  ctx.fillStyle = COL.oro; ctx.fillRect(0, SH, W, 1);
  ctx.font = FONT;
  for (const b of PANNELLO.verbi) {
    const sel = S.verbo === b.id, ov = S.mouse.dentro && S.mouse.x >= b.x && S.mouse.x <= b.x + b.w && S.mouse.y >= b.y && S.mouse.y <= b.y + b.h;
    ctx.fillStyle = sel ? "#3a3016" : COL.navy2; ctx.fillRect(b.x, b.y, b.w, b.h);
    testo(b.nome, b.x + 4, b.y + 3, sel ? COL.oroChiaro : (ov ? COL.oroChiaro : COL.testo));
  }
  // finestra dialogo
  box(110, 183, 124, 54);
  let intest = "", corpo = "", col = COL.dim;
  if (S.testo) {
    intest = S.testo.chi + ":"; col = COL.oroChiaro;
    const n = Math.floor(S.testo.t * 45); corpo = S.testo.s.slice(0, n);
  } else {
    const h = S.hover;
    if (S.verbo) intest = NOMI_VERBO[S.verbo] + (h ? " " + h.nome : "");
    else if (h) intest = (h.exitL ? "Vai a " : "Guarda ") + h.nome;
    col = COL.ciano;
  }
  testo(intest, 115, 187, col);
  if (corpo) righe(corpo, 114).slice(0, 5).forEach((r, i) => testo(r, 115, 197 + i * 8, COL.testo));
  // inventario
  box(240, 183, 76, 54);
  testo("INVENTARIO", 252, 186, COL.dim);
  for (let i = 0; i < 2; i++) { ctx.fillStyle = COL.navy2; ctx.fillRect(246 + i * 28, 199, 24, 24); testo("+", 256 + i * 28, 207, "#3b3a5a"); }
  ctx.fillStyle = COL.oro; ctx.fillRect(303, 202, 7, 2); ctx.fillRect(304, 200, 5, 2); ctx.fillRect(305, 198, 3, 2);
  ctx.fillRect(303, 218, 7, 2); ctx.fillRect(304, 220, 5, 2); ctx.fillRect(305, 222, 3, 2);
}
function disegnaCursore() {
  if (!S.mouse.dentro || S.fade.dir !== 0) return;
  const x = Math.round(S.mouse.x), y = Math.round(S.mouse.y);
  ctx.fillStyle = S.hover ? COL.oroChiaro : COL.rosso;
  ctx.fillRect(x - 4, y, 3, 1); ctx.fillRect(x + 2, y, 3, 1); ctx.fillRect(x, y - 4, 1, 3); ctx.fillRect(x, y + 2, 1, 3);
  ctx.fillRect(x, y, 1, 1);
}
function disegnaDebug() {
  ctx.strokeStyle = "#00ffff"; ctx.lineWidth = 1; ctx.beginPath();
  S.scena.walk.forEach((p, i) => i ? ctx.lineTo(p[0], p[1]) : ctx.moveTo(p[0], p[1])); ctx.closePath(); ctx.stroke();
  for (const h of S.scena.hotspot) {
    ctx.strokeStyle = h.exitL ? "#ffdd00" : (h.floor ? "#8888ff" : "#ff3030"); ctx.strokeRect(h.rl[0] + .5, h.rl[1] + .5, h.rl[2], h.rl[3]);
  }
  ctx.font = FONT; testo(`src ${Math.round(S.mouse.x / K)},${Math.round(S.mouse.y / K)}  [D=debug]`, 140, 170, "#ffffff");
}
function disegna() {
  ctx.fillStyle = "#000"; ctx.fillRect(0, 0, W, H);
  ctx.font = FONT; ctx.textBaseline = "top";
  ctx.drawImage(IMG.scene[S.scena.id], 0, 0, 320, SH);
  disegnaSprite();
  disegnaHUD();
  if (S.banner.t > 0) {
    const a = Math.min(1, S.banner.t * 2); ctx.globalAlpha = a;
    const w = ctx.measureText(S.banner.s).width + 12; box(Math.round((W - w) / 2), 36, Math.round(w), 13);
    testo(S.banner.s, (W - w) / 2 + 6, 40, COL.oroChiaro); ctx.globalAlpha = 1;
  }
  if (S.debug) disegnaDebug();
  disegnaPannello();
  ctx.fillStyle = COL.oro; ctx.fillRect(0, 0, W, 1); ctx.fillRect(0, H - 1, W, 1); ctx.fillRect(0, 0, 1, H); ctx.fillRect(W - 1, 0, 1, H);
  if (S.fade.v > 0) { ctx.fillStyle = `rgba(0,0,0,${S.fade.v})`; ctx.fillRect(0, 0, W, H); }
  disegnaCursore();
}

// ---------- avvio ----------
let ultimo = 0;
function ciclo(t) {
  const dt = Math.min(0.05, (t - ultimo) / 1000 || 0); ultimo = t;
  aggiorna(dt); disegna(); requestAnimationFrame(ciclo);
}
caricaTutto().then(() => {
  const s = leggi();
  if (s && MONDO[s.scena]) {
    Object.assign(S, { costume: s.costume, cosmo: s.cosmo, stamina: s.stamina, settimana: s.settimana, anno: s.anno });
    entraScena(s.scena, [s.px, s.py]);
  } else {
    entraScena(PARTENZA.scena, PARTENZA.pos.map(v => v * K));
    parla("La piazza del Grande Tempio. Qui comincia il mio addestramento.");
  }
  S.caricato = true; requestAnimationFrame(ciclo);
}).catch(e => { disegnaCaricamento("Errore di caricamento: " + e); console.error(e); });

// hook per i test automatici
window.__gioco = { S, MONDO, K, vaiScena, entraScena };
})();
