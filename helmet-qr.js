// "Helmet view on your phone": any element with data-helmet-qr opens a QR code for the helmet page.
// The code always points at the public https site: a phone cannot reach a laptop's localhost, and
// browsers only give camera access to secure pages.
(function () {
  const PUBLIC = 'https://jezero-marswalk-ashy.vercel.app';
  const url = (location.protocol === 'https:' && !/^(localhost|127\.)/.test(location.hostname) ? location.origin : PUBLIC) + '/helmet';
  const css = document.createElement('style');
  css.textContent = `#hqr{position:fixed;inset:0;z-index:7000;background:oklch(0.12 0.01 50 / .72);display:grid;place-items:center;padding:16px}
  #hqr[hidden]{display:none}
  #hqr .box{background:oklch(0.19 0.014 50);color:oklch(0.93 0.015 70);border:1px solid oklch(0.33 0.02 55);border-radius:12px;padding:26px 24px 22px;max-width:420px;width:100%;text-align:center;font-family:"Jost",system-ui,sans-serif}
  #hqr h2{font:400 19px/1.25 "Jost",system-ui,sans-serif;letter-spacing:.14em;text-transform:uppercase;margin:0 0 10px}
  #hqr p{font-size:15px;line-height:1.45;color:oklch(0.78 0.03 62);margin:0 0 16px}
  #hqr .code{background:#fff;padding:12px;border-radius:8px;display:inline-block;line-height:0}
  #hqr .url{font:10.5px/1.5 "Martian Mono",ui-monospace,monospace;color:oklch(0.93 0.015 70);word-break:break-all;margin:12px 0 16px;-webkit-user-select:all;user-select:all}
  #hqr button{font:500 14px "Jost",system-ui,sans-serif;letter-spacing:.06em;background:transparent;color:oklch(0.93 0.015 70);border:1px solid oklch(0.93 0.015 70 / .3);border-radius:8px;min-height:40px;padding:8px 16px;cursor:pointer;margin:0 4px}
  #hqr #hqrCopy{background:oklch(0.70 0.16 45);border-color:oklch(0.70 0.16 45);color:oklch(0.18 0.02 50);font-weight:600}
  #hqr button:hover{border-color:oklch(0.93 0.015 70 / .6)}
  #hqr button:focus-visible{outline:2px solid oklch(0.95 0.012 230);outline-offset:3px}`;
  document.head.appendChild(css);
  const wrap = document.createElement('div'); wrap.id = 'hqr'; wrap.hidden = true;
  wrap.setAttribute('role', 'dialog'); wrap.setAttribute('aria-modal', 'true'); wrap.setAttribute('aria-label', 'Helmet view on your phone');
  wrap.innerHTML = `<div class="box"><h2>Helmet view on your phone</h2>
    <p>Scan with your phone camera, then turn the phone sideways. The rear camera becomes the visor and the terrain model reads the ground ahead.</p>
    <div class="code" id="hqrCode"></div><div class="url">${url}</div>
    <button type="button" id="hqrCopy">Copy link</button><button type="button" id="hqrClose">Close</button></div>`;
  document.body.appendChild(wrap);
  let made = false;
  function open() {
    wrap.hidden = false; document.getElementById('hqrClose').focus();
    if (made) return;
    const draw = () => { new QRCode(document.getElementById('hqrCode'), { text: url, width: 200, height: 200, correctLevel: QRCode.CorrectLevel.M }); made = true; };
    if (window.QRCode) return draw();
    const s = document.createElement('script'); s.src = 'https://cdnjs.cloudflare.com/ajax/libs/qrcodejs/1.0.0/qrcode.min.js';
    s.onload = draw; s.onerror = () => { document.getElementById('hqrCode').outerHTML = '<p>The QR code could not load. Use the link below.</p>'; };
    document.head.appendChild(s);
  }
  const close = () => { wrap.hidden = true; };
  document.getElementById('hqrClose').onclick = close;
  wrap.addEventListener('click', e => { if (e.target === wrap) close(); });
  document.addEventListener('keydown', e => { if (e.key === 'Escape' && !wrap.hidden) close(); });
  document.getElementById('hqrCopy').onclick = async e => {
    try { await navigator.clipboard.writeText(url); e.target.textContent = 'Copied'; } catch (_) { e.target.textContent = 'Select the link above'; }
  };
  document.addEventListener('click', e => { const t = e.target.closest && e.target.closest('[data-helmet-qr]'); if (t) { e.preventDefault(); open(); } });
})();
