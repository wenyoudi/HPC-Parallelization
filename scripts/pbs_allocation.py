#!/usr/bin/env python3
"""Verify PBS once, then reuse a job-bound snapshot with fresh local safety checks."""
import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import socket
import subprocess
import sys
import time

SNAPSHOT_ENV='VANDA_ALLOCATION_SNAPSHOT'
SNAPSHOT_SHA_ENV='VANDA_ALLOCATION_SHA256'
RESOURCE_PATTERN=r'(?m)^[ \t]*(Resource_List\.(?:ncpus|nodect|select|place|mem|walltime)|exec_host|exec_vnode|queue|job_state)[ \t]*=[ \t]*(.*)$'


def _context():
    job_id=os.environ.get('PBS_JOBID')
    nodefile=os.environ.get('PBS_NODEFILE')
    if not job_id or not nodefile or not Path(nodefile).is_file():
        raise RuntimeError('Run inside an allocated PBS compute job (PBS_JOBID/PBS_NODEFILE required)')
    content=Path(nodefile).read_bytes()
    nodes=set(content.decode().split())
    if len(nodes)!=1:
        raise RuntimeError('This experiment requires exactly one allocated node')
    host=socket.gethostname()
    node=next(iter(nodes)).split('.')[0].lower()
    # Usually no DNS lookup is needed; preserve the canonical-name fallback.
    if node!=host.split('.')[0].lower() and node!=socket.getfqdn().split('.')[0].lower():
        raise RuntimeError('Current host is not the allocated compute node; refusing login-node execution')
    return dict(job_id=job_id,hostname=host,nodes=sorted(nodes),
                nodefile_sha256=hashlib.sha256(content).hexdigest())


def _live_cpu_limits():
    affinity=sorted(os.sched_getaffinity(0)) if hasattr(os,'sched_getaffinity') else None
    physical=None
    if affinity:
        try:
            physical=len({((Path(f'/sys/devices/system/cpu/cpu{cpu}/topology')/'physical_package_id').read_text().strip(),
                           (Path(f'/sys/devices/system/cpu/cpu{cpu}/topology')/'core_id').read_text().strip()) for cpu in affinity})
        except OSError:
            pass
    return affinity,physical


def _check_budget(allocation,required_cpus):
    if required_cpus<1:
        raise RuntimeError('Required CPU count must be positive')
    resources=allocation.get('resources')
    if not isinstance(resources,dict) or resources.get('job_state')!='R':
        raise RuntimeError('PBS job was not verified as running')
    try:
        ncpus=int(resources['Resource_List.ncpus'])
    except (KeyError,TypeError,ValueError):
        raise RuntimeError('PBS did not report Resource_List.ncpus')
    if ncpus<1 or required_cpus>ncpus:
        raise RuntimeError('Requested benchmark CPUs exceed the PBS allocation')
    affinity=allocation.get('allowed_os_cpus')
    if affinity is not None and len(affinity)<required_cpus:
        raise RuntimeError('The job cpuset exposes fewer CPUs than this experiment requires')
    physical=allocation.get('visible_physical_cores')
    if physical is not None and physical<required_cpus:
        raise RuntimeError('The job cpuset exposes fewer physical cores than this experiment requires')


def _query_resources(job_id,attempts=3,timeout=15):
    reason=''
    for attempt in range(1,attempts+1):
        try:
            status=subprocess.run(['qstat','-f',job_id],capture_output=True,text=True,timeout=timeout)
            if status.returncode==0:
                return dict(re.findall(RESOURCE_PATTERN,status.stdout)),attempt
            reason=f'qstat returned exit {status.returncode}'
        except subprocess.TimeoutExpired:
            reason=f'qstat timed out after {timeout} seconds'
        except OSError as error:
            raise RuntimeError('Cannot execute qstat to verify the PBS allocation') from error
        if attempt<attempts:
            print(f'Allocation query {attempt}/{attempts}: {reason}; retrying.',file=sys.stderr,flush=True)
            time.sleep(attempt) # Bounded 1s/2s delays; worst-case timeout budget is 48s.
    raise RuntimeError(f'Cannot verify active PBS allocation after {attempts} attempts: {reason}')


