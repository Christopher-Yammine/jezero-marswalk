// "Helmet view on your phone": any element with data-helmet-qr opens a QR code for the helmet page.
// The code always points at the public https site: a phone cannot reach a laptop's localhost, and
// browsers only give camera access to secure pages.
(function () {
  const PUBLIC = 'https://jezero-marswalk-ashy.vercel.app';
  const url = (location.protocol === 'https:' && !/^(localhost|127\.)/.test(location.hostname) ? location.origin : PUBLIC) + '/helmet';
  const css = document.createElement('style');
  css.textContent = `#hqr{position:fixed;inset:0;z-index:7000;background:rgba(0,0,0,.6);display:grid;place-items:center;padding:16px}
  #hqr[hidden]{display:none}
  #hqr .box{background:#1f1b16;color:#efe7dc;border:1px solid #3a322a;border-radius:10px;padding:18px;max-width:340px;width:100%;text-align:center;font-family:"IBM Plex Sans",system-ui,sans-serif}
  #hqr h2{font:700 18px "Archivo",system-ui,sans-serif;margin:0 0 6px}
  #hqr p{font-size:13px;color:#a3978a;margin:0 0 12px}
  #hqr .code{background:#fff;padding:12px;border-radius:8px;display:inline-block;line-height:0}
  #hqr .url{font:12px "IBM Plex Mono",monospace;color:#efe7dc;word-break:break-all;margin:10px 0 12px;user-select:all}
  #hqr button{font:600 13px "IBM Plex Sans",system-ui,sans-serif;background:transparent;color:#efe7dc;border:1px solid #3a322a;border-radius:6px;padding:7px 12px;cursor:pointer;margin:0 4px}
  #hqr button:focus-visible{outline:2px solid #e5b64a;outline-offset:2px}`;
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
