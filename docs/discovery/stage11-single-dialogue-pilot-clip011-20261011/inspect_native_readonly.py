"""Read native CLI/profile metadata only; never invokes Hermes."""
import json,shlex,subprocess
from pathlib import Path
root=Path(__file__).resolve().parent
program=r'''import hashlib,json,os,socket
from pathlib import Path
root=Path('/tmp/stage11-hermes-277-native-cmbcdsp5')
config=root/'profiles/canary277/config.yaml'
paths=[config,Path('/home/teddy/.local/bin/hermes'),Path('/home/teddy/.hermes/hermes-agent/hermes_cli/main.py'),Path('/home/teddy/.hermes/hermes-agent/venv/bin/python')]
values={}
for p in paths:
 values[str(p)]={'exists':p.exists(),'resolved':str(p.resolve()),'executable':os.access(p,os.X_OK)}
 if p.is_file():values[str(p)]['sha256']=hashlib.sha256(p.read_bytes()).hexdigest()
values['profile_path_has_symlink']=any(p.is_symlink() for p in (config,*config.parents))
print(json.dumps({'hostname':socket.gethostname(),'files':values,'temporary_work_exists':(root/'work').is_dir(),'hermes_invoked':False,'remote_writes':0},sort_keys=True))'''
options=['ssh','-F','/dev/null','-T','-i','/root/.ssh/id_ed25519_stage11_hermes','-o','BatchMode=yes','-o','IdentitiesOnly=yes','-o','IdentityAgent=none','-o','StrictHostKeyChecking=yes','-o','UserKnownHostsFile=/root/.ssh/known_hosts_stage11_hermes','-o','GlobalKnownHostsFile=/dev/null','-o','UpdateHostKeys=no','-o','ConnectTimeout=10','-o','ConnectionAttempts=1','-o','ForwardAgent=no','-o','ClearAllForwardings=yes','-o','ControlMaster=no','-o','ControlPath=none']
r=subprocess.run(options+['teddy@192.168.1.230','/usr/bin/python3 -B -c '+shlex.quote(program)],capture_output=True,timeout=30,check=True)
x=json.loads(r.stdout)
config=x['files']['/tmp/stage11-hermes-277-native-cmbcdsp5/profiles/canary277/config.yaml']
assert config['sha256']=='45396316544977c241e10d1a9410ddd14898740ba28258b773c6daf9c27143db'
assert not x['files']['profile_path_has_symlink'] and x['temporary_work_exists']
assert x['files']['/home/teddy/.local/bin/hermes']['executable']
x['readiness']='PASS_STATIC_PROFILE_CLI_PATHS';x['tools_count_runtime_check']='REQUIRED_IN_USER_RUNNER_NOT_EXECUTED_BY_CODEX'
(root/'native-readonly-audit.json').write_text(json.dumps(x,indent=2)+'\n')
print(x['readiness'],'native Hermes calls0, remote writes0')
