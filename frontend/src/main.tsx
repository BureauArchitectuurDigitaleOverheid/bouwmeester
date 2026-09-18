import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
// Registers the nldd-* custom elements we use. The stylesheet is imported from
// index.css so the cascade order relative to the Tailwind bridge stays explicit.
import './components/nldd/register';
import App from './App';
import './index.css';

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
