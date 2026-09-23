import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';

import { PlaceholderScreen } from './screens/PlaceholderScreen';
import './styles/global.css';

const root = document.getElementById('root');
if (!root) throw new Error('Root element #root not found');

createRoot(root).render(
  <StrictMode>
    <PlaceholderScreen />
  </StrictMode>,
);
