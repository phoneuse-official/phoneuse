"use client";

import {useEffect,useRef,useState,type FormEvent,type KeyboardEvent} from 'react';
import {ArrowUp,Check,ExternalLink,LoaderCircle,MessageSquarePlus,PanelRight,ShieldCheck,Sparkles,Trash2,X} from 'lucide-react';
import './chat.css';
import clearedHistory from './cleared-history.json';
import {PhonePanel} from './components/phone-panel';
import {Badge} from '@/components/ui/badge';
import {Button} from '@/components/ui/button';
import {Card} from '@/components/ui/card';
import {Input} from '@/components/ui/input';
import {Sheet,SheetContent,SheetDescription,SheetHeader,SheetTitle} from '@/components/ui/sheet';
import {Textarea} from '@/components/ui/textarea';
import type {Device} from './types';

const API='http://127.0.0.1:8765';

type Task={id:string;device_id:string;task:string;status:string;stage?:string;current_action?:string;answer?:string;error?:string;device_calls?:number;created:number;finished?:number};

function codexSetup(error?:string):'path'|'login'|null{
  if(error?.includes('Codex CLI is unavailable in API process PATH'))return 'path';
  if(error?.includes('Codex CLI failed; check local login and quota'))return 'login';
  return null;
}

function codexAgentPrompt(issue:'path'|'login'){
  return `Set up the Codex CLI for PhoneUse Local on this Mac. The app reported: ${issue==='path'?'Codex CLI is unavailable in the API process PATH.':'Codex CLI could not complete a request; sign-in may be needed.'}

Check whether the official Codex CLI is installed and whether it is signed in. If it is missing, use only OpenAI’s official Codex CLI installation instructions. If sign-in is needed, run codex login and pause so I can complete any browser-based sign-in myself. Never ask me to paste credentials, and do not read, print, or copy credential files.

Make the CLI available to the local PhoneUse API. If needed, set QUNKONG_CODEX_BIN to the CLI’s absolute path and restart only the PhoneUse API after confirming which process belongs to this app. Do not stop unrelated services. Verify codex login status and the local API health endpoint afterward.

Do not interact with the connected phone, submit phone actions, change project files, or expose tokens. Tell me when setup is complete so I can retry my prompt in PhoneUse.`;
}

function statusLabel(task:Task){
  if(task.status==='running')return task.stage==='thinking'?'Thinking':task.stage==='cleanup'?'Finishing':'Working';
  if(task.status==='model_reported_result')return 'Completed';
  if(task.status==='cancelled')return 'Stopped';
  if(task.status==='blocked')return 'Needs your action';
  return 'Needs attention';
}

