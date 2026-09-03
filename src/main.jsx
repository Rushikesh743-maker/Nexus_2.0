import React from 'react';
import ReactDOM from 'react-dom/client';

/* UI face — geometric, characterful, legible down to 11px. */
import '@fontsource-variable/instrument-sans';
/* Display face — editorial, used only for page titles and the wordmark. */
import '@fontsource/instrument-serif/400.css';
/* Figures. Every number in this product is evidence, so it gets its own face. */
import '@fontsource-variable/jetbrains-mono';
/* Devanagari coverage: the corpus carries names in both scripts. */
import '@fontsource-variable/noto-sans-devanagari';

import './index.css';
import App from './App';

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);
