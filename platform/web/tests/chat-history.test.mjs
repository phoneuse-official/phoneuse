import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import test from 'node:test';
import ts from 'typescript';

const source=await readFile(new URL('../app/chat-history.ts',import.meta.url),'utf8');
const javascript=ts.transpileModule(source,{compilerOptions:{module:ts.ModuleKind.ESNext,target:ts.ScriptTarget.ES2022}}).outputText;
const {addTaskToConversation,createConversation,historyScope,loadChatHistory,reconcileTasks,saveChatHistory}=await import(`data:text/javascript;base64,${Buffer.from(javascript).toString('base64')}`);
const task={id:'mock-task',device_id:'mock-device',task:'Read the page',status:'running',created:2};

function storage(){
  const values=new Map();
  return {values,getItem:key=>values.get(key)??null,setItem:(key,value)=>values.set(key,value)};
}

test('deleted chats stay deleted after polling and reloading',()=>{
  const cache=storage();
  saveChatHistory(cache,{activeId:null,conversations:[],deletedTaskIds:[task.id]},'owner');
  const saved=loadChatHistory(cache,'owner');
  assert.deepEqual(reconcileTasks(saved.conversations,[task],new Set(saved.deletedTaskIds)),[]);
});

test('POST assignment wins when polling discovers a task first',()=>{
  const intended=createConversation();
  const polled=reconcileTasks([intended],[task]);
  assert.equal(polled.length,2);
  const assigned=addTaskToConversation(polled,task,intended.id);
  assert.equal(assigned.length,1);
  assert.equal(assigned[0].id,intended.id);
  assert.equal(assigned[0].tasks[0].id,task.id);
});

test('moving a task preserves other messages in its previous chat',()=>{
  const intended=createConversation();
  const polled=reconcileTasks([intended],[task]);
  const sourceId=polled.find(chat=>chat.id!==intended.id).id;
  const withOther=addTaskToConversation(polled,{...task,id:'other'},sourceId);
  const assigned=addTaskToConversation(withOther,task,intended.id);
  assert.deepEqual(assigned.find(chat=>chat.id===sourceId).tasks.map(item=>item.id),['other']);
});

test('completion updates conversation activity time',()=>{
  const initial=reconcileTasks([],[task]);
  const completed=reconcileTasks(initial,[{...task,status:'model_reported_result',finished:100}]);
  assert.equal(completed[0].updatedAt,100000);
});

test('credential caches are isolated and do not store raw API keys',async()=>{
  const cache=storage();
  const scopeA=await historyScope('mock-owner-a');
  const scopeB=await historyScope('mock-owner-b');
  assert.notEqual(scopeA,scopeB);
  assert.equal(scopeA.length,64);
  saveChatHistory(cache,{activeId:null,conversations:reconcileTasks([],[task])},scopeA);
  assert.equal(loadChatHistory(cache,scopeA).conversations.length,1);
  assert.equal(loadChatHistory(cache,scopeB).conversations.length,0);
  assert.ok([...cache.values.keys()].every(key=>!key.includes('mock-owner')));
});

test('unscoped legacy history is never opened for a credential',()=>{
  const cache=storage();
  cache.setItem('phoneuse-chat-history',JSON.stringify({conversations:reconcileTasks([],[task])}));
  assert.equal(loadChatHistory(cache,'authenticated-owner').conversations.length,0);
});
