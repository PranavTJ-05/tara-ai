/*!
 * Voice AI widget. Add to any website:
 *   <script src="https://YOUR-APP-HOST/widget.js" async></script>
 * Options (data- attributes on the script tag):
 *   data-url       app origin, defaults to where this script was loaded from
 *   data-position  "right" (default) or "left"
 *   data-label     accessible name of the launcher, default "Talk to our assistant"
 * JS API: window.VoiceAI.open() / close() / toggle()
 * The assistant runs inside an iframe, so it can't touch (or be styled by) the host page.
 */
(function () {
  if (window.VoiceAI) return;
  var tag = document.currentScript || document.querySelector('script[src*="widget.js"]');
  var base = ((tag && tag.dataset.url) || new URL(tag.src, location.href).origin).replace(/\/$/, "");
  var side = tag && tag.dataset.position === "left" ? "left" : "right";
  var label = (tag && tag.dataset.label) || "Talk to our assistant";

  var host = document.createElement("div");
  host.id = "voice-ai-widget";
  var root = host.attachShadow({ mode: "open" });
  root.innerHTML =
    "<style>" +
    ":host{all:initial}" +
    ".fab{position:fixed;bottom:20px;" + side + ":20px;z-index:2147483000;width:60px;height:60px;border-radius:50%;border:0;cursor:pointer;display:grid;place-items:center;" +
    "background:linear-gradient(135deg,#ecd48f,#d4af5f 55%,#a8832f);color:#2a1f05;box-shadow:0 12px 28px -8px rgba(10,47,44,.55),inset 0 1px 0 rgba(255,255,255,.55);transition:transform .15s}" +
    ".fab:hover{transform:scale(1.06)}.fab:focus-visible{outline:3px solid #17a394;outline-offset:3px}" +
    ".fab svg{width:26px;height:26px;fill:none;stroke:currentColor;stroke-width:2;stroke-linecap:round;stroke-linejoin:round}" +
    ".panel{position:fixed;bottom:92px;" + side + ":20px;z-index:2147483000;width:min(400px,calc(100vw - 32px));height:min(680px,calc(100dvh - 120px));" +
    "border-radius:22px;overflow:hidden;background:#edf1ef;box-shadow:0 30px 70px -18px rgba(4,22,20,.55),0 0 0 1px rgba(10,47,44,.12);" +
    "opacity:0;transform:translateY(12px) scale(.98);pointer-events:none;transition:opacity .18s,transform .18s}" +
    ".panel.open{opacity:1;transform:none;pointer-events:auto}" +
    "iframe{width:100%;height:100%;border:0;display:block}" +
    ".x{display:none;position:absolute;top:10px;right:10px;z-index:2;width:36px;height:36px;border-radius:50%;border:0;background:rgba(10,47,44,.85);color:#fff;cursor:pointer}" +
    ".x svg{width:18px;height:18px;fill:none;stroke:currentColor;stroke-width:2;stroke-linecap:round}" +
    "@media(max-width:520px){.panel{inset:0;width:100%;height:100%;border-radius:0;bottom:auto}.panel.open~.fab{display:none}.x{display:grid;place-items:center}}" +
    "@media(prefers-reduced-motion:reduce){.fab,.panel{transition:none}}" +
    "</style>" +
    '<div class="panel" role="dialog" aria-label="' + label + '"><button class="x" aria-label="Close"><svg viewBox="0 0 24 24"><path d="M6 6l12 12M18 6L6 18"/></svg></button></div>' +
    '<button class="fab" aria-label="' + label + '" aria-expanded="false"></button>';

  var panel = root.querySelector(".panel"), fab = root.querySelector(".fab"), closeBtn = root.querySelector(".x");
  var wave = '<svg viewBox="0 0 24 24"><path d="M5 10v4M9 6v12M13 3v18M17 8v8M21 11v2"/></svg>';
  var cross = '<svg viewBox="0 0 24 24"><path d="M6 6l12 12M18 6L6 18"/></svg>';
  fab.innerHTML = wave;
  var frame = null, isOpen = false;

  function set(open) {
    isOpen = open;
    if (open && !frame) {                                   // load the app only when first opened
      frame = document.createElement("iframe");
      frame.src = base + "/embed";
      frame.title = label;
      frame.allow = "microphone; autoplay";
      panel.appendChild(frame);
    }
    panel.classList.toggle("open", open);
    fab.innerHTML = open ? cross : wave;
    fab.setAttribute("aria-expanded", String(open));
  }
  fab.addEventListener("click", function () { set(!isOpen); });
  closeBtn.addEventListener("click", function () { set(false); });
  document.addEventListener("keydown", function (e) { if (e.key === "Escape" && isOpen) set(false); });

  window.VoiceAI = { open: function () { set(true); }, close: function () { set(false); }, toggle: function () { set(!isOpen); } };
  (document.body ? Promise.resolve() : new Promise(function (r) { document.addEventListener("DOMContentLoaded", r); }))
    .then(function () { document.body.appendChild(host); });
})();
