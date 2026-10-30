"use client";
import {useEffect,useRef,useState,type CanvasHTMLAttributes} from 'react';
type Props=CanvasHTMLAttributes<HTMLCanvasElement>&{deviceId:string;apiKey:string;accessRevision?:string;locale?:'en'|'zh';hideIndicator?:boolean};
export default function LiveScreen({deviceId,apiKey,accessRevision,locale='zh',hideIndicator=false,...canvasProps}:Props){
 const canvas=useRef<HTMLCanvasElement>(null),live=useRef(false),source=useRef('');
 const [status,setStatus]=useState('正在连接手机…'),[fps,setFps]=useState(0),[hasFrame,setHasFrame]=useState(false),[connected,setConnected]=useState(false);
 useEffect(()=>{
  let disposed=false,ws:WebSocket|null=null,retry:ReturnType<typeof setTimeout>|undefined,watch:ReturnType<typeof setInterval>;
  let pending:Blob|null=null,decoding=false,count=0,start=performance.now(),receivedAt=performance.now(),attempt=0,generation=0,connecting=false,terminal=false;
  let request:AbortController|null=null;
  function markOffline(message:string,clear=false){live.current=false;setConnected(false);setFps(0);setStatus(message);if(clear){setHasFrame(false);canvas.current?.getContext('2d')?.clearRect(0,0,canvas.current.width,canvas.current.height);}}
  function retrySoon(){if(disposed||terminal||document.hidden)return;clearTimeout(retry);retry=setTimeout(()=>void connect(),Math.min(500*2**Math.min(attempt++,5),8000));}
  async function draw(gen:number){
   if(decoding)return;decoding=true;
   try{while(pending&&!disposed&&gen===generation){const blob=pending;pending=null;const bitmap=await createImageBitmap(blob);
    if(disposed||gen!==generation){bitmap.close();break;}
    const el=canvas.current;if(el){if(el.width!==bitmap.width||el.height!==bitmap.height){el.width=bitmap.width;el.height=bitmap.height;}el.getContext('2d',{alpha:false})?.drawImage(bitmap,0,0);}
    bitmap.close();count++;if(!live.current){live.current=true;setHasFrame(true);setConnected(true);setStatus('实时');}
    const now=performance.now();if(now-start>=1000){setFps(Math.round(count*1000/(now-start)));count=0;start=now;}
   }}catch{if(!disposed){markOffline('画面正在恢复…');ws?.close();}}finally{decoding=false;if(pending&&!disposed)void draw(generation);}
  }
  async function connect(){
   if(disposed||terminal||connecting||document.hidden)return;connecting=true;clearTimeout(retry);const gen=++generation;receivedAt=performance.now();
   markOffline(attempt?'连接暂时中断，正在自动恢复…':'正在连接手机…');request=new AbortController();const timer=setTimeout(()=>request?.abort(),8000);
   try{
    const response=await fetch(`http://127.0.0.1:8765/api/devices/${encodeURIComponent(deviceId)}/view`,{method:'POST',headers:{Authorization:`Bearer ${apiKey}`},signal:request.signal});
    if(disposed||gen!==generation||document.hidden)return;
    if(!response.ok){let detail='连接暂不可用';try{detail=(await response.json() as {detail?:string}).detail||detail;}catch{}
     if(response.status===401||response.status===403){terminal=true;markOffline(typeof detail==='string'?detail:'使用权限已结束',true);if(response.status===401)window.dispatchEvent(new Event('qunkong-auth-expired'));return;}
     if(response.status===409&&typeof detail==='string'&&detail.includes('主动释放')){terminal=true;markOffline('已释放使用权，点击连接可再次查看',true);return;}
     throw new Error(typeof detail==='string'?detail:'正在等待手机');
    }
    const socket=new WebSocket(`ws://127.0.0.1:8765/api/devices/${encodeURIComponent(deviceId)}/stream`);ws=socket;socket.binaryType='blob';receivedAt=performance.now();
    socket.onopen=()=>{if(!disposed&&gen===generation)socket.send(JSON.stringify({token:apiKey,keepalive:true}));};
    socket.onmessage=e=>{if(disposed||gen!==generation)return;if(e.data instanceof Blob){receivedAt=performance.now();pending=e.data;attempt=0;void draw(gen);}else{try{const d=JSON.parse(e.data);if(d.type==='ready'||d.type==='source')source.current=d.source==='native-usb'?'USB高速画面':'兼容画面';if(d.type==='error'){terminal=d.retryable===false;markOffline(d.message,terminal);}}catch{markOffline('正在恢复视频连接…');}}};
    socket.onclose=()=>{if(disposed||gen!==generation)return;generation++;pending=null;ws=null;if(!terminal){markOffline('画面暂停，正在自动重连…');retrySoon();}};
    socket.onerror=()=>socket.close();
   }catch(e){if(!disposed&&gen===generation){markOffline(`${(e as Error).name==='AbortError'?'节点连接超时':(e as Error).message} · 正在自动重连`);retrySoon();}}
   finally{clearTimeout(timer);connecting=false;}
  }
  function wake(){if(disposed)return;if(document.hidden){clearTimeout(retry);generation++;pending=null;const old=ws;ws=null;old?.close();markOffline('页面在后台，返回后自动恢复画面');return;}if(!terminal){if(connecting){clearTimeout(retry);retry=setTimeout(wake,100);return;}if(!ws||ws.readyState===WebSocket.CLOSED){attempt=0;void connect();}}}
  void connect();watch=setInterval(()=>{if(ws&&performance.now()-receivedAt>12000&&(ws.readyState===WebSocket.OPEN||ws.readyState===WebSocket.CONNECTING)){markOffline('等待新画面，正在自动恢复…');ws.close();}},1000);
  window.addEventListener('online',wake);document.addEventListener('visibilitychange',wake);
  return()=>{disposed=true;generation++;pending=null;live.current=false;request?.abort();clearTimeout(retry);clearInterval(watch);ws?.close();window.removeEventListener('online',wake);document.removeEventListener('visibilitychange',wake);};
 },[deviceId,apiKey,accessRevision]);
 const english=locale==='en';const displayStatus=english?(/权限|凭证/.test(status)?'Access ended. Reconnect Studio.':/主动释放|已释放/.test(status)?'Connection released. Click Reconnect screen.':/后台/.test(status)?'Video paused while this tab is in the background.':/超时/.test(status)?'Phone video timed out. Reconnecting…':/视频|画面|新画面/.test(status)?'Waiting for live phone video. Reconnecting…':/正在连接/.test(status)?'Connecting to the live device…':status):status;
 return <><canvas {...canvasProps} ref={canvas} aria-label={english?'Live phone screen':'手机实时画面，可点击和拖动'} aria-disabled={!connected}
 onPointerDown={e=>{if(live.current)canvasProps.onPointerDown?.(e);}} onPointerUp={e=>{if(live.current)canvasProps.onPointerUp?.(e);}}
 onKeyDown={e=>{if(live.current)canvasProps.onKeyDown?.(e);}}
 style={{visibility:hasFrame?'visible':'hidden',opacity:connected?1:.45,pointerEvents:connected?'auto':'none'}}/>{!connected&&<div className="live-placeholder" role="status">{displayStatus}{hasFrame&&<small>{english?'Last received frame. Waiting for live video.':'显示的是中断前画面，暂不可操作'}</small>}</div>}{!hideIndicator&&<span className="live-indicator">{connected?(english?`● LIVE · ${fps||'…'} FPS · ${source.current==='USB高速画面'?'USB':'Compatible stream'}`:`● 实时 · ${fps||'…'} FPS · ${source.current} · 自动保持连接`):displayStatus}</span>}</>;
}
