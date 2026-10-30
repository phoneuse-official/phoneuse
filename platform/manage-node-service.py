"""Install/remove the current user's launchd service for the local API and WDA supervisor."""
import argparse
import json
import os
import plistlib
import re
import subprocess
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parent
LABEL='local.qunkong.iphone-node'
DOMAIN=f'gui/{os.getuid()}'
PLIST=Path.home()/'Library/LaunchAgents'/f'{LABEL}.plist'
parser=argparse.ArgumentParser()
parser.add_argument('command',choices=['install','remove','status'])
args=parser.parse_args()
if args.command=='status':
    result=subprocess.run(['launchctl','print',DOMAIN+'/'+LABEL],capture_output=True,text=True)
    if result.returncode:
        print('节点后台服务未加载')
    else:
        for line in result.stdout.splitlines():
            if re.match(r'^\s*(state|pid|runs|last exit code) =',line):print(line.strip())
    raise SystemExit(result.returncode)
if args.command=='remove':
    subprocess.run(['launchctl','bootout',DOMAIN,str(PLIST)],check=False,capture_output=True)
    PLIST.unlink(missing_ok=True)
    print('已移除自动启动；手机应用、任务和文件未删除。')
else:
    executable=ROOT.parent/'.venv/bin/python'
    state=ROOT/'.state';state.mkdir(exist_ok=True,mode=0o700)
    log_config=state/'node-logging.json'
    log_config.write_text(json.dumps({'version':1,'disable_existing_loggers':False,
        'formatters':{'plain':{'format':'%(asctime)s %(levelname)s %(name)s %(message)s'}},
        'handlers':{'node':{'class':'logging.handlers.RotatingFileHandler','filename':str(state/'node-service.log'),
            'maxBytes':2097152,'backupCount':1,'formatter':'plain'}},
        'loggers':{'uvicorn':{'handlers':['node'],'level':'INFO','propagate':False},
                   'uvicorn.error':{'handlers':['node'],'level':'INFO','propagate':False},
                   'uvicorn.access':{'handlers':[],'propagate':False}},
        'root':{'handlers':['node'],'level':'WARNING'}}))
    log_config.chmod(0o600)
    config={'Label':LABEL,'ProgramArguments':[str(executable),'-m','uvicorn','backend.api:app','--host','127.0.0.1','--port','8765','--ws-max-size','4096','--ws-per-message-deflate','false','--no-access-log','--log-config',str(log_config)],
        'WorkingDirectory':str(ROOT),'RunAtLoad':True,'KeepAlive':True,'ThrottleInterval':10,
        'EnvironmentVariables':{'PYTHONUNBUFFERED':'1','PATH':'/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin'},
        'StandardOutPath':'/dev/null','StandardErrorPath':str(state/'node-bootstrap.log'),
        'ProcessType':'Interactive','ExitTimeOut':20}
    PLIST.parent.mkdir(parents=True,exist_ok=True)
    if PLIST.exists():
        current=plistlib.loads(PLIST.read_bytes())
        if current.get('Label')!=LABEL:raise SystemExit('同名文件内容不符，未覆盖')
        subprocess.run(['launchctl','bootout',DOMAIN,str(PLIST)],capture_output=True)
    PLIST.write_bytes(plistlib.dumps(config));PLIST.chmod(0o600)
    subprocess.run(['launchctl','bootstrap',DOMAIN,str(PLIST)],check=True)
    print('本机节点已由 launchd 管理：登录时启动，进程退出后恢复。')
