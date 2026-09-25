"""Traceable direct Maps jobs and depth-compatible input batches."""
import hashlib
import json
from collections import defaultdict
from pathlib import Path
from urllib.parse import quote


def pilot_points(points, limit=15):
    groups=defaultdict(list)
    for point in points:
        groups[(point['zone'],point['depth'])].append(point)
    # Round robin across zones and density/depth strata, spread within each stratum.
    sampled=[]
    ordered=[v for _,v in sorted(groups.items())]
    for round_number in range(limit):
        for group in ordered:
            index=round_number*len(group)//limit
            point=group[index]
            if point not in sampled:
                sampled.append(point)
                if len(sampled)>=limit:
                    return sampled
    return sampled


def _terms(profiles, name):
    profile=profiles.get(name,[])
    if isinstance(profile,dict):
        return profile.get('queries',profile.get('terms',[]))
    return profile


def make_jobs(points, categories, pilot=False):
    profiles=categories.get('profiles',{})
    selected=pilot_points(points) if pilot else points
    jobs=[]
    for index,point in enumerate(selected):
        all_terms=list(dict.fromkeys(term for name in profiles for term in _terms(profiles,name)))
        if pilot:
            terms=all_terms
        elif categories.get('active_queries'):
            terms=categories['active_queries']
        else:
            primary=_terms(profiles,point.get('query_profile','FOOD_CORE'))
            # Broad anchor plus rotating terms preserve geographic variety without Cartesian explosion.
            count=int(categories.get('queries_per_point',4))
            terms=list(dict.fromkeys(primary[:1]+[all_terms[(index+j)%len(all_terms)] for j in range(max(0,count-1))])) if all_terms else []
        for term in terms:
            if not isinstance(term,str) or not term.strip() or any(ord(c)<32 for c in term) or '#!#' in term:
                raise ValueError('Queries must be nonempty single-line strings')
            depth=int(point['depth']); zoom=int(point['zoom'])
            if not 1<=depth<=10 or not 1<=zoom<=21:
                raise ValueError('Invalid job depth or zoom')
            job_id='J_'+hashlib.sha256(f"{point['point_id']}|{point['pass']}|{term}".encode()).hexdigest()[:24]
            url=f"https://www.google.com/maps/search/{quote(term,safe='')}/@{float(point['latitude']):.7f},{float(point['longitude']):.7f},{zoom}z"
            jobs.append({'job_id':job_id,'url':url,'point_id':point['point_id'],'zone':point['zone'],'scope':point['scope'],'query':term,'depth':depth,'zoom':zoom,'pass':point['pass']})
    if len({j['job_id'] for j in jobs})!=len(jobs):
        raise ValueError('Duplicate point/query job IDs')
    return jobs


def write_batches(jobs, directory, batch_size=50):
    if not 1<=int(batch_size)<=500:
        raise ValueError('batch_size must be 1–500')
    directory=Path(directory); directory.mkdir(parents=True,exist_ok=True)
    groups=defaultdict(list)
    for job in jobs:
        groups[job['depth']].append(job)
    batches=[]
    for depth,group in sorted(groups.items()):
        for start in range(0,len(group),int(batch_size)):
            chunk=group[start:start+int(batch_size)]
            batch_id=f'batch_{len(batches)+1:04d}'
            path=directory/f'{batch_id}.txt'
            path.write_text(''.join(f"{job['url']} #!# {job['job_id']}\n" for job in chunk),encoding='utf-8')
            batches.append({'batch_id':batch_id,'input':str(path.resolve()),'depth':depth,'jobs':chunk})
    (directory/'manifest.json').write_text(json.dumps(batches,ensure_ascii=False,indent=2),encoding='utf-8')
    return batches
