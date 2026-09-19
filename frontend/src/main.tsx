import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
// Registers the nldd-* custom elements we use. The design system's own
// stylesheet is imported from index.css, so the cascade order against our
// utilities stays where it can be read in one place.
import './components/nldd/register';
import App from './App';
import './index.css';

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
