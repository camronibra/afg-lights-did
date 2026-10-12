from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

input_file = Path("data/viirs_monthly.csv")
figure_directory = Path("figures")
takeover = pd.Timestamp("2021-08-01")

def main():
    data = pd.read_csv(input_file)
    data["month"] = pd.to_datetime((data["month"]), format = "%Y-%m")
    figure_directory.mkdir(exist_ok=True)

def plot_each_country(data):
    for country, group in data.groupby("country"):
        group = group.sort_values("month")
        figure, axes = plt.subplots(3, 1, figsize=(11, 9), sharex=True)

        axes[0].plot(group["month"], group["mean"], label="mean")
        axes[0].plot(group["month"], group["winsorized_mean"], label="winsorized mean")
        axes[0].set_ylabel("radiance")
        axes[0].legend()

        axes[1].plot(group["month"], group["p99"], label="99th percentile")
        axes[1].plot(group["month"], group["max"], label="max")
        axes[1].set_yscale("log")
        axes[1].legend()

        axes[2].plot(group["month"], group["share_valid"])
        axes[2].set_ylabel("share of pixels valid")

        for axis in axes:
            axis.axvline(takeover, color="red", linestyle="--")

        figure.suptitle(country)
        figure.tight_layout()
        figure.savefig(figure_directory / f"{country}_series.png", dpi=150)
        plt.close(figure)

def plot_countries_together(data):
    # Each country scaled so its pre-takeover average = 100, so they share an axis
    pre_average = (
        data[data["month"] < takeover].groupby("country")["winsorized_mean"].mean()
    )
    data["index"] = 100 * data["winsorized_mean"] / data["country"].map(pre_average)

    table = data.pivot(index="month", columns="country", values="index")
    axis = table.plot(figsize=(11, 5))
    axis.axvline(takeover, color="red", linestyle="--")
    axis.set_ylabel("Lights (pre-takeover average = 100)")
    axis.figure.tight_layout()
    axis.figure.savefig(figure_directory / "all_countries_indexed.png", dpi=150)


if __name__ == "__main__":
    main()