"""Freeze a downloaded national GeoJSON network, retaining source and licence.

Usage: python projects/india_railway_2026/prepare_tracks.py path/to/railways.geojson
"""
import argparse
from datetime import datetime, timezone
import gzip
import hashlib
import json
from pathlib import Path

import numpy as np
from settings import ROOT
from store import write_json


def simplify(points, tolerance=150):
    """RDP indices; at most 150 metres of display simplification, no smoothing."""
    keep = {0, len(points)-1}
    pending = [(0, len(points)-1)]
    while pending:
        a, b = pending.pop()
        if b <= a+1:
            continue
        vector = points[b]-points[a]
        length = vector @ vector
        t = np.clip((points[a+1:b]-points[a]) @ vector / length, 0, 1) if length else np.zeros(b-a-1)
        errors = np.linalg.norm(points[a+1:b]-(points[a]+t[:, None]*vector), axis=1)
        i = int(np.argmax(errors))+a+1
        if errors[i-a-1] > tolerance:
            keep.add(i)
            pending.extend(((a, i), (i, b)))
    return sorted(keep)



def prepare(source):
    raw = source.read_bytes()
    data = json.loads(raw)
    if data.get('type') != 'FeatureCollection' or len(data.get('features', [])) < 90000:
        raise ValueError('Incomplete national rail layer')
    network = []
    for feature in data['features']:
        geometry = feature.get('geometry')
        if geometry is None:
            continue
        lines = [geometry['coordinates']] if geometry['type'] == 'LineString' else geometry['coordinates']
        for part, line in enumerate(lines):
            if len(line) >= 2:
                network.append({'id': f"{feature['properties']['objectid']}-{part}",
                                'coordinates': [[round(lon, 5), round(lat, 5)] for lon, lat, *_ in line]})
    output = ROOT / 'assets' / 'railways'
    output.mkdir(exist_ok=True)
    packed = gzip.compress(json.dumps({'source': 'OpenStreetMap', 'network': network}, separators=(',', ':')).encode(), mtime=0)
    (output / 'source-railways.geojson.gz').write_bytes(gzip.compress(raw, mtime=0))
    (output / 'geometry.json.gz').write_bytes(packed)
    write_json(output / 'provenance.json', {
        'source': 'https://www.openstreetmap.org',
        'endpoint': 'https://livingatlas.esri.in/server/rest/services/OSM/Railways/MapServer/0',
        'retrieved': datetime.now(timezone.utc).isoformat(), 'snapshot': 'Source snapshot date not supplied',
        'license': 'ODbL-1.0', 'license_url': 'https://opendatacommons.org/licenses/odbl/1-0/',
        'attribution': '\u00a9 OpenStreetMap contributors; https://www.openstreetmap.org/copyright',
        'raw_sha256': hashlib.sha256(raw).hexdigest(), 'geometry_sha256': hashlib.sha256(packed).hexdigest(),
        'ways': len(network), 'method': 'Full source network rounded to 5 decimal degrees; no invented edges.',
        'limitations': 'Mapped geometry, not verified train itineraries or a completeness claim.'})


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    prepare(parser.parse_args().source)
