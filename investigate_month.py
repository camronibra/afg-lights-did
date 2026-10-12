import sys
from pathlib import Path

import earthaccess
import geopandas as gpd
import matplotlib.pyplot as plt
import numpy as np

from viirs_extraction import (
    get_metadata,
    good_quality,
    load_countries_geometrics,
    login,
    make_country_mask,
    read_tile,
    search_granules,
)

cache_directory = Path("VIIRS")
figure_directory = Path("figures")
top_n = 20


def main():
    # Usage: python investigate_month.py Afghanistan 2023-11
    country, month = sys.argv[1], sys.argv[2]

    login()
    geometry = load_countries_geometrics([country])[country]

    temporal = (f"{month}-01T00:00:00", f"{month}-01T23:59:59")
    granules = [
        granule
        for granule in search_granules(geometry.bounds, temporal)
        if get_metadata(granule)["observed_date"].strftime("%Y-%m") == month
    ]
    print(f"{len(granules)} tiles for {country} {month}")

    files = earthaccess.download(granules, local_path=cache_directory)

    all_values, all_latitudes, all_longitudes = [], [], []
    figure, axis = plt.subplots(figsize=(10, 8))

    for file_path in files:
        radiance, quality, latitudes, longitudes = read_tile(Path(file_path))
        mask = make_country_mask(geometry, latitudes, longitudes)

        if mask is None:
            continue

        valid = mask & (radiance >= 0.0) & (quality == good_quality)

        rows, columns = np.nonzero(valid)
        all_values.append(radiance[rows, columns])
        all_latitudes.append(latitudes[rows])
        all_longitudes.append(longitudes[columns])

        image = np.log1p(np.where(valid, radiance, np.nan))
        axis.imshow(
            image,
            extent=[longitudes.min(), longitudes.max(), latitudes.min(), latitudes.max()],
            origin="upper",  # row 0 of the tile is its northern edge
            cmap="magma",
            vmin=0,
            vmax=np.log1p(100),
        )

    gpd.GeoSeries([geometry]).boundary.plot(ax=axis, color="cyan", linewidth=0.5)
    min_lon, min_lat, max_lon, max_lat = geometry.bounds
    axis.set_xlim(min_lon, max_lon)
    axis.set_ylim(min_lat, max_lat)
    axis.set_title(f"{country} {month}: log(1 + radiance), good-quality pixels")

    figure_directory.mkdir(exist_ok=True)
    output_path = figure_directory / f"{country}_{month}_map.png"
    figure.savefig(output_path, dpi=150)
    print(f"Saved map to {output_path}")

    values = np.concatenate(all_values)
    latitudes = np.concatenate(all_latitudes)
    longitudes = np.concatenate(all_longitudes)

    print(f"Valid pixels: {values.size}")
    for percentile in [50, 90, 99, 99.9]:
        print(f"  {percentile}th percentile: {np.percentile(values, percentile):.3f}")
    print(f"  max: {values.max():.3f}")

    brightest = np.argsort(values)[::-1][:top_n]
    print(f"\nTop {top_n} brightest pixels (paste 'lat, lon' into Google Maps):")
    for i in brightest:
        print(f"  {values[i]:9.2f}   {latitudes[i]:.4f}, {longitudes[i]:.4f}")

    top_1000_share = np.sort(values)[::-1][:1000].sum() / values.sum()
    print(f"\nShare of all light from the 1000 brightest pixels: {top_1000_share:.1%}")


if __name__ == "__main__":
    main()
