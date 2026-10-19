DROP VIEW IF EXISTS analysis_panel;
DROP INDEX IF EXISTS viirs_country_month;
DROP TABLE IF EXISTS viirs_monthly;
DROP TABLE IF EXISTS countries;

CREATE TABLE countries (
    country TEXT PRIMARY KEY,
    iso3 TEXT NOT NULL UNIQUE,
    treated INTEGER NOT NULL CHECK (treated IN (0, 1))
);

INSERT INTO countries (country, iso3, treated) VALUES
    ('Afghanistan', 'AFG', 1),
    ('Bangladesh', 'BGD', 0),
    ('Kyrgyzstan', 'KGZ', 0),
    ('Nepal', 'NPL', 0),
    ('Pakistan', 'PAK', 0),
    ('Philippines', 'PHL', 0),
    ('Tajikistan', 'TJK', 0),
    ('Uzbekistan', 'UZB', 0);

CREATE TABLE viirs_monthly (
    month TEXT NOT NULL,
    country TEXT NOT NULL REFERENCES countries (country),
    mean REAL,
    median REAL,
    log_mean REAL,
    winsorized_mean REAL,
    p99 REAL,
    p999 REAL,
    max REAL,
    sum REAL,
    valid_pixels INTEGER,
    pixels_in_country INTEGER,
    share_valid REAL,
    tiles TEXT,
    share_zero REAL,
    lit_pixels_1 INTEGER,
    lit_sum_1 REAL,
    lit_pixels_2 INTEGER,
    lit_sum_2 REAL,
    lit_pixels_5 INTEGER,
    lit_sum_5 REAL
);

-- One row per country-month; this fails loudly if a month was ever written twice.
CREATE UNIQUE INDEX viirs_country_month
    ON viirs_monthly (country, month);

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
FROM viirs_monthly AS l
JOIN countries AS c ON c.country = l.country;