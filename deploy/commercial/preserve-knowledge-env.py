"""Preserve the running RAG settings when Compose recreates local services.

Credentials are passed directly in the child environment, never printed or
written into the repository. The indexer provides a recovery source if an
earlier recreation dropped the memory service's connection configuration.
"""
import json
import os
from pathlib import Path
import subprocess
import sys

SOURCE=Path('/mnt/c/Users/Benedict/Desktop/OminiDome/omnidome')


def container_environment(service):
    result=subprocess.run(['docker','inspect','omnidome-'+service+'-1'],capture_output=True,text=True)
    if result.returncode: return {}
    data=json.loads(result.stdout)[0]
    return dict(value.split('=',1) for value in data['Config']['Env'] if '=' in value)


environment=dict(os.environ)
memory=container_environment('tenant_memory')
indexer=container_environment('knowledge_indexer')
source=memory if memory.get('KNOWLEDGE_DB_URL') else indexer
if source.get('KNOWLEDGE_DB_URL'):
    for key in ('KNOWLEDGE_DB_URL','KNOWLEDGE_DB_ADMIN_URL','KNOWLEDGE_ENABLED','EMBEDDING_MODEL','EMBEDDING_DIM'):
        if source.get(key): environment[key]=source[key]
    environment['KNOWLEDGE_OLLAMA_URL']=source.get('OLLAMA_BASE_URL','http://ollama:11434')
environment['OD_KNOWLEDGE_ENV_READY']='1'
environment['COMPOSE_FILE']='docker-compose.yaml:docker-compose.override.yml:docker-compose.local.yml:'+str(SOURCE/'deploy/commercial/shadow.yml')
os.chdir('/home/benedict/omnidome')
if sys.argv[1:] == ['--deploy']:
    command=['bash',str(SOURCE/'deploy/commercial/deploy-platform-billing.sh')]
elif sys.argv[1:] == ['--restore-memory']:
    if not source.get('KNOWLEDGE_DB_URL'): raise SystemExit('No existing knowledge configuration could be recovered')
    command=['docker','compose','up','-d','--no-deps','--no-build','--force-recreate','tenant_memory']
else:
    raise SystemExit('Use --deploy or --restore-memory')
raise SystemExit(subprocess.run(command,env=environment).returncode)
