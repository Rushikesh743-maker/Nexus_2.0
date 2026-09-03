import React from 'react';
import ReactDOM from 'react-dom/client';

/*
 * Typography matches the reference investigator console: IBM Plex Sans for
 * body copy, IBM Plex Mono for every label, heading, figure and key hint.
 * The mono is not decoration — it is what gives the interface its instrument
 * character, and it keeps columns of scores and hashes aligned.
 */
import '@fontsource-variable/ibm-plex-sans';
import '@fontsource/ibm-plex-mono/400.css';
import '@fontsource/ibm-plex-mono/500.css';
import '@fontsource/ibm-plex-mono/600.css';
/* Devanagari coverage: the corpus carries names in both scripts. */
import '@fontsource-variable/noto-sans-devanagari';

import './index.css';
import App from './App';

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);
