import React from 'react';
import { createRoot } from 'react-dom/client';
import App from './App';
import {ChampionProvider} from './Champion';
import './styles.css';

createRoot(document.getElementById('root')!).render(<React.StrictMode><ChampionProvider><App /></ChampionProvider></React.StrictMode>);
