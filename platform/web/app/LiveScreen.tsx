"use client";
import {useEffect,useRef,useState,type CanvasHTMLAttributes} from 'react';
type Props=CanvasHTMLAttributes<HTMLCanvasElement>&{deviceId:string;apiKey:string;accessRevision?:string;hideIndicator?:boolean};
export default function LiveScreen({deviceId,apiKey,accessRevision,hideIndicator=false,...canvasProps}:Props){
 const canvas=useRef<HTMLCanvasElement>(null),live=useRef(false),source=useRef('');
 const [status,setStatus]=useState('Connecting to the live device…'),[fps,setFps]=useState(0),[hasFrame,setHasFrame]=useState(false),[connected,setConnected]=useState(false);
 useEffect(()=>{
  let disposed=false,ws:WebSocket|null=null,retry:ReturnType<typeof setTimeout>|undefined,watch:ReturnType<typeof setInterval>;
  let pending:Blob|null=null,decoding=false,count=0,start=performance.now(),receivedAt=performance.now(),attempt=0,generation=0,connecting=false,terminal=false,lastStreamError:string|null=null;
  let request:AbortController|null=null;
  function markOffline(message:string,clear=false){live.current=false;setConnected(false);setFps(0);setStatus(message);if(clear){setHasFrame(false);canvas.current?.getContext('2d')?.clearRect(0,0,canvas.current.width,canvas.current.height);}}
  function retrySoon(){if(disposed||terminal||document.hidden)return;clearTimeout(retry);retry=setTimeout(()=>void connect(),Math.min(500*2**Math.min(attempt++,5),8000));}
  async function draw(gen:number){
   if(decoding)return;decoding=true;
   try{while(pending&&!disposed&&gen===generation){const blob=pending;pending=null;const bitmap=await createImageBitmap(blob);
    if(disposed||gen!==generation){bitmap.close();break;}
    const el=canvas.current;if(el){if(el.width!==bitmap.width||el.height!==bitmap.height){el.width=bitmap.width;el.height=bitmap.height;}el.getContext('2d',{alpha:false})?.drawImage(bitmap,0,0);}
    bitmap.close();count++;if(!live.current){live.current=true;setHasFrame(true);setConnected(true);setStatus('Live');}
    const now=performance.now();if(now-start>=1000){setFps(Math.round(count*1000/(now-start)));count=0;start=now;}
   }}catch{if(!disposed){markOffline('Waiting for live phone video. Reconnecting…');ws?.close();}}finally{decoding=false;if(pending&&!disposed)void draw(generation);}
  }
  async function connect(){
   if(disposed||terminal||connecting||document.hidden)return;connecting=true;clearTimeout(retry);const gen=++generation;receivedAt=performance.now();
   markOffline(attempt?'Connection interrupted. Reconnecting…':'Connecting to the live device…');request=new AbortController();const timer=setTimeout(()=>request?.abort(),8000);
   try{
    const response=await fetch(`http://127.0.0.1:8765/api/devices/${encodeURIComponent(deviceId)}/view`,{method:'POST',headers:{Authorization:`Bearer ${apiKey}`},signal:request.signal});
    if(disposed||gen!==generation||document.hidden)return;
    if(!response.ok){let detail='Connection unavailable';try{detail=(await response.json() as {detail?:string}).detail||detail;}catch{}
     if(response.status===401||response.status===403){terminal=true;markOffline(typeof detail==='string'?detail:'Access ended. Reopen the page with Start PhoneUse.command.',true);if(response.status===401)window.dispatchEvent(new CustomEvent('phoneuse-auth-expired',{detail:{key:apiKey}}));return;}
     if(response.status===409&&typeof detail==='string'&&detail.startsWith('Screen access was released')){terminal=true;markOffline('Connection released. Click Reconnect screen.',true);return;}
     throw new Error(typeof detail==='string'?detail:'Waiting for the phone');
    }
    const socket=new WebSocket(`ws://127.0.0.1:8765/api/devices/${encodeURIComponent(deviceId)}/stream`);ws=socket;socket.binaryType='blob';receivedAt=performance.now();
    socket.onopen=()=>{if(!disposed&&gen===generation)socket.send(JSON.stringify({token:apiKey,keepalive:true}));};
    socket.onmessage=e=>{if(disposed||gen!==generation)return;if(e.data instanceof Blob){receivedAt=performance.now();lastStreamError=null;pending=e.data;attempt=0;void draw(gen);}else{try{const d=JSON.parse(e.data);if(d.type==='ready'||d.type==='source')source.current=d.source==='native-usb'?'USB':d.source==='wda-screenshot'?'USB snapshots':'Compatible stream';if(d.type==='error'){terminal=d.retryable===false;lastStreamError=d.message;markOffline(d.message,terminal);}}catch{markOffline('Waiting for live phone video. Reconnecting…');}}};
    socket.onclose=()=>{if(disposed||gen!==generation)return;generation++;pending=null;ws=null;if(!terminal){markOffline(lastStreamError?`${lastStreamError} · Reconnecting…`:'Waiting for live phone video. Reconnecting…');retrySoon();}};
    socket.onerror=()=>socket.close();
   }catch(e){if(!disposed&&gen===generation){markOffline(`${(e as Error).name==='AbortError'?'The local API timed out':(e as Error).message} · Reconnecting…`);retrySoon();}}
   finally{clearTimeout(timer);connecting=false;}
  }
  function wake(){if(disposed)return;if(document.hidden){clearTimeout(retry);generation++;pending=null;const old=ws;ws=null;old?.close();markOffline('Video paused while this tab is in the background.');return;}if(!terminal){if(connecting){clearTimeout(retry);retry=setTimeout(wake,100);return;}if(!ws||ws.readyState===WebSocket.CLOSED){attempt=0;void connect();}}}
  void connect();watch=setInterval(()=>{if(ws&&performance.now()-receivedAt>12000&&(ws.readyState===WebSocket.OPEN||ws.readyState===WebSocket.CONNECTING)){markOffline('Waiting for live phone video. Reconnecting…');ws.close();}},1000);
  window.addEventListener('online',wake);document.addEventListener('visibilitychange',wake);
  return()=>{disposed=true;generation++;pending=null;live.current=false;request?.abort();clearTimeout(retry);clearInterval(watch);ws?.close();window.removeEventListener('online',wake);document.removeEventListener('visibilitychange',wake);};
 },[deviceId,apiKey,accessRevision]);
  return <><canvas {...canvasProps} ref={canvas} aria-label='Live phone screen' aria-disabled={!connected}
 onPointerDown={e=>{if(live.current)canvasProps.onPointerDown?.(e);}} onPointerUp={e=>{if(live.current)canvasProps.onPointerUp?.(e);}}
 onKeyDown={e=>{if(live.current)canvasProps.onKeyDown?.(e);}}
 style={{visibility:hasFrame?'visible':'hidden',opacity:connected?1:.45,pointerEvents:connected?'auto':'none'}}/>{!connected&&<div className="live-placeholder" role="status">{status}{hasFrame&&<small>Last received frame. Waiting for live video.</small>}</div>}{!hideIndicator&&<span className="live-indicator">{connected?`● LIVE · ${fps||'…'} FPS · ${source.current}`:status}</span>}</>;
}
