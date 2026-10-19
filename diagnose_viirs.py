import h5py
import geopandas as gpd
import numpy as np
from shapely import contains_xy


path = (
    "VIIRS/"
    "VNP46A3.A2012336.h24v05.002.2025086120446.h5"
)

base = "HDFEOS/GRIDS/VIIRS_Grid_DNB_2d/Data Fields/"

boundary = gpd.read_file(
    "data/boundaries/ne_10m_admin_0_sovereignty.shp"
)

afghanistan = boundary[
    boundary["NAME"] == "Afghanistan"
].geometry.union_all()

with h5py.File(path, "r") as file:
    radiance = np.asarray(
        file[base + "AllAngle_Composite_Snow_Free"][:]
    )

    quality = np.asarray(
        file[base + "AllAngle_Composite_Snow_Free_Quality"][:]
    )

    latitudes = np.asarray(
        file[base + "lat"][:]
    )

    longitudes = np.asarray(
        file[base + "lon"][:]
    )

longitude_grid, latitude_grid = np.meshgrid(
    longitudes,
    latitudes,
)

afghanistan_mask = contains_xy(
    afghanistan,
    longitude_grid,
    latitude_grid,
)

valid = (
    afghanistan_mask
    & np.isfinite(radiance)
    & (radiance >= 0.0)
    & (quality == 0)
)

values = radiance[valid]

print("Afghanistan valid pixels:", values.size)
print("Mean:", values.mean())
print("Median:", np.median(values))
print("Maximum:", values.max())
print("99th percentile:", np.percentile(values, 99))
print("99.9th percentile:", np.percentile(values, 99.9))
print(
    "Quality counts inside Afghanistan:",
    dict(zip(*np.unique(quality[afghanistan_mask], return_counts=True))),
)