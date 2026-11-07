"use client";

import {useEffect,useRef,useState,type FormEvent,type KeyboardEvent} from 'react';
import {ArrowUp,Check,ExternalLink,LoaderCircle,MessageSquarePlus,PanelLeft,PanelRight,ShieldCheck,Sparkles,X} from 'lucide-react';
import './chat.css';
import {ChatHistorySidebar} from './components/chat-history-sidebar';
import {PhonePanel} from './components/phone-panel';
import {forgetRejectedKey} from './saved-connection';
import {selectAvailableDevice} from './device-selection';
import {addTaskToConversation,createConversation,historyScope,loadChatHistory,reconcileTasks,saveChatHistory,type ApiTask,type ChatHistory,type ChatTask,type Conversation} from './chat-history';
import {Badge} from '@/components/ui/badge';
import {Button} from '@/components/ui/button';
import {Card} from '@/components/ui/card';
import {Input} from '@/components/ui/input';
import {Sheet,SheetContent,SheetDescription,SheetHeader,SheetTitle} from '@/components/ui/sheet';
import {Textarea} from '@/components/ui/textarea';
import type {Device} from './types';

const API='http://127.0.0.1:8765';

function codexSetup(error?:string):'path'|'login'|null{
  if(error?.includes('Codex CLI is unavailable in API process PATH'))return 'path';
  if(error?.includes('Codex CLI failed; check local login and quota'))return 'login';
  return null;
}

function codexAgentPrompt(issue:'path'|'login'){
  return `Set up the Codex CLI for PhoneUse Local on this Mac. The app reported: ${issue==='path'?'Codex CLI is unavailable in the API process PATH.':'Codex CLI could not complete a request; sign-in may be needed.'}

Check whether the official Codex CLI is installed and whether it is signed in. If it is missing, use only OpenAI’s official Codex CLI installation instructions. If sign-in is needed, run codex login and pause so I can complete any browser-based sign-in myself. Never ask me to paste credentials, and do not read, print, or copy credential files.

Make the CLI available to the local PhoneUse API. If needed, set PHONEUSE_CODEX_BIN to the CLI’s absolute path and restart only the PhoneUse API after confirming which process belongs to this app. Do not stop unrelated services. Verify codex login status and the local API health endpoint afterward.

Do not interact with the connected phone, submit phone actions, change project files, or expose tokens. Tell me when setup is complete so I can retry my prompt in PhoneUse.`;
}

function statusLabel(task:ChatTask){
  if(task.status==='running')return task.stage==='thinking'?'Thinking':task.stage==='cleanup'?'Finishing':'Working';
  if(task.status==='model_reported_result')return 'Result reported';
  if(task.status==='unverified_result')return 'Needs review';
  if(task.status==='cancelled')return 'Stopped';
  if(task.status==='blocked')return 'Needs your action';
  return 'Needs attention';
}

function actionLabel(action?:string){
  const labels:Record<string,string>={source_fast:'Reading the screen',find_elements:'Finding a control',
    element_state:'Checking a control',element_input_state:'Checking the input field',
    element_fill:'Entering text',element_submit_search:'Submitting the search',element_click:'Opening a control',
    active_element:'Checking the focused field',launch_app:'Opening the app',phone_program:'Following the plan'};
  return action?(labels[action]||action.replaceAll('_',' ')):'Starting';
}

function TaskTiming({task}:{task:ChatTask}){
  const [now,setNow]=useState<number|null>(null);
  const running=task.status==='running';
  useEffect(()=>{
    if(!running)return;
    setNow(Date.now());
    const timer=setInterval(()=>setNow(Date.now()),1000);
    return ()=>clearInterval(timer);
  },[running,task.id]);
  const elapsed=task.elapsed_seconds??(task.finished?task.finished-task.created:now===null?null:Math.max(0,now/1000-task.created));
  return <p className="task-progress">
    {elapsed!==null?`${elapsed.toFixed(1)} seconds · `:''}{task.model_calls||0} decisions
    {task.program_step&&running?` · step ${task.program_step} of ${task.program_total}`:''}
    {!running?` · ${task.device_calls||0} phone actions`:''}
  </p>;
}

