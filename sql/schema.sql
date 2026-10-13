-- One row per country-month; this fails loudly if a month was ever written twice
CREATE UNIQUE INDEX IF NOT EXISTS lights_country_month
    ON lights_monthly (country, month);

DROP VIEW IF EXISTS analysis_panel;

CREATE VIEW analysis_panel AS
SELECT
    l.country,
    c.iso3,
    l.month,
    substr(l.month, 6, 2) AS calendar_month,          -- '01'..'12', for seasonality
    c.treated,
    CASE WHEN l.month >= '2021-08' THEN 1 ELSE 0 END AS post,
    -- months since the takeover: 0 = Aug 2021, -1 = Jul 2021, ...
    (CAST(substr(l.month, 1, 4) AS INTEGER) - 2021) * 12
        + CAST(substr(l.month, 6, 2) AS INTEGER) - 8 AS event_time,
    l.lit_sum_1,
    l.lit_sum_2,
    l.lit_sum_5,
    l.lit_pixels_2,
    l.mean,
    l.share_valid
FROM lights_monthly AS l
JOIN countries AS c ON c.country = l.country;