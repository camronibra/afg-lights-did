# Lights Out in Afghanistan

Did the August 2021 Taliban takeover reduce economic activity in Afghanistan? This project measures it with **satellite nighttime lights** and a **difference-in-differences** design: Afghanistan against seven comparison countries, monthly, 2018–2023.

## Headline result

| | |
|---|---|
| Main estimate | −0.73 log points, about a **52% fall** in lit radiance relative to the comparison countries |
| Clustered SE (by country) | 0.11 (8 clusters, so treat it with caution) |
| Permutation test | Afghanistan has the largest decline of all 8 countries (one-sided p = 0.125, the smallest value possible with 8 countries) |
| Placebo (fake takeover Aug 2019) | −0.09, p = 0.16, close to zero as expected |
| Robustness | −0.63 to −0.83 across thresholds and sample restrictions |

The full output is in `results.txt` and the write-up is in `paper/note.qmd`.

## Data

- **Nighttime lights:** NASA Black Marble **VNP46A3** (monthly, collection 2), layer `AllAngle_Composite_Snow_Free`. Only pixels with quality flag 0 (good) are kept.
- **Boundaries:** Natural Earth 1:10m admin-0 sovereignty (`data/boundaries/`).
- **Countries:** Afghanistan (treated). Controls: Bangladesh, Kyrgyzstan, Nepal, Pakistan, Philippines, Tajikistan, Uzbekistan.
- **Period:** January 2018 to December 2023 (72 months × 8 countries).

### Outcome variable

VNP46A3 records radiance below 0.5 nW as 0 and most of Afghanistan is dark. The plain national mean is dominated by faint background pixels. In 2023 a mass of pixels just above 0.5 nW made the mean jump while bright areas stayed flat. The outcome is therefore:

**`log(lit_sum_2)`**, the log of total radiance from pixels brighter than 2 nW, which in practice means settlements.

The 1 nW and 5 nW versions are used as robustness checks.

## Pipeline

```
NASA Earthdata ──► viirs_extraction.py ──► data/viirs_monthly.csv
                                              │
                         build_database.py + sql/schema.sql
                                              ▼
                                       data/lights.sqlite
                                     (view: analysis_panel)
                                              │
                                         analysis.R ──► figures/, results.txt
                                              │
                                     paper/note.qmd ──► note.html / note.pdf
```

| File | What it does |
|---|---|
| `viirs_extraction.py` | Searches and downloads VNP46A3 tiles, keeps valid in-country pixels, and writes one row per country-month with summary statistics (mean, median, percentiles, lit sums above 1/2/5 nW, valid-pixel share). It is resumable: months already in the CSV are skipped. |
| `build_database.py` | Runs `sql/schema.sql` and loads the CSV into SQLite. |
| `sql/schema.sql` | Defines the `countries` table, with the treatment flag, the `viirs_monthly` table, with a unique index so each country-month appears once and the `analysis_panel` view, which adds `post`, `event_time` and `calendar_month`. |
| `analysis.R` | Runs the DiD, the yearly and quarterly event studies, the permutation and time placebos and the robustness table. |
| `paper/note.qmd` | Research note in Quarto. It sources `analysis.R`, so every number in the body is computed live. |
| `plot_series.py`, `investigate_month.py`, `diagnose_viirs.py` | Exploration and diagnostic scripts used to find the measurement problem above. They are not needed to reproduce the results. |

## Method

$$
\log L_{ct} = \alpha_{c,m(t)} + \lambda_t + \beta \, (\text{Afghanistan}_c \times \text{Post}_t) + \varepsilon_{ct}
$$

- $\alpha_{c,m(t)}$: country × calendar-month fixed effects, which absorb each country's own seasonal pattern.
- $\lambda_t$: month fixed effects, which absorb shocks common to every country (e.g. COVID).
- $\beta$: the DiD effect. The % change is $e^{\beta}-1$.
- Country-months with less than 80% valid pixels are dropped (132 of 576, mostly winter in Kyrgyzstan and Tajikistan). Keeping them changes little.

## Reproduce

```bash
# 1. Python environment (needs a free NASA Earthdata account for step 2)
python -m venv .venv && source .venv/bin/activate
pip install earthaccess h5py numpy pandas geopandas shapely matplotlib

# 2. Extract lights (slow: downloads many GB of tiles)
python viirs_extraction.py

# 3. Build the database
python build_database.py

# 4. Run the analysis (R packages: DBI, RSQLite, dplyr, ggplot2, fixest)
Rscript analysis.R > results.txt

# 5. Render the paper (needs Quarto, plus the knitr and rmarkdown R packages)
quarto render paper/note.qmd
```

## Limitations

- **One treated country, 7 controls.** Clustered standard errors can be unreliable with so few clusters. The permutation test is the main evidence and it cannot produce p < 1/8.
- **Mild pre-trend.** Afghanistan was already drifting slightly down before 2021.
- **Imperfect controls.** Pakistan was itself affected by the takeover (border, trade, refugees). Nepal's lights grew unusually fast. Dropping either one leaves the result intact.
- **Lights ≠ income.** Some of the fall may reflect electricity imports or public lighting.
- **No mechanisms.** The design cannot separate the aid cut-off, the banking freeze, remittance disruption and governance changes. That would need subnational data.
