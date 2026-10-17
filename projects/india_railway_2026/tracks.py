"""Read-only, hash-checked railway assets shared by the preview and compositor."""
from functools import lru_cache
import gzip
import hashlib
import json
from settings import ROOT
from geography import pixels, project

DIRECTORY = ROOT / 'assets' / 'railways'

@lru_cache(maxsize=1)
def load_tracks():
    provenance = json.loads((DIRECTORY / 'provenance.json').read_text(encoding='utf-8'))
    raw = (DIRECTORY / 'geometry.json.gz').read_bytes()
    if hashlib.sha256(raw).hexdigest() != provenance['geometry_sha256']:
        raise ValueError('Railway geometry integrity check failed')
    return json.loads(gzip.decompress(raw)), provenance

@lru_cache(maxsize=1)
def network_pixels():
    data, _ = load_tracks()
    return [pixels(project(line['coordinates'])) for line in data['network']]
