import csv
import re
import tempfile
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse
from shapely import contains_xy

import earthaccess
import h5py
import numpy as np
import geopandas as gpd



filename_pattern = re.compile(
    r"\.A(?P<year>\d{4})(?P<day>\d{3})\."
    r"(?P<tile>h\d{2}v\d{2})\."
)

afghanistan_boundary_file = Path("data/boundaries/ne_10m_admin_0_sovereignty.shp")
afghanistan_bbox = (60.0, 29.0, 78.0, 38.5)
study_start = (2018, 1, 1)
study_end = = (2023, 1, 1) 
output_file = Path("viirs_results.csv")

radiance_dataset_path = (
    "HDFEOS/GRIDS/VIIRS_Grid_DNB_2d/"
    "Data Fields/AllAngle_Composite_Snow_Free"
)

quality_dataset_path = (
    "HDFEOS/GRIDS/VIIRS_Grid_DNB_2d/"
    "Data Fields/AllAngle_Composite_Snow_Free_Quality"
)

latitude_dataset_path = (
    "HDFEOS/GRIDS/VIIRS_Grid_DNB_2d/"
    "Data Fields/lat"
)

longitude_dataset_path = (
    "HDFEOS/GRIDS/VIIRS_Grid_DNB_2d/"
    "Data Fields/lon"
)

def main():
    login()

    granules = search_granules()

    if not granules:
        print("No granules were found")
        write_results([])
        return

    granule_records = []

    for number, granule in enumerate(granules, start=1):
        print(f"Processing granule {number} of {len(granules)}")

        try:
            record = process_granule(granule)
            granule_records.append(record)


        except(
            KeyError,
            OSError,
            RuntimeError, 
            ValueError,
            TypeError,
        ) as e: 
             print(f"Skipping granule due to an Error: {e}")

    monthly_records = aggregate_monthly_results(granule_records)
    write_results(monthly_records)

    print(
        f"Wrote {len(monthly_records)} records "
        f"to {output_file}"
    )

def login():
    auth = earthaccess.login(
            strategy="all", 
            persist=True,
    )
        
    if not auth:
        raise RuntimeError("Earthdata login failed")

def search_granules():
        while True:
            try:
                granules = earthaccess.search_data(
                    short_name = "VNP46A3", # NASA Black Marble Gap-Filled monthly NTL
                    bounding_box = afghanistan_bbox,
                    temporal = takeover_temporal,
                )

                if granules:
                    return(granules)

            except(Exception) as e:
                print(f"Search failed: {e}")
                print("Retrying in 60 seconds...")
                time.sleep(60)

def get_filename(granule):
    links = granule.data_links()

    if not links:
        raise RuntimeError(f"No data links found for granule: {granule}")

    first_link = links[0]
    filename = Path(urlparse(first_link).path).name

    if not filename:
         raise RuntimeError(f"Could not extract fileanme from: {first_link}")

    return(filename)

def get_metadata(granule):
    filename = get_filename(granule)
    match = filename_pattern.search(filename)

    if match is None:
        raise ValueError(f"Filename: {filename} does not match expected pattern")
    
    year = int(match.group("year"))
    day_of_year = int(match.group("day"))

    observed_date = datetime.strptime(f"{year}{day_of_year:03d}", "%Y%j").date()

    granule_id = getattr(granule, "concept_id", str(granule))

    return(
        {
        "granule_id": granule_id,
        "filename": filename,
        "observed_date": observed_date,
        "tile_id": match.group("tile"),
    }
    )

def find_dataset(file_path: Path):
    dataset_paths = []
     
    with h5py.File(file_path, "r") as hdf_file:
        def visit_dataset(name, object_reference):
            if isinstance(object_reference, h5py.Dataset):
                dataset_paths.append(name)
        
        hdf_file.visititems(visit_dataset)

    for dataset_path in dataset_paths:
        print(dataset_path)

    return(dataset_paths[0])

def load_afghanistan_boundary():
    boundaries = gpd.read_file(afghanistan_boundary_file)

    if boundaries.crs is None:
        raise ValueError("The boundary file has no coordinate refernce system")

    boundaries = boundaries.to_crs("EPSG:4326")

    afghanistan = boundaries[boundaries["NAME"] == "Afghanistan"]

    if afghanistan.empty:
        raise ValueError("Afghanistan was not found in the boundary file") 

    return(afghanistan.geometry.union_all())


def extract_afghanistan_value(file_path: Path):
    with h5py.File(file_path, "r") as hdf_file:
        radiance = np.asarray(
            hdf_file[radiance_dataset_path][:]
        )

        quality = np.asarray(
            hdf_file[quality_dataset_path][:]
        )

        latitudes = np.asarray(
            hdf_file[latitude_dataset_path][:]
        )

        longitudes = np.asarray(
            hdf_file[longitude_dataset_path][:]
        )

    afghanistan_geometry = load_afghanistan_boundary()

    longitude_grid, latitude_grid = np.meshgrid(
        longitudes,
        latitudes,
    )

    afghanistan_mask = contains_xy(
        afghanistan_geometry,
        longitude_grid,
        latitude_grid,
    )

    valid_values = (
        afghanistan_mask
        & np.isfinite(radiance)
        & (radiance >= 0.0)
        & (quality == 0)
    )


    values = radiance[valid_values]

    if values.size == 0:
        raise ValueError(
            "No valid Afghanistan nighttime-light pixels found"
        )

    return {
        "pixel_sum": float(np.sum(values)),
        "pixel_count": int(values.size),
    }
    
def process_granule(granule):
    metadata = get_metadata(granule)

    with tempfile.TemporaryDirectory(
         prefix="earthdata_"
    ) as temporary_directory:
        temporary_directory_path = Path(temporary_directory)

        downloaded_files = earthaccess.download(
                [granule],
                local_path=temporary_directory_path,
        )

        if not downloaded_files:
            raise(RuntimeError(f"Download returned no files for {metadata['filename']}")) 

        downloaded_file = Path(downloaded_files[0])
        
        statistics = extract_afghanistan_value(downloaded_file)

        result = {
            **metadata,
            **statistics,
        }
    
    return(result)

def aggregate_monthly_results(granule_records: list[dict]):
    monthly_totals = defaultdict(
        lambda: {
            "pixel_sum": 0.0,
            "pixel_count": 0,
            "granule_count": 0,
        }
    )

    for record in granule_records:
        month = record["observed_date"].strftime("%Y-%m")

        monthly_totals[month]["pixel_sum"] += record["pixel_sum"]
        monthly_totals[month]["pixel_count"] += record["pixel_count"]
        monthly_totals[month]["granule_count"] += 1

    monthly_records = []

    for month in sorted(monthly_totals):
        totals = monthly_totals[month]

        if totals["pixel_count"] == 0:
            continue

        monthly_records.append(
            {
                "month": month,
                "nighttime_lights_mean": (totals["pixel_sum"] / totals["pixel_count"]),
                "valid_pixel_count": totals["pixel_count"],
                "granule_count": totals["granule_count"],
            }
        )

    return monthly_records

def write_results(records: list[dict]):
    fieldnames = [
        "month",
        "nighttime_lights_mean",
        "valid_pixel_count",
        "granule_count",
     ]

    output_file.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    with output_file.open(
        mode="w",
        newline="",
        encoding="utf-8",
    ) as csv_file:
        writer = csv.DictWriter(
            csv_file,
            fieldnames=fieldnames,
        )

        writer.writeheader()
        writer.writerows(records)

if __name__ == "__main__":
    main()