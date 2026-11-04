const KEY='phoneuse-api-key';

export function forgetRejectedKey(storage:Pick<Storage,'getItem'|'removeItem'>,rejectedKey:string){
  // Another tab may have saved a newer connection since this tab authenticated.
  if(storage.getItem(KEY)===rejectedKey)storage.removeItem(KEY);
}
