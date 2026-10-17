"""Prepare the Esri-hosted OSM track geometry for the synthetic preview; no invented graph edges.

Usage: python projects/india_railway_2026/prepare_tracks.py path/to/railways.geojson
The original paginated GeoJSON layer is retained under assets/railways with ODbL provenance.
"""
import argparse
import gzip
import hashlib
import json
from pathlib import Path

import numpy as np
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components, dijkstra
from scipy.spatial import cKDTree

from demo import CORRIDORS, NODES
from geography import project
from settings import ROOT


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
    if data.get('type') != 'FeatureCollection' or len(data.get('features',[])) < 90000:
        raise ValueError('Incomplete national rail layer')
    ways=[]
    node_ids={}
    for feature in data['features']:
        geometry=feature.get('geometry')
        if not geometry:
            continue
        lines=[geometry['coordinates']] if geometry['type']=='LineString' else geometry['coordinates']
        for part, line in enumerate(lines):
            if len(line)<2:
                continue
            nodes=[]
            points=[]
            for lon,lat,*_ in line:
                # The source is split at administrative borders. Canonicalise sub-metre rounding.
                key=(round(lon,5),round(lat,5))
                nodes.append(node_ids.setdefault(key,len(node_ids)))
                points.append({'lon':key[0],'lat':key[1]})
            ways.append({'id':f"{feature['properties']['objectid']}-{part}",'nodes':nodes,'geometry':points})
    coordinates = {}
    for way in ways:
        for node, point in zip(way['nodes'], way['geometry']):
            coordinates[node] = (point['lon'], point['lat'])
    ids = sorted(coordinates)
    index = {node: i for i, node in enumerate(ids)}
    lonlat = np.array([coordinates[n] for n in ids])
    xy = project(lonlat)
    edges = set()
    for way in ways:
        for a,b in zip(way['nodes'], way['nodes'][1:]):
            if a != b:
                edges.add(tuple(sorted((index[a], index[b]))))
    edges = np.array(sorted(edges))
    lengths = np.linalg.norm(xy[edges[:,0]]-xy[edges[:,1]], axis=1)
    graph = coo_matrix((np.r_[lengths,lengths], (np.r_[edges[:,0],edges[:,1]], np.r_[edges[:,1],edges[:,0]])), shape=(len(ids),len(ids))).tocsr()
    _, labels = connected_components(graph, directed=False)
    tree = cKDTree(xy)
    anchors = {}
    component_sizes = np.bincount(labels)
    for name, point in NODES.items():
        center = project([point])[0]
        nearby = tree.query_ball_point(center, 15000)
        candidates = {}
        for node in nearby:
            component = int(labels[node])
            if component_sizes[component] < 100:
                continue
            distance = float(np.linalg.norm(xy[node]-center))
            if component not in candidates or distance < candidates[component][0]:
                candidates[component] = (distance, node)
        anchors[name] = candidates
    routes, omitted, snaps = [], [], {}
    used = set()
    for route_index, (category, names) in enumerate(CORRIDORS):
        names_list = names.split()
        for leg, (left, right) in enumerate(zip(names_list, names_list[1:])):
            identity = f'{route_index}-{leg}'
            pair = (category, tuple(sorted((left, right))))
            if pair in used:
                continue
            used.add(pair)
            common = anchors[left].keys() & anchors[right].keys()
            if not common:
                omitted.append({'id':identity, 'names':f'{left} {right}', 'reason':'No connected mapped path near both cities'})
                continue
            component = min(common, key=lambda c: (anchors[left][c][0]+anchors[right][c][0],c))
            a,b = anchors[left][component][1], anchors[right][component][1]
            distance, predecessors = dijkstra(graph, directed=False, indices=a, return_predecessors=True)
            direct = np.linalg.norm(xy[b]-xy[a])
            if a == b or distance[b] > direct*2.5:
                omitted.append({'id':identity,'names':f'{left} {right}','reason':'Degenerate or excessive detour in incomplete track graph'})
                continue
            path=[b]
            while path[-1] != a:
                path.append(int(predecessors[path[-1]]))
            path.reverse()
            pts=xy[path]
            along=np.r_[0.,np.cumsum(np.linalg.norm(np.diff(pts,axis=0),axis=1))]
            selected=simplify(pts)
            total=float(along[-1])
            # Stops at mapped track nodes, spaced along the demonstration leg.
            stop_indices = sorted(set([0, *[int(np.searchsorted(along, d)) for d in np.arange(50000,total,50000)],len(path)-1]))
            selected=sorted(set(selected)|set(stop_indices))
            routes.append({'id':identity,'category':category,'names':f'{left} {right}',
                           'coordinates':lonlat[np.asarray(path)[selected]].tolist(),
                           'distances':along[selected].tolist(),'stops':along[stop_indices].tolist()})
            snaps[identity] = {left:anchors[left][component][0],right:anchors[right][component][0]}
            print(f'{identity}: {left} - {right}: {total/1000:.0f} km, {len(selected)} points',flush=True)
    output=ROOT/'assets'/'railways'
    output.mkdir(exist_ok=True)
    (output/'source-railways.geojson.gz').write_bytes(gzip.compress(raw,mtime=0))
    geometry={'source':'OpenStreetMap','snapshot':'Source snapshot date not supplied',
              'routes':routes, 'network':[{'id':w['id'], 'coordinates':[[p['lon'],p['lat']] for p in w['geometry']]} for w in ways]}
    packed=gzip.compress(json.dumps(geometry,separators=(',',':')).encode(),mtime=0)
    (output/'geometry.json.gz').write_bytes(packed)
    provenance={'source':'https://www.openstreetmap.org','endpoint':'https://livingatlas.esri.in/server/rest/services/OSM/Railways/MapServer/0',
                'retrieved':'2026-10-10','snapshot':'Source snapshot date not supplied',
                'license':'ODbL-1.0','license_url':'https://opendatacommons.org/licenses/odbl/1-0/',
                'attribution':'© OpenStreetMap contributors; https://www.openstreetmap.org/copyright',
                'raw_sha256':hashlib.sha256(raw).hexdigest(),'geometry_sha256':hashlib.sha256(packed).hexdigest(),
                'ways':len(ways),'nodes':len(ids),'routes':len(routes),'omitted':omitted,'anchor_snap_metres':snaps,
                'method':'Shortest undirected paths on source track vertices rounded to 5 decimal degrees (about 1 m) to reunite administrative splits. No larger gap bridging. City pairs snap within 15 km to a common connected component. Missing paths and detours over 2.5 times straight distance are omitted. Stops are invented positions on mapped track nodes. Route display simplification <=150 m; full network retained.',
                'limitations':'Mapped track geometry, not a verified train itinerary or October 2026 completeness claim. All preview timings and services are invented.'}
    (output/'provenance.json').write_text(json.dumps(provenance,indent=2,ensure_ascii=False),encoding='utf-8')
    print('Saved',len(routes),'routes; omitted',omitted)

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source',type=Path)
    prepare(parser.parse_args().source)
