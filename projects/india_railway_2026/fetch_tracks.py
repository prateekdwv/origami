"""Explicitly download the public Esri-hosted OpenStreetMap Rail layer.

Run from the repository root. Pages and assembled GeoJSON stay in media/tooling;
prepare_tracks.py creates the attributed, compressed project input assets.
No traffic observations, credentials, or RailRadar quota are used.
"""
import concurrent.futures
import json
import urllib.parse
import urllib.request
from settings import MEDIA

ENDPOINT = 'https://livingatlas.esri.in/server/rest/services/OSM/Railways/MapServer/0/query'
PAGE_SIZE = 2000


def request(parameters):
    url = ENDPOINT + '?' + urllib.parse.urlencode(parameters)
    with urllib.request.urlopen(url, timeout=120) as response:
        data = json.load(response)
    if 'error' in data:
        raise RuntimeError(data['error'])
    return data


def main():
    folder = MEDIA / 'tooling' / 'esri-railways'
    folder.mkdir(parents=True, exist_ok=True)
    count = request({'where': "fclass='Rail'", 'returnCountOnly': 'true', 'f': 'json'})['count']
    def fetch(offset):
        data = request({'where': "fclass='Rail'", 'outFields': 'objectid,id,fclass',
                        'outSR': 4326, 'f': 'geojson', 'resultOffset': offset,
                        'resultRecordCount': PAGE_SIZE, 'orderByFields': 'objectid', 'geometryPrecision': 6})
        if len(data.get('features', [])) != min(PAGE_SIZE, count-offset):
            raise RuntimeError(f'Incomplete railway page at {offset}')
        (folder / f'{offset}.json').write_text(json.dumps(data, separators=(',', ':')), encoding='utf-8')
        print(f'{offset + len(data["features"])}/{count}', flush=True)
        return data['features']
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        pages = list(pool.map(fetch, range(0, count, PAGE_SIZE)))
    features = [feature for page in pages for feature in page]
    if len(features) != len({f['properties']['objectid'] for f in features}) or len(features) != count:
        raise RuntimeError('Duplicate or missing railway features')
    output = folder.parent / 'railways.geojson'
    output.write_text(json.dumps({'type': 'FeatureCollection', 'features': features}, separators=(',', ':')), encoding='utf-8')
    print(output)


if __name__ == '__main__':
    main()