export default function Demo(){
  const historyRef=useRef<HTMLDivElement>(null);
  const deletedTaskIdsRef=useRef(new Set<string>());
  const [key,setKey]=useState('');
  const [draft,setDraft]=useState('');
  const [devices,setDevices]=useState<Device[]>([]);
  const [device,setDevice]=useState('');
  const [input,setInput]=useState('');
  const [visualFallback,setVisualFallback]=useState(false);
  const [screenMode,setScreenMode]=useState<'ocr'|'accessibility'>('ocr');
  const [tasks,setTasks]=useState<ApiTask[]>([]);
  const [conversations,setConversations]=useState<Conversation[]>([]);
  const [activeChatId,setActiveChatId]=useState<string|null>(null);
  const [historyReady,setHistoryReady]=useState(false);
  const [authenticatedKey,setAuthenticatedKey]=useState('');
  const [historyStorageScope,setHistoryStorageScope]=useState('');
  const [historyOpen,setHistoryOpen]=useState(false);
  const [historyError,setHistoryError]=useState('');
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
      if(savedKey)sessionStorage.setItem('phoneuse-api-key',savedKey);
      else savedKey=sessionStorage.getItem('phoneuse-api-key')||localStorage.getItem('phoneuse-api-key')||'';
    }catch{}
    setKey(savedKey);
  },[]);

  useEffect(()=>{
    if(!historyReady||authenticatedKey!==key)return;
    try{
      saveChatHistory(localStorage,{activeId:activeChatId,conversations,
        deletedTaskIds:Array.from(deletedTaskIdsRef.current)},historyStorageScope);
      setHistoryError('');
    }catch{setHistoryError('Chat history could not be saved in this browser. Storage may be full.');}
  },[activeChatId,conversations,historyReady,authenticatedKey,key,historyStorageScope]);

  useEffect(()=>{
    const expired=(event:Event)=>{
      const rejectedKey=(event as CustomEvent<{key?:string}>).detail?.key??key;
      if(rejectedKey!==key)return;
      try{forgetRejectedKey(sessionStorage,key);}catch{}
      try{forgetRejectedKey(localStorage,key);}catch{}
      setKey('');
      setDevice('');
      setDevices([]);
      setTasks([]);
      setConversations([]);
      setActiveChatId(null);
      setAuthenticatedKey('');
      setHistoryReady(false);
      setError('Your local API key expired. Reopen PhoneUse with Start PhoneUse.command.');
    };
    window.addEventListener('phoneuse-auth-expired',expired);
    return()=>window.removeEventListener('phoneuse-auth-expired',expired);
  },[key]);

  async function call<T>(path:string,method='GET',body?:unknown):Promise<T>{
    const response=await fetch(API+path,{
      method,
      headers:{Authorization:`Bearer ${key}`,'Content-Type':'application/json'},
      body:body?JSON.stringify(body):undefined,
      signal:AbortSignal.timeout(12000),
    });
    const data=await response.json() as T&{detail?:string};
    if(response.status===401)window.dispatchEvent(new CustomEvent('phoneuse-auth-expired',{detail:{key}}));
    if(!response.ok)throw Error(typeof data.detail==='string'?data.detail:`Request failed (${response.status})`);
    return data;
  }

  useEffect(()=>{
    setHistoryReady(false);
    setAuthenticatedKey('');
    setConversations([]);
    setActiveChatId(null);
    deletedTaskIdsRef.current=new Set();
    if(!key)return;
    let disposed=false;
    let pending=false;
    let loaded=false;
    async function refresh(){
      if(pending)return;
      pending=true;
      try{
        const [deviceResponse,taskResponse]=await Promise.all([
          call<{devices:Device[]}>('/api/devices'),
          call<{tasks:ApiTask[]}>('/api/ai/tasks'),
        ]);
        if(disposed)return;
        if(!loaded){
          // Remember only credentials that both API reads have authenticated.
          try{localStorage.setItem('phoneuse-api-key',key);}catch{}
          // Authenticate both API reads before opening this credential's cache.
          const scope=await historyScope(key);
          if(disposed)return;
          let saved:ChatHistory={activeId:null,conversations:[]};
          try{saved=loadChatHistory(localStorage,scope);}catch{}
          deletedTaskIdsRef.current=new Set(saved.deletedTaskIds||[]);
          // Migrate old deletion markers only for tasks this credential can read.
          try{
            const legacy:unknown=JSON.parse(localStorage.getItem('phoneuse-hidden-history')||'[]');
            const allowedIds=new Set(taskResponse.tasks.map(task=>task.id));
            if(Array.isArray(legacy))for(const id of legacy){
              if(typeof id==='string'&&allowedIds.has(id))deletedTaskIdsRef.current.add(id);
            }
          }catch{}
          const initial=saved.conversations.length?saved.conversations:[createConversation()];
          setConversations(reconcileTasks(initial,taskResponse.tasks,deletedTaskIdsRef.current));
          setActiveChatId(saved.activeId||initial[0].id);
          setHistoryStorageScope(scope);
          setAuthenticatedKey(key);
          setHistoryReady(true);
          loaded=true;
        }else{
          setConversations(current=>reconcileTasks(current,taskResponse.tasks,deletedTaskIdsRef.current));
        }
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
    const available=selectAvailableDevice(devices,device);
    if(available!==device)setDevice(available);
  },[device,devices]);

  const selected=devices.find(item=>item.id===device);
  const active=tasks.find(task=>task.status==='running');
  const currentConversation=conversations.find(item=>item.id===activeChatId);
  const shown=currentConversation?.tasks||[];
  const historyVersion=JSON.stringify(shown);

  useEffect(()=>{
    if(historyReady&&conversations.length&&!conversations.some(item=>item.id===activeChatId)){
      setActiveChatId([...conversations].sort((left,right)=>right.updatedAt-left.updatedAt)[0].id);
    }
  },[activeChatId,conversations,historyReady]);

  useEffect(()=>{
    if(historyRef.current)historyRef.current.scrollTop=historyRef.current.scrollHeight;
  },[historyVersion,activeChatId]);

  function newChat(){
    const conversation=createConversation();
    setConversations(current=>[...current,conversation]);
    setActiveChatId(conversation.id);
    setInput('');
    setHistoryOpen(false);
  }

  function selectChat(id:string){
    setActiveChatId(id);
    setInput('');
    setHistoryOpen(false);
  }

  function deleteChat(id:string){
    const conversation=conversations.find(item=>item.id===id);
    if(!conversation||conversation.tasks.some(task=>task.status==='running'))return;
    if(!window.confirm(`Delete “${conversation.title}”? This removes it from this browser’s chat history.`))return;
    for(const task of conversation.tasks)deletedTaskIdsRef.current.add(task.id);
    const remaining=conversations.filter(item=>item.id!==id);
    if(remaining.length){
      setConversations(remaining);
      if(activeChatId===id){
        setActiveChatId([...remaining].sort((left,right)=>right.updatedAt-left.updatedAt)[0].id);
        setInput('');
      }
    }else{
      const fresh=createConversation();
      setConversations([fresh]);
      setActiveChatId(fresh.id);
      setInput('');
    }
  }

  async function send(){
    if(busy||active||!activeChatId||!input.trim()||selected?.automation!=='ready')return;
    const chatId=activeChatId;
    const prompt=input.trim();
    const previous=currentConversation?.tasks.at(-1);
    const previousTaskId=previous&&tasks.some(task=>task.id===previous.id&&task.device_id===device)?previous.id:undefined;
    setBusy(true);
    setError('');
    try{
      const task=await call<ApiTask>('/api/ai/tasks','POST',{device_id:device,task:prompt,executor:'program',screen_mode:screenMode,visual_fallback:visualFallback,...(previousTaskId?{previous_task_id:previousTaskId}:{})});
      setTasks(current=>current.some(item=>item.id===task.id)?current.map(item=>item.id===task.id?task:item):[...current,task]);
      setConversations(current=>addTaskToConversation(current,task,chatId));
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

  async function retryTask(task:ChatTask){
    const source=tasks.find(item=>item.id===task.id);
    const chatId=activeChatId;
    if(busy||active||!source||!chatId||task.device_calls)return;
    setBusy(true);
    setError('');
    try{
      const next=await call<ApiTask>('/api/ai/tasks','POST',{device_id:source.device_id,task:task.task,executor:'program',screen_mode:screenMode,visual_fallback:visualFallback});
      setTasks(current=>[...current,next]);
      setConversations(current=>addTaskToConversation(current,next,chatId));
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
    try{sessionStorage.setItem('phoneuse-api-key',nextKey);}catch{}
    setKey(nextKey);
    setDraft('');
  }

  function composerKeyDown(event:KeyboardEvent<HTMLTextAreaElement>){
    if(event.key==='Enter'&&!event.shiftKey&&!event.nativeEvent.isComposing&&event.nativeEvent.keyCode!==229){
      event.preventDefault();
      void send();
    }
  }

  const historyPanelProps={conversations,activeId:activeChatId,onNewChat:newChat,onSelect:selectChat,onDelete:deleteChat};
  const phonePanelProps={
    apiKey:key,
    device,
    devices,
    active:Boolean(active),
    revision,
    onDeviceChange:setDevice,
    onReconnect:()=>setRevision(value=>value+1),
  };

  if(!key||!historyReady||authenticatedKey!==key)return <main className="login-shell">
    <Card className="login-card">
      <div className="brand-lockup"><span className="brand-mark"><Sparkles aria-hidden="true"/></span><span>PhoneUse</span><Badge variant="secondary">Local</Badge></div>
      <div className="login-copy"><h1>Connect to your workspace</h1><p>Connect once to get started. This browser will remember your workspace when you return. Open Start PhoneUse.command to connect automatically, or enter your local API key below.</p></div>
      {error&&<div className="inline-alert" role="alert"><span>{error}</span></div>}
      <form className="login-form" onSubmit={connect}>
        <label htmlFor="local-api-key">Local API key</label>
        <Input id="local-api-key" type="password" autoComplete="off" value={draft} onChange={event=>setDraft(event.target.value)} required/>
        <Button type="submit" className="login-submit">Connect <ArrowUp aria-hidden="true"/></Button>
      </form>
      <div className="login-foot"><ShieldCheck aria-hidden="true"/><span>Your key is saved in this browser and is sent only to the local API.</span></div>
    </Card>
  </main>;

  return <main className="phoneuse-shell">
    <header className="app-header">
      <a href="/" className="brand-lockup" aria-label="PhoneUse Local home"><span className="brand-mark"><Sparkles aria-hidden="true"/></span><span>PhoneUse</span><Badge variant="secondary">Local</Badge></a>
      <div className="header-actions">
        <div className="session-indicator"><span className="status-dot is-live" aria-hidden="true"/>Local session</div>
        <a className="website-link" href="https://phoneuse.com/?utm_source=phoneuse-local&utm_medium=app&utm_campaign=opensource" target="_blank" rel="noopener noreferrer">About PhoneUse <ExternalLink aria-hidden="true"/></a>
        <Button type="button" variant="ghost" size="sm" className="history-toggle" aria-label="Open chat history" onClick={()=>setHistoryOpen(true)}><PanelLeft aria-hidden="true"/> History</Button>
        <Button type="button" variant="outline" size="sm" className="phone-toggle" onClick={()=>setPhoneOpen(true)}><PanelRight aria-hidden="true"/> Phone screen</Button>
      </div>
    </header>

    <div className="workspace">
      <aside className="desktop-history"><ChatHistorySidebar {...historyPanelProps}/></aside>
      <section className="chat-workspace" aria-label="Phone assistant chat">
        <div className="chat-scroll" ref={historyRef} role="log" aria-live="polite" aria-relevant="additions text">
          {historyError&&<div className="inline-alert" role="alert"><span>{historyError}</span></div>}
          {error&&<div className="inline-alert" role="alert"><span>{error}</span><Button type="button" variant="ghost" size="icon-sm" aria-label="Dismiss error" onClick={()=>setError('')}><X aria-hidden="true"/></Button></div>}
          {selected&&selected.automation!=='ready'&&<div className="inline-alert connection-alert" role="status"><span>Phone control is offline. Keep the iPhone unlocked and WebDriverAgent running in Xcode. Live video may still be available.</span></div>}
          {active&&!shown.some(task=>task.id===active.id)&&<div className="inline-alert connection-alert" role="status"><span>A task is running in another chat. Switch back to follow its progress.</span></div>}

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
                  {running&&<p className="task-progress">{actionLabel(task.current_action)} <span>·</span> {task.device_calls||0} phone actions</p>}
                  <TaskTiming task={task}/>
                  {answer&&<p className="assistant-answer">{answer}</p>}
                  {task.failed_action&&<div className="inline-alert" role="status"><div>
                    <p>{actionLabel(task.failed_action)} failed{task.error_code==='stale_element'?' because the control changed during interaction.':'.'}</p>
                    <p>{task.recovery_guidance}</p>
                    {task.recovery_observed&&<p>The screen was checked again without repeating the action.</p>}
                  </div></div>}
                  {setup&&<div className="codex-setup" role="status">
                    <strong>{setup==='path'?'Connect the Codex CLI':'Sign in to Codex'}</strong>
                    <p>{setup==='path'?'In Terminal, install the Codex CLI if needed, then sign in with':'In Terminal, sign in with'} <code>codex login</code> and finish the sign-in flow. Credentials stay with the Codex CLI; do not paste them into PhoneUse.</p>
                    {setup==='path'&&<p>If the API still cannot find the CLI, stop it and restart from the repository root with <code>PHONEUSE_CODEX_BIN="$(command -v codex)" ./platform/start-api.sh</code>.</p>}
                    {!task.device_calls&&<Button type="button" variant="outline" size="sm" disabled={busy||Boolean(active)||!tasks.some(item=>item.id===task.id)} onClick={()=>void retryTask(task)}>I’ve signed in — retry this prompt</Button>}
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
            <label className="visual-fallback-option">Screen reading <select aria-label="Screen reading mode" value={screenMode} disabled={Boolean(active)} onChange={event=>setScreenMode(event.target.value as 'ocr'|'accessibility')}><option value="ocr">OCR first, accessibility fallback</option><option value="accessibility">Accessibility only</option></select><span>Screen text is shared with the model.</span></label>
            <label className="visual-fallback-option"><input type="checkbox" checked={visualFallback} disabled={Boolean(active)} onChange={event=>setVisualFallback(event.target.checked)}/> Use screenshots if controls cannot be found <span>(shares screen images with the model)</span></label>
            <div className="composer-toolbar">
              <span>{active?shown.some(task=>task.id===active.id)?'Phone is working…':'A task is running in another chat…':selected?.automation==='ready'?'Enter to send · Shift + Enter for a new line':'Connect a ready phone to send a task'}</span>
              {active?<Button type="button" variant="destructive" size="icon" aria-label="Stop task" title="Stop task" onClick={()=>void stop()} disabled={busy}><span className="stop-icon"/></Button>:<Button type="submit" size="icon" aria-label="Send message" title="Send message" disabled={busy||!input.trim()||selected?.automation!=='ready'}>{busy?<LoaderCircle className="status-spinner" aria-hidden="true"/>:<ArrowUp aria-hidden="true"/>}</Button>}
            </div>
          </form>
          <p className="safety-note">PhoneUse can act on your requests. Review results and stop the task whenever needed.</p>
        </div>
      </section>

      {!smallScreen&&<aside className="desktop-phone-panel" aria-label="Live phone screen"><PhonePanel {...phonePanelProps}/></aside>}
    </div>

    <Sheet open={smallScreen&&historyOpen} onOpenChange={setHistoryOpen}>
      <SheetContent side="left" className="history-sheet" showCloseButton={false}>
        <SheetHeader className="sr-only"><SheetTitle>Chat history</SheetTitle><SheetDescription>Search and switch between saved chats.</SheetDescription></SheetHeader>
        <ChatHistorySidebar {...historyPanelProps}/>
      </SheetContent>
    </Sheet>

    <Sheet open={smallScreen&&phoneOpen} onOpenChange={setPhoneOpen}>
      <SheetContent side="right" className="phone-sheet">
        <SheetHeader className="sr-only"><SheetTitle>Phone screen</SheetTitle><SheetDescription>Live preview of your connected iPhone.</SheetDescription></SheetHeader>
        {smallScreen&&phoneOpen&&<PhonePanel {...phonePanelProps}/>}
      </SheetContent>
    </Sheet>
  </main>;
}
