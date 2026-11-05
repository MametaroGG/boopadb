"""Private, separately executed source derivation. No network or credentials."""
import argparse
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import stream_source as source


def run(request_path, expected_sha256, output):
    request_path=Path(request_path)
    raw=source.read_anchored(request_path.parent,request_path.name,16*1024**2)
    if source.sha(raw)!=expected_sha256:raise ValueError('Private source request changed')
    request=source.strict_json(raw)
    output=Path(output);output.mkdir()
    evidence=output/'evidence';evidence.mkdir()
    binding=source.Binding(**request['binding'])
    # Read local compressed input through an anchored no-follow descriptor.
    from contextlib import ExitStack
    import os,stat
    path=Path(request['archive_path']);root=source.safe_root(path.parent)
    directory=os.open(root,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
    try:
        leaf=os.open(path.name,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=directory)
        with os.fdopen(leaf,'rb') as stream:
            if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):raise ValueError('Regular source archive required')
            result=source.prepare(stream,binding=binding,commit_raw=json.dumps(request['commit'],sort_keys=True,separators=(',',':'),allow_nan=False).encode(),root_raw=json.dumps(request['root'],sort_keys=True,separators=(',',':'),allow_nan=False).encode(),producer_raw=bytes.fromhex(request['producer_raw_hex']),inventory_raw=None,attestation_raw=None,derive_claim=request['derive_claim'],evidence_output=evidence,output=output/'prepared',limits=source.Limits(**request['limits']))
    finally:os.close(directory)
    (output/'source-result.json').write_text(json.dumps(result,sort_keys=True,separators=(',',':'),allow_nan=False)+'\n')
    return result

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--request',required=True);p.add_argument('--sha256',required=True);p.add_argument('--output',required=True);a=p.parse_args()
    print(json.dumps(run(a.request,a.sha256,a.output),sort_keys=True,separators=(',',':'),allow_nan=False))
