import React from 'react';
import ReactDOM from 'react-dom/client';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import App from './App';
import { applyTheme, useUi } from './state';
import './styles/base.css';

applyTheme(useUi.getState().theme);
const systemTheme = window.matchMedia('(prefers-color-scheme: dark)');
systemTheme.addEventListener('change', () => {
  if (useUi.getState().theme === 'system') applyTheme('system');
});
const queryClient = new QueryClient({ defaultOptions: { queries: { enabled: false, retry: false } } });
ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <QueryClientProvider client={queryClient}>
      <App />
    </QueryClientProvider>
  </React.StrictMode>,
);
