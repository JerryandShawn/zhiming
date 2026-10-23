import React from 'react';
import ReactDOM from 'react-dom/client';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import App from './App';
import { applyTheme, useUi } from './state';
import { OfflineBanner, registerShellWorker, trackOfflineTypography } from './pwa';
import './styles/base.css';

applyTheme(useUi.getState().theme);
trackOfflineTypography();
const systemTheme = window.matchMedia('(prefers-color-scheme: dark)');
systemTheme.addEventListener('change', () => {
  if (useUi.getState().theme === 'system') applyTheme('system');
});
const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false, refetchOnWindowFocus: false } } });
ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <QueryClientProvider client={queryClient}>
      <OfflineBanner />
      <App />
    </QueryClientProvider>
  </React.StrictMode>,
);
void registerShellWorker();
