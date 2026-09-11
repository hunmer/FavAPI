import {StrictMode} from 'react';
import {createRoot} from 'react-dom/client';
import {HashRouter} from 'react-router-dom';
import App from './App.tsx';
import './index.css';

// HashRouter：后端 StaticFiles 无 SPA 回退路由，hash 路由（/#/data）无需后端配合
createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <HashRouter>
      <App />
    </HashRouter>
  </StrictMode>,
);
