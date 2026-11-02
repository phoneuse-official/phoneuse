"use client";

import {useMemo,useState} from 'react';
import {MessageSquareText,Plus,Search,Trash2} from 'lucide-react';
import type {Conversation} from '../chat-history';
import {Button} from '@/components/ui/button';

type Props={
  conversations:Conversation[];
  activeId:string|null;
  onNewChat:()=>void;
  onSelect:(id:string)=>void;
  onDelete:(id:string)=>void;
};

function sectionFor(timestamp:number,now:number){
  const today=new Date(now);today.setHours(0,0,0,0);
  if(timestamp>=today.getTime())return 'Today';
  const weekStart=new Date(today);weekStart.setDate(weekStart.getDate()-6);
  return timestamp>=weekStart.getTime()?'Previous 7 days':'Earlier';
}

export function ChatHistorySidebar({conversations,activeId,onNewChat,onSelect,onDelete}:Props){
  const [query,setQuery]=useState('');
  const groups=useMemo(()=>{
    const now=Date.now();
    const sections=['Today','Previous 7 days','Earlier'];
    const filtered=conversations
      .filter(item=>item.title.toLowerCase().includes(query.trim().toLowerCase()))
      .sort((left,right)=>right.updatedAt-left.updatedAt);
    return sections.map(title=>({title,items:filtered.filter(item=>sectionFor(item.updatedAt,now)===title)})).filter(group=>group.items.length);
  },[conversations,query]);

  return <nav className="chat-history" aria-label="Chat history">
    <div className="history-top">
      <Button type="button" variant="outline" className="new-chat-button" onClick={onNewChat}><Plus aria-hidden="true"/>New chat</Button>
      <label className="history-search">
        <Search aria-hidden="true"/>
        <input type="search" aria-label="Search chats" placeholder="Search chats" value={query} onChange={event=>setQuery(event.target.value)}/>
      </label>
    </div>
    <div className="history-list">
      {groups.map(group=><section className="history-group" key={group.title} aria-label={group.title}>
        <h2>{group.title}</h2>
        {group.items.map(conversation=>{
          const running=conversation.tasks.some(task=>task.status==='running');
          const selected=conversation.id===activeId;
          return <div className={`history-row${selected?' is-active':''}`} key={conversation.id}>
            <button type="button" className="history-select" aria-current={selected?'page':undefined} onClick={()=>onSelect(conversation.id)}>
              <MessageSquareText aria-hidden="true"/>
              <span>{conversation.title}</span>
            </button>
            <Button type="button" variant="ghost" size="icon-sm" className="history-delete" aria-label={`Delete chat: ${conversation.title}`} title="Delete chat" disabled={running} onClick={()=>onDelete(conversation.id)}>
              <Trash2 aria-hidden="true"/>
            </Button>
          </div>;
        })}
      </section>)}
      {!groups.length&&<p className="history-empty">{query?'No matching chats':'Your chats will appear here'}</p>}
    </div>
    <p className="history-privacy">Chat history is stored in this browser.</p>
  </nav>;
}
