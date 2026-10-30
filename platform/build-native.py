"""Build local macOS USB screen helpers with Command Line Tools (no Xcode app required)."""
import os,subprocess
from pathlib import Path
root=Path(__file__).resolve().parent
compiler='/Library/Developer/CommandLineTools/usr/bin/clang'
sdk='/Library/Developer/CommandLineTools/SDKs/MacOSX.sdk'
out=root/'.state/bin';out.mkdir(parents=True,exist_ok=True,mode=0o700)
for name in ['probe-capture','capture-phone']:
 command=[compiler,'-fobjc-arc','-O2','-isysroot',sdk]
 for framework in ['Foundation','AVFoundation','CoreMediaIO','CoreImage','CoreMedia','CoreVideo','CoreGraphics','ImageIO']:command+=['-framework',framework]
 subprocess.run(command+[str(root/'native'/f'{name}.m'),'-o',str(out/(name+'.next'))],check=True,env={**os.environ,'DEVELOPER_DIR':'/Library/Developer/CommandLineTools'})
 (out/(name+'.next')).replace(out/name)
 print('Built',name)
