"""Copy only the configured IoT encryption key to the WSL runtime; never print it."""
import json
import subprocess
from pathlib import Path
from dotenv import dotenv_values

root = Path(__file__).resolve().parents[1]
key = dotenv_values(root / '.env').get('IOT_TOKEN_ENCRYPTION_KEY')
if not key:
    raise SystemExit('IOT_TOKEN_ENCRYPTION_KEY is missing')
program = '''import json,sys
from pathlib import Path
key=json.loads(sys.stdin.read())
p=Path('/home/benedict/omnidome/.env')
lines=p.read_text().splitlines()
existing=[line.split('=',1)[1].strip() for line in lines if line.startswith('IOT_TOKEN_ENCRYPTION_KEY=')]
if existing and existing[0] and existing[0]!=key:
    raise SystemExit('Runtime IoT key differs; refusing to replace it')
lines=[line for line in lines if not line.startswith('IOT_TOKEN_ENCRYPTION_KEY=')]
lines.append('IOT_TOKEN_ENCRYPTION_KEY='+key)
p.write_text('\\n'.join(lines)+'\\n')
p.chmod(0o600)
print('Runtime IoT key configured')
'''
subprocess.run(['wsl','-d','Ubuntu-26.04','--','python3','-c',program], input=json.dumps(key), text=True, check=True)
