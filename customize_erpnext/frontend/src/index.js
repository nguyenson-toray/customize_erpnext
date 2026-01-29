import React from 'react';
import ReactDOM from 'react-dom/client';
import './index.css';
import App from './App';

// Chờ DOM load xong
const mountReactApp = () => {
  const el = document.getElementById("shoe-rack-react-root");
  
  if (el) {
    console.log(' Found root element, mounting React...');
    const root = ReactDOM.createRoot(el);
    root.render(<App />);
  } else {
    console.error('❌ Element #shoe-rack-react-root not found');
  }
};

// Thử mount ngay
mountReactApp();

// Nếu chưa ready, chờ DOMContentLoaded
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', mountReactApp);
}