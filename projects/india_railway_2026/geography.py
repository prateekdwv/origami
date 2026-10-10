"""Survey of India geometry and a single shared, official-native projection."""
import hashlib
import io
from functools import lru_cache
import zipfile

import numpy as np
from pyproj import CRS, Transformer
import shapefile

from settings import ROOT

ARCHIVE = ROOT / "assets" / "soi" / "Outline_of_India.zip"


@lru_cache(maxsize=1)
def official_map():
    with zipfile.ZipFile(ARCHIVE) as archive:
        stem = "Outline_of_India"
        crs = CRS.from_wkt(archive.read(stem + ".prj").decode())
        reader = shapefile.Reader(**{ext: io.BytesIO(archive.read(stem + "." + ext)) for ext in ("shp", "shx", "dbf")})
        rings = []
        for shape in reader.shapes():
            points = np.array(shape.points)
            boundaries = list(shape.parts) + [len(points)]
            rings.extend(points[a:b] for a, b in zip(boundaries[:-1], boundaries[1:]))
        return crs, tuple(reader.bbox), rings


@lru_cache(maxsize=1)
def projector():
    return Transformer.from_crs("EPSG:4326", official_map()[0], always_xy=True)


def project(coordinates):
    array = np.asarray(coordinates, dtype=float)
    if array.ndim != 2 or array.shape[1] != 2 or not np.isfinite(array).all():
        raise ValueError("Invalid coordinate array")
    if (np.abs(array[:, 0]) > 180).any() or (np.abs(array[:, 1]) > 90).any():
        raise ValueError("Coordinates must be [longitude, latitude]")
    result = np.column_stack(projector().transform(array[:, 0], array[:, 1]))
    if not np.isfinite(result).all():
        raise ValueError("Coordinates cannot be projected")
    return result


def pixels(points):
    """Fit full boundary, including islands, into the central map area."""
    x0, y0, x1, y1 = official_map()[1]
    scale = min(944 / (x1-x0), 1060 / (y1-y0))
    points = np.asarray(points)
    return np.column_stack((540 + (points[:, 0]-(x0+x1)/2)*scale,
                            840 - (points[:, 1]-(y0+y1)/2)*scale))


def boundary_hash():
    return hashlib.sha256(ARCHIVE.read_bytes()).hexdigest()
