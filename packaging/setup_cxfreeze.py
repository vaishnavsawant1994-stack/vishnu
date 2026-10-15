import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from cx_Freeze import Executable, setup

include_files=[]
if (ROOT/'.rea').is_dir():include_files.append((str(ROOT/'.rea'),'lib/.rea'))
setup(name='PersonalAI',version='0.6.0',description='Vishnu desktop runtime',executables=[Executable(str(ROOT/'app/main.py'),base='gui',target_name='PersonalAI.exe')],options={'build_exe':{'path':[str(ROOT),*sys.path],'packages':['app','agent','automation','browser','core','dashboard','desktop','devices','integrations','memory','models','security','server','tools','ui','updates','vision','voice'],'include_files':include_files,'zip_exclude_packages':['integrations']},'bdist_msi':{'upgrade_code':'{9D22239D-EC32-4D45-BA7B-E967A8121D65}'}})
