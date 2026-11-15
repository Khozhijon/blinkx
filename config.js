// Where the Blink X API lives.
//   ""  -> same origin: the FastAPI server also serves this page (local runs and the Render deploy).
//   When this folder is hosted as a plain static site (GitHub Pages), the API is the Render service.
//   The saved examples work even with no backend at all.
window.BLINKX_API = /\.github\.io$/.test(location.hostname) ? "https://blinkx-khofra.onrender.com" : "";
