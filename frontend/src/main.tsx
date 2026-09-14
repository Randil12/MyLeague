import React from 'react';
import { createRoot } from 'react-dom/client';
import App from './App';
import {ChampionProvider} from './Champion';
import {EquipmentProvider} from './Equipment';
import './styles.css';

createRoot(document.getElementById('root')!).render(<React.StrictMode><ChampionProvider><EquipmentProvider><App /></EquipmentProvider></ChampionProvider></React.StrictMode>);
