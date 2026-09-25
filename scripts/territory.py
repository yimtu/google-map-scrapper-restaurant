"""Validated local territory imports; no implied production boundary."""
import json
import math
import xml.etree.ElementTree as ET
import zipfile
from datetime import datetime, timezone
from pathlib import Path

SCOPES = {'CORE_GDL', 'CORE_PERIFERICO', 'URBAN_AMG', 'AMG_FULL'}
DENSITIES = {'high', 'medium', 'periphery', 'rural'}
MAX_BYTES = 20_000_000


def _validate_geometry(geometry):
    kind = geometry.get('type')
    if kind not in ('Polygon', 'MultiPolygon'):
        raise ValueError('Territory must contain only Polygon or MultiPolygon geometries')
    polygons = [geometry['coordinates']] if kind == 'Polygon' else geometry['coordinates']
    if not polygons:
        raise ValueError('Empty territory geometry')
    for polygon in polygons:
        if not polygon:
            raise ValueError('Empty polygon')
        for ring in polygon:
            if len(ring) < 4 or ring[0][:2] != ring[-1][:2]:
                raise ValueError('Polygon rings must be closed and have at least four coordinates')
            for point in ring:
                if len(point) < 2 or any(isinstance(x, bool) or not isinstance(x, (int, float)) or not math.isfinite(x) for x in point[:2]):
                    raise ValueError('Invalid polygon coordinate')
                if not -180 <= point[0] <= 180 or not -90 <= point[1] <= 90:
                    raise ValueError('Coordinate out of longitude/latitude range')
            area = sum(a[0]*b[1]-b[0]*a[1] for a,b in zip(ring,ring[1:]))
            if abs(area) < 1e-12:
                raise ValueError('Degenerate polygon ring')
    return geometry


def _kml(data):
    if b'<!DOCTYPE' in data.upper() or b'<!ENTITY' in data.upper():
        raise ValueError('DTD and XML entities are not allowed')
    root = ET.fromstring(data)
    for element in root.iter():
        element.tag = element.tag.rsplit('}', 1)[-1]
    features = []
    for item in root.iter('Placemark'):
        props = {'zone': item.findtext('name') or f'ZONE_{len(features)+1}'}
        for field in item.findall('.//ExtendedData/Data'):
            props[field.get('name')] = field.findtext('value')
        for field in item.findall('.//SimpleData'):
            props[field.get('name')] = field.text
        polygons = []
        for polygon in item.iter('Polygon'):
            rings = []
            for boundary in ['outerBoundaryIs', 'innerBoundaryIs']:
                for ring in polygon.findall(f'{boundary}/LinearRing/coordinates'):
                    rings.append([[float(x) for x in pair.split(',')[:2]] for pair in (ring.text or '').split()])
            polygons.append(rings)
        if polygons:
            geometry = {'type': 'Polygon', 'coordinates': polygons[0]} if len(polygons)==1 else {'type':'MultiPolygon','coordinates':polygons}
            features.append({'type':'Feature','properties':props,'geometry':geometry})
    return {'type':'FeatureCollection','features':features}


def _read(source):
    if source.stat().st_size > MAX_BYTES:
        raise ValueError('Territory file exceeds 20 MB')
    if source.suffix.lower() == '.kmz':
        with zipfile.ZipFile(source) as archive:
            files = [f for f in archive.infolist() if f.filename.lower().endswith('.kml')]
            if len(files) != 1 or files[0].file_size > MAX_BYTES:
                raise ValueError('KMZ must contain one KML smaller than 20 MB')
            return _kml(archive.read(files[0]))
    data = source.read_bytes()
    if source.suffix.lower() == '.kml':
        return _kml(data)
    if source.suffix.lower() not in ('.geojson', '.json'):
        raise ValueError('Use a .geojson, .kml or .kmz file')
    return json.loads(data.decode('utf-8-sig'))


def import_territory(source, destination, scope=None, density='high', approved=False):
    source, destination = Path(source), Path(destination)
    geo = _read(source)
    if geo.get('type') == 'Feature':
        geo = {'type':'FeatureCollection', 'features':[geo]}
    if geo.get('type') != 'FeatureCollection' or not geo.get('features'):
        raise ValueError('Territory needs at least one polygon')
    features = []
    for i, feature in enumerate(geo['features']):
        props = dict(feature.get('properties') or {})
        props.update(scope=scope or props.get('scope'), density=props.get('density',density))
        props['zone'] = str(props.get('zone') or props.get('name') or f'ZONE_{i+1}').strip()
        if props['scope'] not in SCOPES or props['density'] not in DENSITIES:
            raise ValueError('Provide scope CORE_GDL/CORE_PERIFERICO/URBAN_AMG/AMG_FULL and a valid density')
        props.update(approved=bool(approved), source=source.name, imported_at=datetime.now(timezone.utc).isoformat())
        features.append({'type':'Feature','properties':props,'geometry':_validate_geometry(feature.get('geometry') or {})})
    keys = {(f['properties']['scope'], f['properties']['zone']) for f in features}
    previous = load_territory(destination, False)['features'] if destination.exists() else []
    kept = [f for f in previous if (f['properties']['scope'],f['properties']['zone']) not in keys]
    result = {'type':'FeatureCollection','features':kept+features}
    destination.parent.mkdir(parents=True,exist_ok=True)
    temporary = destination.with_suffix('.tmp')
    temporary.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    temporary.replace(destination)
    return result


def load_territory(path, require_approved=True):
    path = Path(path)
    if not path.is_file():
        raise ValueError('ONE-TIME HUMAN INPUT REQUIRED: import approved territory polygons')
    geo = json.loads(path.read_text(encoding='utf-8-sig'))
    if geo.get('type') != 'FeatureCollection' or not geo.get('features'):
        raise ValueError('ONE-TIME HUMAN INPUT REQUIRED: import approved territory polygons')
    for feature in geo['features']:
        _validate_geometry(feature.get('geometry') or {})
        props = feature.get('properties') or {}
        if props.get('scope') not in SCOPES or props.get('density') not in DENSITIES or not props.get('zone'):
            raise ValueError('Territory is missing zone/scope/density')
        if require_approved and props.get('approved') is not True:
            raise ValueError('ONE-TIME HUMAN INPUT REQUIRED: territory has unapproved polygons')
    return geo


def _ring_contains(ring, x, y):
    inside = False
    for a,b in zip(ring,ring[1:]):
        x1,y1 = a[:2]; x2,y2 = b[:2]
        cross = (x-x1)*(y2-y1)-(y-y1)*(x2-x1)
        if abs(cross) < 1e-12 and min(x1,x2)-1e-12 <= x <= max(x1,x2)+1e-12 and min(y1,y2)-1e-12 <= y <= max(y1,y2)+1e-12:
            return True
        if (y1 > y) != (y2 > y) and x < (x2-x1)*(y-y1)/(y2-y1)+x1:
            inside = not inside
    return inside


def geometry_contains(geometry, lat, lon):
    polygons = [geometry['coordinates']] if geometry['type']=='Polygon' else geometry['coordinates']
    return any(_ring_contains(p[0],lon,lat) and not any(_ring_contains(h,lon,lat) for h in p[1:]) for p in polygons)


def zones_for_point(geojson, lat, lon):
    return [dict(f['properties']) for f in geojson['features'] if geometry_contains(f['geometry'],lat,lon)]


def contains(geojson, lat, lon, scope=None):
    if scope is not None and scope not in SCOPES:
        raise ValueError('Unknown territory scope')
    zones = zones_for_point(geojson, lat, lon)
    return bool(zones) if scope is None else any(p.get('scope') == scope for p in zones)
