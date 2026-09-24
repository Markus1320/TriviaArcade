import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';

// The pixel font is bundled with the app (OFL licensed), not loaded from Google.
import '@fontsource/press-start-2p/latin-400.css';
import '@fontsource/press-start-2p/latin-ext-400.css';

import { App } from './App';
import { SoundProvider } from './audio/SoundProvider';
import { SoundToggle } from './components/SoundToggle';
import './styles/global.css';

const root = document.getElementById('root');
if (!root) throw new Error('Root element #root not found');

createRoot(root).render(
  <StrictMode>
    <SoundProvider>
      <SoundToggle />
      <App />
    </SoundProvider>
  </StrictMode>,
);
