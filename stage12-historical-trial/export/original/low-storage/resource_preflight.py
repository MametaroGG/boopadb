"""Resource arithmetic only. No cleanup, paid runner or product-count cap."""
import math,os
from pathlib import Path

def inspect(path):
 s=os.statvfs(path)
 memory={}
 try:
  for line in Path('/proc/meminfo').read_text().splitlines():
   key,value=line.split(':',1)
   if key in ('MemTotal','MemAvailable','SwapTotal'):memory[key+'_bytes']=int(value.split()[0])*1024
 except OSError:pass
 cgroup={}
 for name in ('memory.max','memory.current','memory.peak'):
  path=Path('/sys/fs/cgroup')/name
  try:cgroup[name]=path.read_text().strip()
  except OSError:cgroup[name]=None
 return {'free_bytes':s.f_bavail*s.f_frsize,'free_inodes':s.f_favail,'filesystem_block_bytes':s.f_frsize,'host_memory':memory,'cgroup_memory':cgroup}

def preflight(path,components,safety_ratio=.25,required_memory_bytes=None,require_cgroup=False):
 if not isinstance(components,dict) or not components:raise ValueError('Explicit stage components required')
 if type(safety_ratio) not in (int,float) or not math.isfinite(safety_ratio) or not .25<=safety_ratio<=1:raise ValueError('Explicit safety ratio from25%to100% required')
 if type(required_memory_bytes)is not int or required_memory_bytes<=0:raise ValueError('Explicit positive memory budget required')
 for value in components.values():
  if set(value)!={'additional_bytes','additional_inodes','basis'} or any(type(value[k]) is not int or value[k]<0 for k in ('additional_bytes','additional_inodes')) or not value['basis']:raise ValueError('Invalid resource component')
 observed=inspect(path);required={key:math.ceil(sum(c['additional_'+key] for c in components.values())*(1+safety_ratio)) for key in ('bytes','inodes')}
 result={'schema':'boopa-stage-resource-preflight-v1','components':components,'safety_ratio':safety_ratio,'required_additional':required,'observed':observed,'runner_measurement':False}
 if observed['free_bytes']<required['bytes'] or observed['free_inodes']<required['inodes']:raise ValueError('Insufficient measured storage: '+str(result))
 mem=observed['host_memory'].get('MemAvailable_bytes');limit=observed['cgroup_memory']['memory.max'];used=observed['cgroup_memory']['memory.current']
 if require_cgroup and (limit is None or used is None):raise ValueError('Runtime memory allowance unavailable')
 budgets=[mem] if mem is not None else []
 if limit not in (None,'max') and used is not None:budgets.append(int(limit)-int(used))
 if required_memory_bytes is not None and (not budgets or min(budgets)<required_memory_bytes):raise ValueError('Insufficient observed memory for explicit local budget')
 result['finite_cgroup_memory_limit_available']=limit not in (None,'max') and used is not None
 result['effective_available_memory_bytes']=min(budgets) if budgets else None
 result['required_memory_bytes']=required_memory_bytes
 return result
