import csv
import re
import tempfile
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse
from datetime import date

import earthaccess
import h5py
import numpy as np
import geopandas as gpd
from shapely import contains_xy
from shapely.geometry import box 

countries = (
    "Afghanistan", 
    "Pakistan", 
    "Nepal",
    "Philippines",
    "Bangladesh",
    "Tajikistan",
    "Kyrgyzstan",
    "Uzbekistan",
    )

afghanistan_bbox = (60.0, 29.0, 78.0, 38.5)
study_start = date(2018, 1, 1)
study_end = date(2023, 12, 31) 
month_limit = 2 # will set to 2 while testing; None = all months 

boundary_file = Path("data/boundaries/ne_10m_admin_0_sovereignty.shp")
output_file = Path("data/viirs_monthly.csv")

lit_thresholds = (1, 2, 5)

good_quality = 0 

filename_pattern = re.compile(
    r"\.A(?P<year>\d{4})(?P<day>\d{3})\."
    r"(?P<tile>h\d{2}v\d{2})\."
)

data_fields = "HDFEOS/GRIDS/VIIRS_Grid_DNB_2d/Data Fields/"
radiance_dataset_path = data_fields + "AllAngle_Composite_Snow_Free" 
quality_dataset_path = data_fields + "AllAngle_Composite_Snow_Free_Quality"
latitude_dataset_path = data_fields + "lat"
longitude_dataset_path = data_fields + "lon"

fieldnames = [
    "month",
    "country",
    "mean",
    "median", 
    "log_mean",
    "winsorized_mean",
    "p99", 
    "p999", 
    "max",
    "sum",
    "valid_pixels",
    "pixels_in_country",
    "share_valid",
    "tiles",
    "share_zero",
]

for threshold in lit_thresholds:
    fieldnames += [f"lit_pixels_{threshold}", f"lit_sum_{threshold}"]

def main():
    login()

    geometries = load_countries_geometrics(countries)
    granules_by_month = collect_granules_monthly(geometries)
    months = sorted(granules_by_month)

    if not granules_by_month:
        print("No granules were found")
        return
    else:
        if month_limit is not None:
            months = months[:month_limit]

    finished_months = load_finished_months()
    mask_cache = {}

    for number, month in enumerate(months, start=1):
        if month in finished_months:
            print(f"[{number}]/{len(months)}) {month}: already done, skipping...")
            continue

        granules = granules_by_month[month]
        print(f"[{number}/{len(months)}] {month}: {len(granules)} tiles")

        try:
            rows = process_month(month, granules, geometries, mask_cache)

        except(
            KeyError, OSError, RuntimeError, ValueError) as e: 
            print(f"Skipping {month} due to an Error: {e}")
            continue

        append_rows(rows)

    print(f"Done. Results are in {output_file}")

def login():
    auth = earthaccess.login(
            strategy="all", 
            persist=True,
    )
        
    if not auth:
        raise RuntimeError("Earthdata login failed")

def load_countries_geometrics(country_names):
    boundaries = gpd.read_file(boundary_file)

    if boundaries.crs is None:
        raise ValueError("The boundary file has no coordinate reference system")

    boundaries = boundaries.to_crs("EPSG:4326")
    geometries = {}

    for name in country_names:
        rows = boundaries[boundaries["NAME"] == name]

        if rows.empty:
            raise ValueError(f"{name} was not found in the boundary file")
        
        geometries[name] = rows.geometry.union_all()

    return(geometries)

def get_filename(granule):
    links = granule.data_links()

    if not links:
        raise RuntimeError(f"No data links found for granule: {granule}")

    first_link = links[0]
    filename = Path(urlparse(first_link).path).name

    if not filename:
         raise RuntimeError(f"Could not extract fileanme from: {first_link}")
    
    return(filename)

def search_granules(bounding_box, temporal, max_attempts=5, wait_seconds=60):
    for attempt in range(1, max_attempts + 1): 
        try:
            return earthaccess.search_data(
                short_name="VNP46A3",  # NASA Black Marble monthly nighttime lights
                version="2",
                bounding_box=bounding_box,
                temporal=temporal,
            )

        except(Exception) as e:
            print(f"Search attempt {attempt} of {max_attempts} failed as {e}")

            if attempt < max_attempts:
                time.sleep(wait_seconds)

    raise(RuntimeError(f"Granule search failed after {max_attempts} attempts"))

