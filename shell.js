// Shared app shell for the Marswalk tool pages (plan, identify, 3d, helmet):
// one top bar with the same four destinations everywhere, and the landing page's type and colour.
// Load it in <head> so the layout offset is in place before the page draws.
(function () {
  const page = (location.pathname.split('/').pop() || 'index').replace(/\.html$/, '') || 'index';
  const H = 48, root = document.documentElement; root.dataset.mw = page;
  const font = document.createElement('link'); font.rel = 'stylesheet';
  font.href = 'https://fonts.googleapis.com/css2?family=Jost:wght@400;500;600&family=Martian+Mono:wght@400;500&display=swap';
  const css = document.createElement('style');
  css.textContent = `
:root{--mwbar:${H}px;
  --bg:oklch(0.16 0.012 50);--rail:oklch(0.19 0.014 50);--panel:oklch(0.225 0.016 50);--fg:oklch(0.93 0.015 70);--mute:oklch(0.74 0.03 62);--line:oklch(0.33 0.02 55);
  --rust:oklch(0.70 0.16 45);--rust-soft:oklch(0.30 0.07 40);--suit:oklch(0.95 0.012 230);
  --display:"Jost",system-ui,sans-serif}
h1{font-weight:500;letter-spacing:.03em}
.eyebrow{font-family:"Martian Mono",ui-monospace,monospace;font-size:10.5px;letter-spacing:.12em}
#mwbar{position:fixed;top:0;left:0;right:0;height:${H}px;z-index:6500;display:flex;align-items:center;justify-content:space-between;gap:16px;
  padding:0 max(16px,env(safe-area-inset-right)) 0 max(16px,env(safe-area-inset-left));background:oklch(0.16 0.012 50 / .94);border-bottom:1px solid oklch(0.93 0.015 70 / .14);
  font-family:"Jost",system-ui,sans-serif;-webkit-user-select:none;user-select:none}
#mwbar a{text-decoration:none;color:oklch(0.74 0.03 62)}
#mwbar .mark{font-family:"Martian Mono",ui-monospace,monospace;font-size:11px;letter-spacing:.14em;text-transform:uppercase;color:oklch(0.93 0.015 70);white-space:nowrap}
#mwbar nav{display:flex;gap:clamp(14px,2.4vw,34px);overflow-x:auto;scrollbar-width:none}
#mwbar nav::-webkit-scrollbar{display:none}
#mwbar nav a{font-size:13px;font-weight:500;letter-spacing:.12em;text-transform:uppercase;white-space:nowrap;padding:14px 0 12px;border-bottom:2px solid transparent;transition:color .25s}
#mwbar nav a:hover{color:oklch(0.93 0.015 70)}
#mwbar nav a[aria-current="page"]{color:oklch(0.95 0.012 230);border-bottom-color:oklch(0.95 0.012 230)}
#mwbar a:focus-visible{outline:2px solid oklch(0.95 0.012 230);outline-offset:3px;border-radius:2px}
#mwbar .s{display:none}
@media (max-width:640px){#mwbar .l{display:none}#mwbar .s{display:inline}#mwbar nav a{font-size:12px;letter-spacing:.08em}}
html[data-mw] body{padding-top:${H}px}
html[data-mw="plan"] #globe{top:${H}px}
html[data-mw="3d"] body,html[data-mw="helmet"] body{padding-top:0}
html[data-mw="3d"] #panel{top:${H + 16}px;max-height:calc(100% - ${H + 32}px);background:oklch(0.19 0.014 50 / .93)}
@media (max-width:700px){html[data-mw="3d"] #panel{top:auto;max-height:52vh}}
html[data-mw="helmet"].live #mwbar{display:none}
`;
  document.head.appendChild(font); document.head.appendChild(css);
  const ITEMS = [['plan', 'Plan a walk', 'Plan'], ['identify', 'Identify the ground', 'Identify'], ['3d', 'Mars in 3D', '3D'], ['helmet', 'Helmet view', 'Helmet']];
  function build() {
    const bar = document.createElement('header'); bar.id = 'mwbar';
    const qr = page !== 'helmet' && matchMedia('(pointer: fine)').matches;   // on a laptop, Helmet view offers the QR code for a phone
    bar.innerHTML = '<a class="mark" href="./" aria-label="Marswalk home">Marswalk</a><nav aria-label="Marswalk tools">' +
      ITEMS.map(([id, long, short]) => '<a href="' + id + '.html"' + (id === page ? ' aria-current="page"' : '') + (id === 'helmet' && qr ? ' data-helmet-qr' : '') +
        '><span class="l">' + long + '</span><span class="s">' + short + '</span></a>').join('') + '</nav>';
    document.body.insertBefore(bar, document.body.firstChild);
    if (qr && !document.querySelector('script[src*="helmet-qr"]')) { const s = document.createElement('script'); s.src = 'helmet-qr.js'; document.body.appendChild(s); }
    if (page === 'helmet') {   // the bar belongs to the start screen only; the live visor is full screen
      const st = document.getElementById('start'); if (!st) return;
      const sync = () => root.classList.toggle('live', st.hidden || getComputedStyle(st).display === 'none' || !st.isConnected);
      new MutationObserver(sync).observe(st, { attributes: true }); new MutationObserver(sync).observe(document.body, { childList: true }); sync();
    }
  }
  if (document.body) build(); else document.addEventListener('DOMContentLoaded', build);
})();
