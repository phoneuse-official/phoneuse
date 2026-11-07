import type {Device} from './types';

export function selectAvailableDevice(devices:Device[],currentId:string):string{
  if(devices.some(device=>device.id===currentId&&device.online===true))return currentId;
  return devices.find(device=>device.online===true&&device.automation==='ready')?.id
    ??devices.find(device=>device.online===true)?.id??currentId;
}
