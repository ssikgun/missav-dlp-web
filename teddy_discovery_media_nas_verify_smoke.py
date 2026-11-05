"""Offline only: exercise the fixed NAS inspection against temporary files."""
import json
import os
import pwd
import grp
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch
import teddy_discovery_media_nas_verify as verify

with tempfile.TemporaryDirectory() as raw:
    root = Path(raw) / 'library'
    folder = root / 'ABC' / 'ABC-123'
    folder.mkdir(parents=True)
    video = folder / 'ABC-123.ts'
    video.write_bytes(b'fixture')
    holding = {'relative_path':'ABC/ABC-123/ABC-123.ts', 'size_bytes':7}
    class Station:
        def stat_library(self, path):
            return {'size':7,'owner':pwd.getpwuid(os.getuid()).pw_name,'group':grp.getgrgid(os.getgid()).gr_name}
        def thumbnail_poster_exists(self, **kwargs):
            return (folder / 'cover.jpg').exists()
    station=Station()
    script=verify.REMOTE.replace("root='/volume1/video/video2/JAV'", 'root=' + repr(str(root)))
    def local_run(cmd, **kwargs):
        assert cmd[0]=='ssh' and cmd[-2]==verify.HOST
        return subprocess.run([sys.executable,'-c',script,holding['relative_path'],str(holding['size_bytes'])],
                              stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,timeout=5,check=False)
    assert verify.verify_existing_path('ABC-123',holding,station,run=local_run)
    (folder/'cover.jpg').write_bytes(b'existing')
    assert verify.verify_existing_path('ABC-123',holding,station,run=local_run)
    (folder/'cover.jpg').unlink()
    video.unlink(); video.symlink_to('/dev/null')
    assert not verify.verify_existing_path('ABC-123',holding,station,run=local_run)
    video.unlink();video.write_bytes(b'fixture')
    class Wrong(Station):
        def stat_library(self, path):
            return {'size':7,'owner':'wrong','group':grp.getgrgid(os.getgid()).gr_name}
    assert not verify.verify_existing_path('ABC-123',holding,Wrong(),run=local_run)
    assert not verify.verify_existing_path('ABC-123',{'relative_path':'../../bad','size_bytes':7},station,run=local_run)
    print('NAS_SSH_VERIFIER_OFFLINE=5 PASS / 0 FAIL')
