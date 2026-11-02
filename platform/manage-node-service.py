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
LABEL='com.phoneuse.local-node'
LEGACY_LABEL='local.qunkong.iphone-node'
DOMAIN=f'gui/{os.getuid()}'
PLIST=Path.home()/'Library/LaunchAgents'/f'{LABEL}.plist'
LEGACY_PLIST=Path.home()/'Library/LaunchAgents'/f'{LEGACY_LABEL}.plist'


def remove_legacy():
    # Earlier builds used LEGACY_LABEL. Remove it only when it runs this checkout,
    # never a service that belongs to another installation.
    try:
        legacy=plistlib.loads(LEGACY_PLIST.read_bytes())
    except (OSError,ValueError):
        return
    if legacy.get('Label')==LEGACY_LABEL and legacy.get('WorkingDirectory')==str(ROOT):
        subprocess.run(['launchctl','bootout',DOMAIN,str(LEGACY_PLIST)],check=False,capture_output=True)
        LEGACY_PLIST.unlink(missing_ok=True)


parser=argparse.ArgumentParser()
parser.add_argument('command',choices=['install','remove','status'])
args=parser.parse_args()
if args.command=='status':
    result=subprocess.run(['launchctl','print',DOMAIN+'/'+LABEL],capture_output=True,text=True)
    if result.returncode:
        legacy=subprocess.run(['launchctl','print',DOMAIN+'/'+LEGACY_LABEL],capture_output=True,text=True)
        print(f'Only the older {LEGACY_LABEL} service is loaded. Run install to replace it.' if legacy.returncode==0
              else 'The background service is not loaded.')
    else:
        for line in result.stdout.splitlines():
            if re.match(r'^\s*(state|pid|runs|last exit code) =',line):print(line.strip())
    raise SystemExit(result.returncode)
if args.command=='remove':
    remove_legacy()
    subprocess.run(['launchctl','bootout',DOMAIN,str(PLIST)],check=False,capture_output=True)
    PLIST.unlink(missing_ok=True)
    print('Automatic start removed. Phone apps, tasks and files were not deleted.')
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
    remove_legacy()
    if PLIST.exists():
        current=plistlib.loads(PLIST.read_bytes())
        if current.get('Label')!=LABEL:raise SystemExit('A different file with the same name exists; it was not overwritten.')
        subprocess.run(['launchctl','bootout',DOMAIN,str(PLIST)],capture_output=True)
    PLIST.write_bytes(plistlib.dumps(config));PLIST.chmod(0o600)
    subprocess.run(['launchctl','bootstrap',DOMAIN,str(PLIST)],check=True)
    print('The local API is now managed by launchd: it starts at login and restarts if it exits.')
