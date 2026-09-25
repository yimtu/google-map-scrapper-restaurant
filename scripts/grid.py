"""Deterministic density-specific grid, clipped to approved input geometry."""
import csv
import hashlib
import json
import math
from pathlib import Path
from scripts.territory import geometry_contains, contains

DEFAULTS = {
    'high': {'cell_km':0.5,'zoom':16,'depth':8,'query_profile':'FOOD_CORE'},
    'medium': {'cell_km':1.0,'zoom':16,'depth':7,'query_profile':'FOOD_CORE'},
    'periphery': {'cell_km':1.5,'zoom':15,'depth':5,'query_profile':'FOOD_CORE'},
    'rural': {'cell_km':2.0,'zoom':15,'depth':5,'query_profile':'FOOD_CORE'},
}
FIELDS = ['point_id','zone','scope','latitude','longitude','cell_km','zoom','depth','query_profile','pass']


def _profile_for_feature(props, coverage):
    """Select a spacing profile from subzone yield history, with density as fallback."""
    density = props['density']
    densities = coverage.get('densities', {})
    baseline = {**DEFAULTS[density], **densities.get(density, {})}
    adaptive = coverage.get('adaptive_grid', {})
    if not adaptive.get('enabled', False):
        return baseline

    history = coverage.get('historical_yields', {}).get(props['zone'])
    if history is None:
        return baseline
    if not isinstance(history, dict):
        raise ValueError('Historical yield entries must be objects keyed by zone')

    observations = history.get('observations', 0)
    results = history.get('results', 0)
    try:
        observations = int(observations)
        results = float(results)
    except (TypeError, ValueError) as exc:
        raise ValueError('Historical yield results and observations must be numeric') from exc
    if observations < 0 or results < 0:
        raise ValueError('Historical yield results and observations cannot be negative')
    if observations < int(adaptive.get('min_observations', 2)):
        return baseline

    high_yield = float(adaptive.get('high_yield', 80))
    medium_yield = float(adaptive.get('medium_yield', 30))
    if not 0 <= medium_yield <= high_yield:
        raise ValueError('Adaptive yield thresholds must satisfy 0 <= medium_yield <= high_yield')
    observed_yield = results / observations if observations else 0
    if observed_yield >= high_yield:
        selected = adaptive.get('high_profile', 'high')
    elif observed_yield >= medium_yield:
        selected = adaptive.get('medium_profile', 'medium')
    else:
        selected = adaptive.get('low_profile', 'periphery')
    if selected not in DEFAULTS:
        raise ValueError(f'Unknown adaptive grid profile: {selected}')
    return {**DEFAULTS[selected], **densities.get(selected, {})}


def _point(props, lat, lon, profile, pass_number):
    identifier = hashlib.sha256(f"{props['zone']}|{props['scope']}|{lat:.7f}|{lon:.7f}|{pass_number}".encode()).hexdigest()[:16]
    return {'point_id':f'P_{identifier}', 'zone':props['zone'],'scope':props['scope'],
            'latitude':round(lat,7),'longitude':round(lon,7),**profile,'pass':pass_number}


def generate_grid(territory, coverage, scope='AMG_FULL', pass_number=1):
    if not any(f['properties']['scope']==scope for f in territory['features']):
        raise ValueError(f'ONE-TIME HUMAN INPUT REQUIRED: explicit {scope} polygon missing')
    points = []
    occupied = set()
    limit = int(coverage.get('max_grid_points',100000))
    features = sorted(
        (feature for feature in territory['features'] if feature['properties'].get('scope') == scope),
        key=lambda f: DEFAULTS[f['properties']['density']]['cell_km'],
    )
    accepted_features = []
    for feature in features:
        props=feature['properties']
        profile=_profile_for_feature(props,coverage)
        cell=float(profile['cell_km'])
        if not 0.1 <= cell <= 20 or not 1 <= int(profile['depth']) <= 10:
            raise ValueError('cell_km must be 0.1–20 and depth 1–10')
        geom=feature['geometry']
        polygons=[geom['coordinates']] if geom['type']=='Polygon' else geom['coordinates']
        for polygon in polygons:
            xs=[p[0] for p in polygon[0]]; ys=[p[1] for p in polygon[0]]
            dy=cell/111.32
            dx=dy/max(.01,math.cos(math.radians((min(ys)+max(ys))/2)))
            if (max(xs)-min(xs))/dx * (max(ys)-min(ys))/dy > limit*4:
                raise ValueError('Territory grid too large; review geometry/coverage')
            offset=.5 if pass_number % 2 else .25
            lat=min(ys)+dy*offset
            while lat < max(ys):
                lon=min(xs)+dx*offset
                while lon < max(xs):
                    key=(round(lat,7),round(lon,7))
                    if key not in occupied and geometry_contains(geom,lat,lon) and not any(geometry_contains(g,lat,lon) for g in accepted_features):
                        points.append(_point(props,lat,lon,profile,pass_number)); occupied.add(key)
                        if len(points)>limit:
                            raise ValueError('Grid exceeds configured point limit')
                    lon+=dx
                lat+=dy
        accepted_features.append(geom)
    if not points:
        raise ValueError('No grid points inside territory; reduce cell_km or review polygons')
    return points


def refine_grid(points, counts, territory, coverage):
    result=[]; seen={(p['latitude'],p['longitude']) for p in points}
    threshold=coverage.get('refine_result_threshold',80)
    for p in points:
        if counts.get(p['point_id'],0)<threshold:
            continue
        profile={k:p[k] for k in ('cell_km','zoom','depth','query_profile')}
        dy=float(p['cell_km'])/111.32/4
        dx=dy/max(.01,math.cos(math.radians(float(p['latitude']))))
        for sy,sx in ((-1,-1),(-1,1),(1,-1),(1,1)):
            lat=round(float(p['latitude'])+sy*dy,7); lon=round(float(p['longitude'])+sx*dx,7)
            if (lat,lon) not in seen and contains(territory,lat,lon,p['scope']):
                result.append(_point(p,lat,lon,{**profile,'cell_km':float(p['cell_km'])/2},int(p['pass'])+1))
                seen.add((lat,lon))
    return result


refinement=refine_grid


def write_grid(points, csv_path, preview_path):
    csv_path,preview_path=Path(csv_path),Path(preview_path)
    csv_path.parent.mkdir(parents=True,exist_ok=True)
    preview_path.parent.mkdir(parents=True,exist_ok=True)
    with csv_path.open('w',newline='',encoding='utf-8-sig') as handle:
        writer=csv.DictWriter(handle,fieldnames=FIELDS); writer.writeheader(); writer.writerows(points)
    features=[{'type':'Feature','properties':p,'geometry':{'type':'Point','coordinates':[p['longitude'],p['latitude']]}} for p in points]
    preview_path.write_text(json.dumps({'type':'FeatureCollection','features':features},ensure_ascii=False),encoding='utf-8')
