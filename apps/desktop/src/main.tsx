import '@fontsource-variable/inter';
import '@fontsource-variable/jetbrains-mono';
import './styles/global.css';

import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';

import { App } from './App';
import { consumePairingLink } from './core/api/session';

// A phone opened from the pairing QR code (`…/#pair=<token>`): keep the token,
// clean the address bar, then connect with it.
consumePairingLink();

const root = document.getElementById('root');
if (!root) throw new Error('Missing #root element');

createRoot(root).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
