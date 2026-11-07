import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import test from 'node:test';
import ts from 'typescript';

const source=await readFile(new URL('../app/device-selection.ts',import.meta.url),'utf8');
const javascript=ts.transpileModule(source,{compilerOptions:{module:ts.ModuleKind.ESNext,target:ts.ScriptTarget.ES2022}}).outputText;
const {selectAvailableDevice}=await import(`data:text/javascript;base64,${Buffer.from(javascript).toString('base64')}`);

const devices=[
  {id:'stale',online:false},
  {id:'checking',online:null},
  {id:'connected',online:true},
  {id:'also-connected',online:true},
];

test('selects a detected device when no selected device is available',()=>{
  assert.equal(selectAvailableDevice(devices,'stale'),'connected');
});

test('keeps the selected device while it remains available',()=>{
  assert.equal(selectAvailableDevice(devices,'also-connected'),'also-connected');
});

test('waits for a detected device instead of selecting a cached unknown device',()=>{
  assert.equal(selectAvailableDevice(devices.slice(0,2),''),'');
});

test('keeps the current selection when no device is available',()=>{
  assert.equal(selectAvailableDevice(devices.slice(0,2),'stale'),'stale');
});

test('prefers an online ready device on initial load or replacement',()=>{
  const candidates=[
    {id:'unavailable',online:true,automation:'not_running'},
    {id:'offline-ready',online:false,automation:'ready'},
    {id:'ready',online:true,automation:'ready'},
  ];
  assert.equal(selectAvailableDevice(candidates,''),'ready');
  assert.equal(selectAvailableDevice(candidates,'stale'),'ready');
  assert.equal(selectAvailableDevice(candidates,'unavailable'),'unavailable');
});
