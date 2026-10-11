#!/bin/bash
# Reuse the existing remaining-nine direct native CLI transport, unchanged model/settings.
set -euo pipefail
umask 077
cd "$(dirname -- "$0")"
sha256sum -c SHA256SUMS
/opt/stage11-stt-venv/bin/python -B ./verify-inputs.py --preflight
if [ "${1-}" = "--preflight" ] && [ "$#" -eq 1 ]; then
  exit 0
fi
if [ "$#" -ne 0 ]; then
  echo "Usage: $0 [--preflight]" >&2
  exit 2
fi
audio_bundle="$(pwd)"
audio_run_dir="$(mktemp -d /tmp/stage11-single-supplemental-result-XXXXXXXX)"
ssh_options=(
  -F /dev/null -T -i /root/.ssh/id_ed25519_stage11_hermes
  -o BatchMode=yes -o IdentitiesOnly=yes -o IdentityAgent=none
  -o StrictHostKeyChecking=yes
  -o UserKnownHostsFile=/root/.ssh/known_hosts_stage11_hermes
  -o GlobalKnownHostsFile=/dev/null -o UpdateHostKeys=no
  -o ConnectTimeout=10 -o ConnectionAttempts=1
  -o ServerAliveInterval=5 -o ServerAliveCountMax=2
  -o ForwardAgent=no -o ClearAllForwardings=yes
  -o ControlMaster=no -o ControlPath=none
)

# Stage a separate revised prompt in the existing temporary workspace.
remote_stage_command="$(python3 -B - <<'STAGE_COMMAND'
import shlex
code = """import hashlib, os, sys
from pathlib import Path
root = Path('/tmp/stage11-hermes-277-native-cmbcdsp5')
config = root / 'profiles/canary277/config.yaml'
prompt = root / 'work/supplemental13.prompt.a9992ce7f26eb761b47cd8a9cbdc7cf7dc003fa845bc09b0f9ebf582076d3e19.txt'
for target in (config, prompt):
    if any(p.is_symlink() for p in (target, *target.parents)):
        raise SystemExit('STOP: remote path symlink')
if hashlib.sha256(config.read_bytes()).hexdigest() != '45396316544977c241e10d1a9410ddd14898740ba28258b773c6daf9c27143db':
    raise SystemExit('STOP: temporary config changed')
raw = sys.stdin.buffer.read(128001)
digest = hashlib.sha256(raw).hexdigest()
if digest != 'a9992ce7f26eb761b47cd8a9cbdc7cf7dc003fa845bc09b0f9ebf582076d3e19':
    raise SystemExit('STOP: revised prompt SHA mismatch')
if prompt.exists():
    if prompt.read_bytes() != raw:
        raise SystemExit('STOP: remote revised prompt differs')
else:
    fd = os.open(prompt, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'wb') as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
if hashlib.sha256(prompt.read_bytes()).hexdigest() != digest:
    raise SystemExit('STOP: remote prompt readback mismatch')
print('PROMPT_STAGED_SHA256=' + digest)
"""
print('/usr/bin/python3 -B -c ' + shlex.quote(code))
STAGE_COMMAND
)"
ssh "${ssh_options[@]}" teddy@192.168.1.230 "$remote_stage_command" \
  < "$audio_bundle/supplemental13.prompt.txt" > "$audio_run_dir/prompt-staging.log"

ssh "${ssh_options[@]}" teddy@192.168.1.230 '/bin/bash --noprofile --norc -s' \
  > "$audio_run_dir/stdout.json" 2> "$audio_run_dir/stderr.log" <<'REMOTE'
set -euo pipefail
umask 077
export HERMES_HOME=/tmp/stage11-hermes-277-native-cmbcdsp5
export PATH=/home/teddy/.hermes/hermes-agent/venv/bin:/usr/local/bin:/usr/bin:/bin
cd "$HERMES_HOME/work"
/usr/bin/python3 -B - <<'PINS'
import hashlib
from pathlib import Path
pins = {
    '../profiles/canary277/config.yaml': '45396316544977c241e10d1a9410ddd14898740ba28258b773c6daf9c27143db',
    'supplemental13.prompt.a9992ce7f26eb761b47cd8a9cbdc7cf7dc003fa845bc09b0f9ebf582076d3e19.txt': 'a9992ce7f26eb761b47cd8a9cbdc7cf7dc003fa845bc09b0f9ebf582076d3e19',
}
for name, digest in pins.items():
    p = Path(name).absolute()
    if any(q.is_symlink() for q in (p, *p.parents)) or hashlib.sha256(p.read_bytes()).hexdigest() != digest:
        raise SystemExit('STOP: temporary config/prompt changed')
PINS
tools_check_file="$(mktemp "$HERMES_HOME/work/tools-check-XXXXXXXX.json")"
env -i HOME="$HOME" PATH="$PATH" LANG=C.UTF-8 \
  HERMES_HOME="$HERMES_HOME" PYTHONDONTWRITEBYTECODE=1 \
  /home/teddy/.local/bin/hermes --profile canary277 prompt-size --json > "$tools_check_file"
/usr/bin/python3 -B - "$tools_check_file" <<'ZERO'
import json, sys
from pathlib import Path
count = json.loads(Path(sys.argv[1]).read_bytes()).get('tools', {}).get('count')
if type(count) is not int or count != 0:
    raise SystemExit('STOP: native tools.count is not zero: ' + repr(count))
print('TOOLS_COUNT=0', file=sys.stderr)
ZERO
exec env -i HOME="$HOME" PATH="$PATH" LANG=C.UTF-8 \
  HERMES_HOME="$HERMES_HOME" PYTHONDONTWRITEBYTECODE=1 \
  /home/teddy/.local/bin/hermes --profile canary277 chat -Q --ignore-rules \
  --provider openai-codex --model gpt-5.6-luna --reasoning xhigh \
  --max-turns 1 -q "$(cat supplemental13.prompt.a9992ce7f26eb761b47cd8a9cbdc7cf7dc003fa845bc09b0f9ebf582076d3e19.txt)"
REMOTE

/opt/stage11-stt-venv/bin/python -B "$audio_bundle/verify-inputs.py" --validate "$audio_run_dir"