def save_allocation_snapshot(path,allocation):
    """Write a new verified snapshot; never overwrite existing job evidence."""
    data=(json.dumps(allocation,indent=2)+'\n').encode()
    with Path(path).open('xb') as stream:
        stream.write(data)
    return hashlib.sha256(data).hexdigest()


def snapshot_environment(path,digest,base=None):
    env=dict(os.environ if base is None else base)
    env[SNAPSHOT_ENV]=str(Path(path).resolve())
    env[SNAPSHOT_SHA_ENV]=digest
    return env


def inspect_allocation(required_cpus,*,force_refresh=False):
    context=_context()
    path=os.environ.get(SNAPSHOT_ENV) if not force_refresh else None
    if path:
        try:
            raw=Path(path).read_bytes()
            expected=os.environ.get(SNAPSHOT_SHA_ENV,'')
            if not re.fullmatch(r'[0-9a-f]{64}',expected) or hashlib.sha256(raw).hexdigest()!=expected:
                raise RuntimeError('Allocation snapshot checksum is missing or mismatched')
            allocation=json.loads(raw)
        except (OSError,ValueError) as error:
            raise RuntimeError('Cannot read a valid allocation snapshot; no scheduler fallback is permitted') from error
        if (not isinstance(allocation,dict) or allocation.get('snapshot_version')!=1
                or allocation.get('verified_via')!='qstat -f' or not allocation.get('verified_at_utc')):
            raise RuntimeError('Allocation snapshot is not an initial verified PBS record')
        if (allocation.get('job_id')!=context['job_id']
                or not isinstance(allocation.get('hostname'),str)
                or allocation['hostname'].split('.')[0].lower()!=context['hostname'].split('.')[0].lower()
                or allocation.get('nodes')!=context['nodes']
                or allocation.get('nodefile_sha256')!=context['nodefile_sha256']):
            raise RuntimeError('Allocation snapshot belongs to a different PBS job, host or nodefile')
        cached_cpus=allocation.get('allowed_os_cpus')
        if cached_cpus is not None and (not isinstance(cached_cpus,list)
                or any(type(cpu) is not int or cpu<0 for cpu in cached_cpus)
                or len(set(cached_cpus))!=len(cached_cpus)):
            raise RuntimeError('Malformed cached CPU affinity')
        cached_physical=allocation.get('visible_physical_cores')
        if cached_physical is not None and (type(cached_physical) is not int or cached_physical<1):
            raise RuntimeError('Malformed cached physical-core count')
        _check_budget(allocation,required_cpus)
        affinity,physical=_live_cpu_limits()
        if cached_cpus is not None and (affinity is None or not set(affinity).issubset(cached_cpus)):
            raise RuntimeError('Live CPU affinity exceeds or cannot verify the startup allocation snapshot')
        if cached_physical is not None and physical is None:
            raise RuntimeError('Cannot recheck the physical-core limit captured at job startup')
        if cached_physical is not None:
            physical=min(physical,cached_physical)
        allocation.update(allowed_os_cpus=affinity,visible_physical_cores=physical,
                          requested_cpus=required_cpus,allocation_snapshot=str(Path(path).resolve()),
                          allocation_snapshot_sha256=expected)
        _check_budget(allocation,required_cpus)
        return allocation
    resources,attempts=_query_resources(context['job_id'])
    affinity,physical=_live_cpu_limits()
    allocation=dict(context,resources=resources,allowed_os_cpus=affinity,visible_physical_cores=physical,
        requested_cpus=required_cpus,snapshot_version=1,verified_via='qstat -f',
        verified_at_utc=dt.datetime.now(dt.timezone.utc).isoformat(),scheduler_query_attempts=attempts)
    _check_budget(allocation,required_cpus)
    return allocation


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--cpus',type=int,default=8)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--refresh',action='store_true',help='Initial job query; ignore any inherited snapshot')
    a=p.parse_args()
    allocation=inspect_allocation(a.cpus,force_refresh=a.refresh)
    save_allocation_snapshot(a.output,allocation)
    print(json.dumps(allocation))