def collect_granules_monthly(geometries):
    temporal = (
        f"{study_start}T00:00:00",
        f"{study_end}T23:59:59",
    )
    granules_by_month = defaultdict(dict) # month -> {filename: granule}

    for country, geometry in geometries.items():
        print(f"Searching for {country} granules")
        granules = search_granules(geometry.bounds, temporal)
        print(f"  found {len(granules)}")

        for granule in granules:
            metadata = get_metadata(granule)
            observed_date = metadata["observed_date"]

            if not (study_start <= observed_date <= study_end):
                continue
            month = observed_date.strftime("%Y-%m")
            # Keyed by filename, so a title shared by two countries is only stored once 
            granules_by_month[month][metadata["filename"]] = granule

    return(granules_by_month)

def read_tile(file_path: Path):
    with h5py.File(file_path, "r") as hdf_file:
        radiance = hdf_file[radiance_dataset_path][:]
        quality = hdf_file[quality_dataset_path][:]
        latitudes = hdf_file[latitude_dataset_path][:]
        longitudes = hdf_file[longitude_dataset_path][:]

    return(radiance, quality, latitudes, longitudes)

def make_country_mask(geometry, latitudes, longitudes):
    """True for pixels inside the countryu, or None if the tile mises it entirely"""
    tile_box = box(longitudes.min(), latitudes.min(), longitudes.max(), latitudes.max())
    if not geometry.intersects(tile_box):
        return(None)

    longitude_grid, latitude_grid = np.meshgrid(longitudes, latitudes)
    mask = contains_xy(geometry, longitude_grid, latitude_grid)

    if mask.any():
        return(mask)
    return None 

def summarise_values(values):
    values = values.astype(np.float64)  # float32 loses precision when summing millions of pixels
    p999 = np.percentile(values, 99.9)

    summary = {
        "mean": float(values.mean()),
        "median": float(np.median(values)),
        "log_mean": float(np.log1p(values).mean()),
        "winsorized_mean": float(np.minimum(values, p999).mean()),
        "p99": float(np.percentile(values, 99)),
        "p999": float(p999),
        "max": float(values.max()),
        "sum": float(values.sum()),
        "share_zero": float((values == 0).mean()),
    }

    for threshold in lit_thresholds:
        lit = values[values > threshold]
        summary[f"lit_pixels_{threshold}"] = int(lit.size)
        summary[f"lit_sum_{threshold}"] = float(lit.sum())

    return summary

def process_month(month, granules, geometries, mask_cache):
    values = defaultdict(list)
    pixels_in_country = defaultdict(int)
    tiles_used = defaultdict(list)

    with tempfile.TemporaryDirectory(prefix="earthdata_") as temporary_directory:
        downloaded_files = earthaccess.download(
            list(granules.values()),
            local_path = temporary_directory,
        )

        if len(downloaded_files) != len(granules): 
            raise RuntimeError(f"Expected {len(granules)} files but downloaded {len(downloaded_files)}")

        for file_path in downloaded_files:
            file_path = Path(file_path)
            tile_id = filename_pattern.search(file_path.name).group("tile")
            radiance, quality, latitudes, longitudes = read_tile(file_path)

            for country, geometry in geometries.items():
                # The pixel grid of a tile never changes, so each mask only built once
                key = (country, tile_id)
                if key not in mask_cache:
                    mask_cache[key] = make_country_mask(geometry, latitudes, longitudes)

                mask = mask_cache[key]
                if mask is None:
                    continue 
                # radiance >= 0 also removes the -999.9 fill value 
                valid = mask & (radiance >= 0.0) & (quality == good_quality)

                values[country].append(radiance[valid])
                pixels_in_country[country] += int(mask.sum())
                tiles_used[country].append(tile_id)
    rows = []

    for country in geometries:
        if not values[country]:
            raise RuntimeError(f"No tiles covered {country} in {month}")

        country_values = np.concatenate(values[country])

        if country_values.size == 0:
            raise ValueError(f"No valid pixels for {country} in {month}")

        rows.append(
            {
                "month": month,
                "country": country,
                **summarise_values(country_values),
                "valid_pixels": int(country_values.size),
                "pixels_in_country": pixels_in_country[country],
                "share_valid": country_values.size / pixels_in_country[country],
                "tiles": ";".join(sorted(tiles_used[country])),
            }
        )
    return(rows)

def load_finished_months(): 
    if not output_file.exists():
        return(set())

    with output_file.open(newline="", encoding="utf-8") as csv_file:
        return{row["month"] for row in csv.DictReader(csv_file)}

def append_rows(rows):
    write_header = not output_file.exists()
    output_file.parent.mkdir(parents=True, exist_ok=True)

    with output_file.open(mode="a", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=fieldnames)

        if write_header:
            writer.writeheader()

        writer.writerows(rows)

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

if __name__ == "__main__":
    main()