"use client";

import { RefreshCw, Smartphone } from 'lucide-react';
import LiveScreen from '../LiveScreen';
import type {Device} from '../types';
import {Badge} from '@/components/ui/badge';
import {Button} from '@/components/ui/button';
import {Card} from '@/components/ui/card';
import {Select, SelectContent, SelectItem, SelectTrigger, SelectValue} from '@/components/ui/select';

type PhonePanelProps={
  apiKey:string;
  device:string;
  devices:Device[];
  active:boolean;
  revision:number;
  onDeviceChange:(id:string)=>void;
  onReconnect:()=>void;
};

export function PhonePanel({apiKey,device,devices,active,revision,onDeviceChange,onReconnect}:PhonePanelProps){
  const selected=devices.find(item=>item.id===device);
  const online=Boolean(selected&&selected.online!==false);
  const ready=selected?.automation==='ready';

  return <Card className="phone-panel">
    <div className="phone-stage">
      <div className="phone-frame">
        <div className="phone-screen">
          {online?<LiveScreen deviceId={device} apiKey={apiKey} accessRevision={`${revision}:${selected?.automation}`} hideIndicator className="phone-screen-canvas"/>:<div className="phone-empty"><Smartphone aria-hidden="true"/><strong>{selected?'Phone is offline':'Connect your iPhone'}</strong><span>{selected?'Unlock the iPhone and restart WebDriverAgent to reconnect.':'Connect a phone by USB to see its live screen here.'}</span></div>}
        </div>
      </div>
    </div>

    <div className="phone-panel-footer">
      <div className="phone-footer-heading">
        <h2>Your iPhone</h2>
        {online&&<Badge variant="outline" className={`device-state ${ready?'is-ready':'is-view-only'}`}>
          <span aria-hidden="true" className="status-dot"/>{ready?'Ready':selected?.recovery?.phase==='starting'?'Recovering':selected?.automation==='checking'?'Checking':'Needs attention'}
        </Badge>}
      </div>
      <div className="phone-device-controls">
        <Select value={device||null} onValueChange={value=>onDeviceChange(value??'')} disabled={!devices.length||active}>
          <SelectTrigger className="phone-device-select" aria-label="Select phone">
            <Smartphone aria-hidden="true"/>
            <SelectValue placeholder="Waiting for a phone">
              {selected&&<>
                <span>{selected.name||selected.model}</span>
                {selected.online===false&&<Badge variant="outline" className="device-state is-offline">Offline</Badge>}
              </>}
            </SelectValue>
          </SelectTrigger>
          <SelectContent>
            {devices.map(item=><SelectItem value={item.id} key={item.id}>
              <span>{item.name||item.model}</span>
              {item.online===false&&<Badge variant="outline" className="device-state is-offline">Offline</Badge>}
            </SelectItem>)}
          </SelectContent>
        </Select>
        <Button type="button" variant="outline" size="icon" aria-label="Reconnect phone screen" title="Reconnect screen" onClick={onReconnect}>
          <RefreshCw aria-hidden="true"/>
        </Button>
      </div>
    </div>
  </Card>;
}
