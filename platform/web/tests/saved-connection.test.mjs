import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import test from 'node:test';
import ts from 'typescript';

const source=await readFile(new URL('../app/saved-connection.ts',import.meta.url),'utf8');
const javascript=ts.transpileModule(source,{compilerOptions:{module:ts.ModuleKind.ESNext,target:ts.ScriptTarget.ES2022}}).outputText;
const {forgetRejectedKey}=await import(`data:text/javascript;base64,${Buffer.from(javascript).toString('base64')}`);

function storage(value){
  const items=new Map(value?[['phoneuse-api-key',value]]:[]);
  return {getItem:key=>items.get(key)??null,removeItem:key=>items.delete(key)};
}

test('a stale tab cannot erase another tab’s newer saved connection',()=>{
  const shared=storage('mock-new-key');
  const staleTab=storage('mock-old-key');
  forgetRejectedKey(staleTab,'mock-old-key');
  forgetRejectedKey(shared,'mock-old-key');
  assert.equal(staleTab.getItem('phoneuse-api-key'),null);
  assert.equal(shared.getItem('phoneuse-api-key'),'mock-new-key');
});

test('the rejected saved connection is removed',()=>{
  const shared=storage('mock-rejected-key');
  forgetRejectedKey(shared,'mock-rejected-key');
  assert.equal(shared.getItem('phoneuse-api-key'),null);
});

test('an empty saved connection stays empty',()=>{
  const shared=storage();
  forgetRejectedKey(shared,'mock-rejected-key');
  assert.equal(shared.getItem('phoneuse-api-key'),null);
});
