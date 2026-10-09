# afg-remittances-did

Did the August 2021 Taliban takeover cause a differential drop in formal remittance inflows to Afghanistan, relative to three control countries (Pakistan, Nepal and Phillipines)?

## Treatment Date

The Taliban most recently took over Afghanistan on August 2021.

Remittances are in USD. 


## Weaknesses - extreme anomolies in VIIRS data

Median: 0.0
99th percentile: 0.616
99.9th percentile: 7.068
Maximum: 286.914

The extracted VIIRS radiance series contains substantial right-skewness. Afghanistan has many zero or low-radiance pixels and a small number of highly illuminated urban pixels, causing the mean to be sensitive to extreme values. Seasonal conditions, quality flags, gap filling, and changes in valid-pixel coverage may also contribute to month-to-month variation. These values have not been arbitrarily corrected or removed. Future analysis should compare the baseline mean with median, log-transformed, trimmed, or winsorized specifications and inspect suspicious months using the underlying quality and spatial data.

## Moving forward

1. Validate the measurement
Before regression, create alternative versions using:

mean radiance;
median radiance;
log(1 + mean radiance);
a trimmed or winsorized mean;
stricter quality filtering.
Compare whether the broad time pattern is similar across specifications.

2. Obtain a remittance variable
Nighttime lights are not remittance inflows. You need a separate remittance series from an official, survey, financial, or other defensible source.

Your eventual dataset might contain:
month
nighttime_lights
remittance_inflows
exchange_rate
inflation
conflict_measure
aid_or_humanitarian_flows

3. Start with descriptive analysis
Before estimating anything:

plot nighttime lights over time;
plot remittances over time;
compare pre- and post-August 2021 averages;
inspect seasonality;
check missing observations and definitions;
document all transformations.

4. Begin with a simple model
With national monthly data, start descriptively with an interrupted time-series model:

[
Lights_t =
\alpha +
\beta PostTakeover_t +
\gamma Trend_t +
\text{month controls} +
\varepsilon_t
]

Treat this as an association, not automatically a causal estimate.

A stronger design would require province- or district-level data and pre-takeover remittance exposure:

[
Lights_{it}
\alpha_i +
\lambda_t +
\beta(Post_t \times RemittanceExposure_i)
+
\varepsilon_{it}
]

6. Use robustness checks
Report whether conclusions remain similar when you:

use mean versus median lights;
use log-transformed lights;
exclude suspicious months;
change the quality filter;
change the pre/post window;
control for seasonality, inflation, exchange rates, conflict, and COVID-related effects.