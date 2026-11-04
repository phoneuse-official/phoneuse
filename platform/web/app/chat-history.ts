export type ApiTask={
  id:string;
  device_id:string;
  task:string;
  status:string;
  stage?:string;
  current_action?:string;
  answer?:string;
  error?:string;
  device_calls?:number;
  created:number;
  finished?:number;
  elapsed_seconds?:number;
  model_calls?:number;
  failed_action?:string;
  error_code?:string;
  recovery_guidance?:string;
  recovery_observed?:boolean;
  program_step?:number;
  program_total?:number;
};

export type ChatTask=Omit<ApiTask,'device_id'>;

export type Conversation={
  id:string;
  title:string;
  createdAt:number;
  updatedAt:number;
  tasks:ChatTask[];
};

export type ChatHistory={
  activeId:string|null;
  conversations:Conversation[];
  deletedTaskIds?:string[];
};

export const CHAT_HISTORY_KEY='phoneuse-chat-history';

export async function historyScope(apiKey:string){
  const digest=await globalThis.crypto.subtle.digest('SHA-256',new TextEncoder().encode(apiKey));
  return Array.from(new Uint8Array(digest),byte=>byte.toString(16).padStart(2,'0')).join('');
}

function newId(){
  return globalThis.crypto?.randomUUID?.()||`${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

export function titleForTask(task:string){
  const title=task.trim().replace(/\s+/g,' ');
  return title.length>48?`${title.slice(0,47).trimEnd()}…`:title||'New chat';
}

export function createConversation(now=Date.now()):Conversation{
  return {id:newId(),title:'New chat',createdAt:now,updatedAt:now,tasks:[]};
}

function storedTask(task:ApiTask):ChatTask{
  const {device_id,...stored}=task;
  return stored;
}

function sameTask(left:ChatTask,right:ChatTask){
  return left.id===right.id&&left.task===right.task&&left.status===right.status&&left.stage===right.stage&&left.current_action===right.current_action&&left.answer===right.answer&&left.error===right.error&&left.device_calls===right.device_calls&&left.finished===right.finished&&left.model_calls===right.model_calls&&left.program_step===right.program_step&&left.program_total===right.program_total&&left.elapsed_seconds===right.elapsed_seconds&&left.failed_action===right.failed_action&&left.error_code===right.error_code&&left.recovery_guidance===right.recovery_guidance&&left.recovery_observed===right.recovery_observed;
}

function fromTask(task:ApiTask):Conversation{
  const createdAt=task.created*1000;
  return {id:newId(),title:titleForTask(task.task),createdAt,updatedAt:Math.max(createdAt,task.finished?task.finished*1000:createdAt),tasks:[storedTask(task)]};
}

function isObject(value:unknown):value is Record<string,unknown>{
  return Boolean(value)&&typeof value==='object'&&!Array.isArray(value);
}

function parseTask(value:unknown):ChatTask|null{
  if(!isObject(value)||typeof value.id!=='string'||typeof value.task!=='string'||typeof value.status!=='string'||typeof value.created!=='number')return null;
  return {
    id:value.id,
    task:value.task,
    status:value.status,
    created:value.created,
    ...(typeof value.stage==='string'?{stage:value.stage}:{}),
    ...(typeof value.current_action==='string'?{current_action:value.current_action}:{}),
    ...(typeof value.answer==='string'?{answer:value.answer}:{}),
    ...(typeof value.error==='string'?{error:value.error}:{}),
    ...(typeof value.device_calls==='number'?{device_calls:value.device_calls}:{}),
    ...(typeof value.finished==='number'?{finished:value.finished}:{}),
    ...Object.fromEntries(['elapsed_seconds','model_calls','program_step','program_total'].filter(key=>typeof value[key]==='number'&&Number.isFinite(value[key])).map(key=>[key,value[key]])),
    ...Object.fromEntries(['failed_action','error_code','recovery_guidance'].filter(key=>typeof value[key]==='string').map(key=>[key,value[key]])),
    ...(typeof value.recovery_observed==='boolean'?{recovery_observed:value.recovery_observed}:{}),
  };
}

function parseConversation(value:unknown):Conversation|null{
  if(!isObject(value)||typeof value.id!=='string'||typeof value.title!=='string'||typeof value.createdAt!=='number'||typeof value.updatedAt!=='number'||!Array.isArray(value.tasks))return null;
  const tasks=value.tasks.map(parseTask);
  if(tasks.some(task=>task===null))return null;
  return {id:value.id,title:value.title,createdAt:value.createdAt,updatedAt:value.updatedAt,tasks:tasks as ChatTask[]};
}

export function loadChatHistory(storage:Pick<Storage,'getItem'>,scope:string):ChatHistory{
  try{
    const raw=storage.getItem(`${CHAT_HISTORY_KEY}:${scope}`);
    if(!raw)return {activeId:null,conversations:[]};
    const value:unknown=JSON.parse(raw);
    if(!isObject(value)||!Array.isArray(value.conversations))return {activeId:null,conversations:[]};
    const conversations=value.conversations.map(parseConversation).filter((item):item is Conversation=>item!==null);
    const activeId=typeof value.activeId==='string'&&conversations.some(item=>item.id===value.activeId)?value.activeId:null;
    const deletedTaskIds=Array.isArray(value.deletedTaskIds)?value.deletedTaskIds.filter((id):id is string=>typeof id==='string'):[];
    return {activeId,conversations,deletedTaskIds};
  }catch{
    return {activeId:null,conversations:[]};
  }
}

export function saveChatHistory(storage:Pick<Storage,'setItem'>,history:ChatHistory,scope:string){
  storage.setItem(`${CHAT_HISTORY_KEY}:${scope}`,JSON.stringify(history));
}

export function addTaskToConversation(conversations:Conversation[],task:ApiTask,conversationId:string|null):Conversation[]{
  const stored=storedTask(task);
  const existing=conversations.findIndex(item=>item.tasks.some(message=>message.id===task.id));
  const target=conversations.findIndex(item=>item.id===conversationId);
  // A poll can discover a submitted task before its POST response assigns its chat.
  if(existing>=0&&target>=0&&existing!==target){
    const source=conversations[existing];
    const remaining=source.tasks.filter(message=>message.id!==task.id);
    const moved=conversations.flatMap((item,index)=>index!==existing?[item]:remaining.length?[{...item,tasks:remaining}]:[]);
    return addTaskToConversation(moved,task,conversationId);
  }
  if(existing>=0){
    const conversation=conversations[existing];
    const tasks=conversation.tasks.map(message=>message.id===task.id?stored:message);
    if(conversation.tasks.every((message,index)=>sameTask(message,tasks[index])))return conversations;
    return conversations.map((item,index)=>index===existing?{...item,tasks,
      updatedAt:Math.max(item.updatedAt,task.finished?task.finished*1000:task.created*1000)}:item);
  }
  if(target<0)return [...conversations,fromTask(task)];
  return conversations.map((item,index)=>index===target?{
    ...item,
    title:item.tasks.length?item.title:titleForTask(task.task),
    updatedAt:Math.max(item.updatedAt,task.finished?task.finished*1000:task.created*1000),
    tasks:[...item.tasks,stored],
  }:item);
}

export function reconcileTasks(conversations:Conversation[],tasks:ApiTask[],deletedTaskIds:ReadonlySet<string>=new Set()):Conversation[]{
  let next=conversations;
  for(const task of tasks){
    if(!deletedTaskIds.has(task.id))next=addTaskToConversation(next,task,null);
  }
  const liveIds=new Set(tasks.map(task=>task.id));
  return next.map(conversation=>{
    let changed=false;
    const messages=conversation.tasks.map(task=>{
      if(task.status!=='running'||liveIds.has(task.id))return task;
      changed=true;
      return {...task,status:'interrupted',stage:undefined,current_action:undefined,error:'This task stopped when PhoneUse restarted. Its result may be incomplete.'};
    });
    return changed?{...conversation,tasks:messages}:conversation;
  });
}