export default function Demo(){
  const historyRef=useRef<HTMLDivElement>(null);
  const [hidden,setHidden]=useState<string[]>(clearedHistory);
  const [key,setKey]=useState('');
  const [draft,setDraft]=useState('');
  const [devices,setDevices]=useState<Device[]>([]);
  const [device,setDevice]=useState('');
  const [input,setInput]=useState('');
  const [tasks,setTasks]=useState<Task[]>([]);
  const [error,setError]=useState('');
  const [busy,setBusy]=useState(false);
  const [revision,setRevision]=useState(0);
  const [copiedSetupPrompt,setCopiedSetupPrompt]=useState<'path'|'login'|null>(null);
  const [phoneOpen,setPhoneOpen]=useState(false);
  const [smallScreen,setSmallScreen]=useState(false);

  useEffect(()=>{
    const media=window.matchMedia('(max-width: 980px)');
    const update=()=>setSmallScreen(media.matches);
    update();
    media.addEventListener('change',update);
    return()=>media.removeEventListener('change',update);
  },[]);

  useEffect(()=>{
    document.title='PhoneUse Local';
    const fragment=new URLSearchParams(location.hash.slice(1)).get('key');
    if(fragment)history.replaceState(null,'',location.pathname+location.search);
    let savedKey=fragment||'';
    try{
      if(savedKey)sessionStorage.setItem('qunkong-api-key',savedKey);
      else savedKey=sessionStorage.getItem('qunkong-api-key')||'';
      const savedHidden=JSON.parse(localStorage.getItem('phoneuse-hidden-history')||'[]');
      setHidden([...clearedHistory,...(Array.isArray(savedHidden)?savedHidden:[])]);
    }catch{}
    setKey(savedKey);
  },[]);

  useEffect(()=>{
    const expired=()=>{
      try{sessionStorage.removeItem('qunkong-api-key');}catch{}
      setKey('');
      setDevice('');
      setDevices([]);
      setTasks([]);
      setError('Your local API key expired. Reopen PhoneUse with Start PhoneUse.command.');
    };
    window.addEventListener('qunkong-auth-expired',expired);
    return()=>window.removeEventListener('qunkong-auth-expired',expired);
  },[]);

  async function call<T>(path:string,method='GET',body?:unknown):Promise<T>{
    const response=await fetch(API+path,{
      method,
      headers:{Authorization:`Bearer ${key}`,'Content-Type':'application/json'},
      body:body?JSON.stringify(body):undefined,
      signal:AbortSignal.timeout(12000),
    });
    const data=await response.json() as T&{detail?:string};
    if(!response.ok)throw Error(typeof data.detail==='string'?data.detail:`Request failed (${response.status})`);
    return data;
  }

  useEffect(()=>{
    if(!key)return;
    let disposed=false;
    let pending=false;
    async function refresh(){
      if(pending)return;
      pending=true;
      try{
        const [deviceResponse,taskResponse]=await Promise.all([
          call<{devices:Device[]}>('/api/devices'),
          call<{tasks:Task[]}>('/api/ai/tasks'),
        ]);
        if(!disposed){
          setDevices(deviceResponse.devices);
          setTasks(taskResponse.tasks);
          setError('');
        }
      }catch(caught){
        if(!disposed)setError((caught as Error).message);
      }finally{
        pending=false;
      }
    }
    void refresh();
    const timer=setInterval(refresh,1500);
    return()=>{disposed=true;clearInterval(timer);};
  },[key]);

  useEffect(()=>{
    if(!device&&devices.length){
      const preferred=devices.find(item=>item.online!==false&&item.automation==='ready')||devices.find(item=>item.online!==false)||devices[0];
      setDevice(preferred.id);
    }
  },[device,devices]);

  const selected=devices.find(item=>item.id===device);
  const active=tasks.find(task=>task.status==='running');
  const shown=tasks.filter(task=>task.device_id===device&&(!hidden.includes(task.id)||task.status==='running')).sort((a,b)=>a.created-b.created);
  const historyVersion=JSON.stringify(shown);

  useEffect(()=>{
    if(historyRef.current)historyRef.current.scrollTop=historyRef.current.scrollHeight;
  },[historyVersion]);

  function clearHistory(){
    const ids=Array.from(new Set([...hidden,...tasks.filter(task=>task.status!=='running').map(task=>task.id)]));
    setHidden(ids);
    try{localStorage.setItem('phoneuse-hidden-history',JSON.stringify(ids));}catch{}
  }

  async function send(){
    if(busy||active||!input.trim()||selected?.automation!=='ready')return;
    setBusy(true);
    setError('');
    try{
      const task=await call<Task>('/api/ai/tasks','POST',{device_id:device,task:input.trim(),executor:'program',max_steps:30});
      setTasks(current=>[...current,task]);
      setInput('');
    }catch(caught){
      setError((caught as Error).message);
    }finally{
      setBusy(false);
    }
  }

  async function stop(){
    if(!active)return;
    setBusy(true);
    try{await call(`/api/ai/tasks/${active.id}/cancel`,'POST');}
    catch(caught){setError((caught as Error).message);}
    finally{setBusy(false);}
  }

  async function retryTask(task:Task){
    if(busy||active||task.device_calls)return;
    setBusy(true);
    setError('');
    try{
      const next=await call<Task>('/api/ai/tasks','POST',{device_id:task.device_id,task:task.task,executor:'program',max_steps:30});
      setTasks(current=>[...current,next]);
    }catch(caught){
      setError((caught as Error).message);
    }finally{
      setBusy(false);
    }
  }

  async function copySetupPrompt(issue:'path'|'login'){
    try{
      await navigator.clipboard.writeText(codexAgentPrompt(issue));
      setCopiedSetupPrompt(issue);
    }catch{
      setError('Could not copy the setup prompt. Expand the agent prompt below and copy its text manually.');
    }
  }

  function connect(event:FormEvent<HTMLFormElement>){
    event.preventDefault();
    const nextKey=draft.trim();
    try{sessionStorage.setItem('qunkong-api-key',nextKey);}catch{}
    setKey(nextKey);
    setDraft('');
  }

  function composerKeyDown(event:KeyboardEvent<HTMLTextAreaElement>){
    if(event.key==='Enter'&&!event.shiftKey&&!event.nativeEvent.isComposing&&event.nativeEvent.keyCode!==229){
      event.preventDefault();
      void send();
    }
  }

  const phonePanelProps={
    apiKey:key,
    device,
    devices,
    active:Boolean(active),
    revision,
    onDeviceChange:setDevice,
    onReconnect:()=>setRevision(value=>value+1),
  };

  if(!key)return <main className="login-shell">
    <Card className="login-card">
      <div className="brand-lockup"><span className="brand-mark"><Sparkles aria-hidden="true"/></span><span>PhoneUse</span><Badge variant="secondary">Local</Badge></div>
      <div className="login-copy"><h1>Connect to your workspace</h1><p>Open PhoneUse with Start PhoneUse.command to connect automatically, or enter the local API key below.</p></div>
      {error&&<div className="inline-alert" role="alert"><span>{error}</span></div>}
      <form className="login-form" onSubmit={connect}>
        <label htmlFor="local-api-key">Local API key</label>
        <Input id="local-api-key" type="password" autoComplete="off" value={draft} onChange={event=>setDraft(event.target.value)} required/>
        <Button type="submit" className="login-submit">Connect <ArrowUp aria-hidden="true"/></Button>
      </form>
      <div className="login-foot"><ShieldCheck aria-hidden="true"/><span>Your key stays in this browser session and is sent only to the local API.</span></div>
    </Card>
  </main>;

  return <main className="phoneuse-shell">
    <header className="app-header">
      <a href="/" className="brand-lockup" aria-label="PhoneUse Local home"><span className="brand-mark"><Sparkles aria-hidden="true"/></span><span>PhoneUse</span><Badge variant="secondary">Local</Badge></a>
      <div className="header-actions">
        <div className="session-indicator"><span className="status-dot is-live" aria-hidden="true"/>Local session</div>
        <a className="website-link" href="https://phoneuse.com/?utm_source=phoneuse-local&utm_medium=app&utm_campaign=opensource" target="_blank" rel="noopener noreferrer">About PhoneUse <ExternalLink aria-hidden="true"/></a>
        <Button type="button" variant="ghost" size="sm" className="clear-chat" aria-label="Clear chat" onClick={clearHistory} disabled={!shown.some(task=>task.status!=='running')}><Trash2 aria-hidden="true"/> Clear chat</Button>
        <Button type="button" variant="outline" size="sm" className="phone-toggle" onClick={()=>setPhoneOpen(true)}><PanelRight aria-hidden="true"/> Phone screen</Button>
      </div>
    </header>

    <div className="workspace">
      <section className="chat-workspace" aria-label="Phone assistant chat">
        <div className="chat-scroll" ref={historyRef} role="log" aria-live="polite" aria-relevant="additions text">
          {error&&<div className="inline-alert" role="alert"><span>{error}</span><Button type="button" variant="ghost" size="icon-sm" aria-label="Dismiss error" onClick={()=>setError('')}><X aria-hidden="true"/></Button></div>}
          {selected&&selected.automation!=='ready'&&<div className="inline-alert connection-alert" role="status"><span>Phone control is offline. Keep the iPhone unlocked and WebDriverAgent running in Xcode. Live video may still be available.</span></div>}

          {shown.length?shown.map(task=>{
            const setup=codexSetup(task.error);
            const running=task.status==='running';
            const answer=task.answer||task.error||(running?'':`Stopped: ${task.status.replaceAll('_',' ')}`);
            return <article key={task.id} className="chat-turn">
              <div className="user-message"><p>{task.task}</p></div>
              <div className="assistant-message">
                <span className="assistant-avatar"><Sparkles aria-hidden="true"/></span>
                <div className="assistant-content">
                  <div className="assistant-heading"><strong>PhoneUse</strong><Badge variant={running?'secondary':task.status==='model_reported_result'?'outline':'destructive'}>{running&&<LoaderCircle className="status-spinner" aria-hidden="true"/>}{statusLabel(task)}</Badge></div>
                  {running&&<p className="task-progress">{task.current_action?.replaceAll('_',' ')||'Starting'} <span>·</span> {task.device_calls||0} phone actions</p>}
                  {answer&&<p className="assistant-answer">{answer}</p>}
                  {setup&&<div className="codex-setup" role="status">
                    <strong>{setup==='path'?'Connect the Codex CLI':'Sign in to Codex'}</strong>
                    <p>{setup==='path'?'In Terminal, install the Codex CLI if needed, then sign in with':'In Terminal, sign in with'} <code>codex login</code> and finish the sign-in flow. Credentials stay with the Codex CLI; do not paste them into PhoneUse.</p>
                    {setup==='path'&&<p>If the API still cannot find the CLI, stop it and restart from the repository root with <code>QUNKONG_CODEX_BIN="$(command -v codex)" ./platform/start-api.sh</code>.</p>}
                    {!task.device_calls&&<Button type="button" variant="outline" size="sm" disabled={busy||Boolean(active)} onClick={()=>void retryTask(task)}>I’ve signed in — retry this prompt</Button>}
                    <details><summary>Ask your agent to set this up</summary><p>Copy this prompt into your coding agent. It will guide setup without asking you to share credentials.</p><pre>{codexAgentPrompt(setup)}</pre><Button type="button" variant="outline" size="sm" onClick={()=>void copySetupPrompt(setup)}>{copiedSetupPrompt===setup?<Check aria-hidden="true"/>:null}{copiedSetupPrompt===setup?'Prompt copied':'Copy setup prompt'}</Button></details>
                  </div>}
                </div>
              </div>
            </article>;
          }):<div className="welcome-state">
            <span className="welcome-icon"><MessageSquarePlus aria-hidden="true"/></span>
            <h2>What should I do on your iPhone?</h2>
            <p>Describe a task in plain language. You’ll see the conversation here and the live phone screen beside it.</p>
            <div className="prompt-suggestions">
              <button type="button" onClick={()=>setInput('Open the Settings app')}>Open an app<span>“Open the Settings app”</span></button>
              <button type="button" onClick={()=>setInput('Go to the Home Screen')}>Navigate your phone<span>“Go to the Home Screen”</span></button>
            </div>
          </div>}
        </div>

        <div className="composer-dock">
          <form className="chat-composer" onSubmit={event=>{event.preventDefault();void send();}}>
            <Textarea aria-label="Phone task" placeholder="Message PhoneUse" value={input} rows={1} maxLength={2000} disabled={busy||Boolean(active)} onChange={event=>setInput(event.target.value)} onKeyDown={composerKeyDown}/>
            <div className="composer-toolbar">
              <span>{active?'Phone is working…':selected?.automation==='ready'?'Enter to send · Shift + Enter for a new line':'Connect a ready phone to send a task'}</span>
              {active?<Button type="button" variant="destructive" size="icon" aria-label="Stop task" title="Stop task" onClick={()=>void stop()} disabled={busy}><span className="stop-icon"/></Button>:<Button type="submit" size="icon" aria-label="Send message" title="Send message" disabled={busy||!input.trim()||selected?.automation!=='ready'}>{busy?<LoaderCircle className="status-spinner" aria-hidden="true"/>:<ArrowUp aria-hidden="true"/>}</Button>}
            </div>
          </form>
          <p className="safety-note">PhoneUse can make mistakes. Purchases, messages, credentials, deletion, and settings changes require human handling.</p>
        </div>
      </section>

      {!smallScreen&&<aside className="desktop-phone-panel" aria-label="Live phone screen"><PhonePanel {...phonePanelProps}/></aside>}
    </div>

    <Sheet open={smallScreen&&phoneOpen} onOpenChange={setPhoneOpen}>
      <SheetContent side="right" className="phone-sheet">
        <SheetHeader className="sr-only"><SheetTitle>Phone screen</SheetTitle><SheetDescription>Live preview of your connected iPhone.</SheetDescription></SheetHeader>
        {smallScreen&&phoneOpen&&<PhonePanel {...phonePanelProps}/>}
      </SheetContent>
    </Sheet>
  </main>;
}
