import {useEffect, useState} from 'react';
import {Activity, AlertTriangle, Clock3, Radio, RefreshCw} from 'lucide-react';
import {useData, type Row} from './api';

const when = (value: Row[string]) => value ? new Date(String(value)).toLocaleString('fr-FR',{dateStyle:'short',timeStyle:'medium'}) : '—';
const statusLabels:Record<string,string> = {
  in_game:'Partie détectée', not_in_game:'Aucune partie détectée', other_queue:'Autre file de jeu', error:'Observation en erreur',
};
const serviceLabels:Record<string,string> = {
  ok:'Collecte opérationnelle', polling:'Interrogation en cours', running:'Collecte en cours', idle:'Aucun joueur suivi',
  rate_limited:'Pause demandée par Riot (quota)', authentication_error:'Clé Riot refusée : vérifier la clé ou les accès',
  degraded:'Collecte dégradée : nouvelle tentative prévue', stopped:'Service arrêté',
};

export default function LiveGames({revision}:{revision:number}) {
  const [tick,setTick]=useState(0);
  useEffect(()=>{
    const refresh=()=>{if(document.visibilityState==='visible')setTick(v=>v+1);};
    const timer=window.setInterval(refresh,15000);
    document.addEventListener('visibilitychange',refresh);
    return()=>{clearInterval(timer);document.removeEventListener('visibilitychange',refresh);};
  },[]);
  const service=useData('/api/live/status',{},revision+tick);
  const players=useData('/api/live/players',{},revision+tick);
  const heartbeat=service.rows[0];
  const currentGames=new Set(players.rows.filter(p=>p.status==='in_game'&&!p.is_stale).map(p=>p.game_id));
  return <div className="live-page"><aside className="note"><Radio size={20}/><div><strong>Observations spectator · actualisation de l’écran toutes les 15 secondes</strong><p>Cette vue ne dépend ni du patch ni du joueur sélectionné dans les autres analyses. Le service interroge les joueurs configurés, Academy en priorité. Ce n’est pas un flux continu de positions, d’or ou de kills.</p></div></aside>
    {(service.error||players.error)&&<div className="error-banner" role="alert"><AlertTriangle size={16}/> {service.error||players.error} Le service Docker <code>riot-live</code> doit avoir initialisé ses vues. L’état des parties est inconnu tant que la connexion n’est pas rétablie.</div>}
    {service.loading||players.loading?<div className="loading" role="status"><RefreshCw size={18}/> Actualisation des observations…</div>:<>
      {heartbeat?<><div className={`live-service ${heartbeat.is_stale||heartbeat.status==='stopped'?'stale':''}`} role="status"><Activity size={20}/><div><strong>{heartbeat.is_stale?'Service sans nouvelles récentes':serviceLabels[String(heartbeat.status)]||String(heartbeat.status)}</strong><p>Dernier signal : {when(heartbeat.heartbeat_at)} · prochain cycle prévu : {when(heartbeat.next_poll_at)}</p></div><span className="badge">Cycle cible : {String(heartbeat.interval_seconds)} s</span></div><div className="stats"><article className="stat"><span>Joueurs sélectionnés</span><strong>{String(heartbeat.selected_players)}</strong><small>Limite configurable, priorité Academy</small></article><article className="stat"><span>Parties observées récemment</span><strong>{currentGames.size}</strong><small>Parties distinctes, pas un total mondial</small></article><article className="stat"><span>Erreurs du dernier cycle</span><strong>{String(heartbeat.errors)}</strong><small>Une erreur ne signifie pas une fin de partie</small></article><article className="stat"><span>Écran actualisé à</span><strong className="live-time">{new Date().toLocaleTimeString('fr-FR')}</strong><small>Heure locale de ce navigateur</small></article></div></>:!service.error&&<div className="empty"><Radio size={25}/><h3>En attente du premier cycle</h3><p>Le service n’a pas encore enregistré son état. Vérifie ses logs sur le VPS.</p></div>}
      {!players.error&&!players.rows.length&&<div className="empty"><h3>Aucune observation disponible</h3><p>Il faut des joueurs suivis dans l’entrepôt et un premier cycle réussi. Un écran vide n’est pas une preuve que tous les joueurs sont hors partie.</p></div>}
      <div className="live-grid">{players.rows.map((p,index)=>{
        const stale=Boolean(p.is_stale)||Boolean(heartbeat?.is_stale)||heartbeat?.status==='stopped';
        const active=p.status==='in_game';
        return <article className={`panel live-card ${stale?'stale':''}`} key={`${p.player_name}-${index}`}><div className="panel-head"><div><span className="eyebrow">JOUEUR SUIVI · EUW</span><h2>{String(p.player_name)}</h2></div><span className={`badge ${stale||p.status==='error'?'warning':''}`}>{stale?'Observation périmée':statusLabels[String(p.status)]||'État inconnu'}</span></div>
          {active&&<><div className="live-match"><span>Partie #{String(p.game_id)}</span><span>Début déclaré : {when(p.game_started_at)}</span></div><div className="live-teams"><div><h3>Côté bleu</h3><p>{String(p.blue_team||'Composition indisponible')}</p></div><div><h3>Côté rouge</h3><p>{String(p.red_team||'Composition indisponible')}</p></div></div></>}
          {!active&&<p className="live-message">{p.status==='error'?`Échec de l’observation (${String(p.error_code||'erreur inconnue')}). Aucune conclusion sur la partie actuelle.`:p.status==='other_queue'?'Une partie a été détectée hors classé solo ; elle n’est pas affichée dans ce périmètre.':'Riot ne renvoyait pas de partie active lors de cette vérification. Ce n’est pas un statut de connexion du joueur.'}</p>}
          {stale&&<p className="live-message negative">Ne pas considérer cette observation comme l’état actuel du joueur.</p>}
          <div className="live-timing"><span><Clock3 size={12}/> Observation : {when(p.checked_at)}</span><span>Stockage : {when(p.stored_at)}</span><span>Appel API : {String(p.request_ms??'—')} ms · observation → SQL : {String(p.storage_delay_ms??'—')} ms</span>{active&&<span>Première détection : {when(p.first_observed_at)}</span>}</div>
        </article>;
      })}</div>
    </>}
  </div>;
}
