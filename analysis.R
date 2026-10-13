library(DBI)
library(dplyr)
library(ggplot2)
library(fixest)

con <- dbConnect(RSQLite::SQLite(), "data/lights.sqlite")
panel <- dbGetQuery(con, "SELECT * FROM analysis_panel")
dbDisconnect(con)

panel <- panel |>
  mutate(
    date = as.Date(paste0(month, "-01")),
    log_lights = log(lit_sum_2),
    event_quarter = floor(event_time / 3),  # quarters smooth out monthly noise
    event_year = floor(event_time / 12)     # 0 = Aug 2021-Jul 2022, -1 = Aug 2020-Jul 2021, ...
  )
panel_all <- panel                              # full version, for comparison
panel <- panel |> filter(share_valid >= 0.8)    # drop months with poor pixel coverage

takeover <- as.Date("2021-08-01")

# The picture first
panel |>
  group_by(country) |>
  mutate(index = 100 * lit_sum_2 / mean(lit_sum_2[post == 0])) |>
  ungroup() |>
  ggplot(aes(date, index, group = country, colour = country == "Afghanistan")) +
  geom_line() +
  geom_vline(xintercept = takeover, linetype = "dashed") +
  scale_colour_manual(values = c("grey65", "firebrick"), guide = "none") +
  labs(x = NULL, y = "Lit radiance (pre-takeover mean = 100)",
       title = "Afghanistan (red) vs comparison countries")
ggsave("figures/indexed_lights.png", width = 9, height = 5)

# Difference-in-differences test
# ── FIX: standard errors ──────────────────────────────────────────────────
# PROBLEM:
#   se <- IID default            # treats every country-month as independent
#   but months within a country are correlated -> SE far too small (0.06)
# FIX:
#   se <- cluster by country     # allow correlation within each country
#   caveat: only 8 clusters, so even this is shaky -> the permutation test
#           further down is the inference to trust
did <- feols(
  log_lights ~ treated:post | country^calendar_month + month,
  data = panel
)
summary(did, vcov = ~country)
exp(coef(did)) - 1   # convert the log coefficient into a % change

# Event study
# ── FIX: event study was misidentified ────────────────────────────────────
# PROBLEM:
#   model: lights = afghan_calendar_month_effect + quarter_effect[q]
#   Afghanistan is the only treated country, so for every "season"
#   (Feb-Apr, May-Jul, Aug-Oct, Nov-Jan):
#       afghan_effect[season] + c   and   quarter_effect[q in season] - c
#   fit the data equally well for any c -> each season needs its own baseline
#   ref = -1 only pins down the May-Jul quarters; R silently drops 3 other
#   quarters to pin down the rest -> coefficients measured against 4 different
#   baselines -> fake "+0.7 pre-trend", jumpy coefficients
#   also: quarter -1 (May-Jul 2021) already includes the Taliban offensive,
#         lights fell ~35% in Jun-Jul 2021 -> contaminated baseline
# FIX:
#   bin by event YEAR (Aug-Jul), each year covers all 12 calendar months
#       -> one reference year pins down everything, no dropped coefficients
#   ref <- year -2 (Aug 2019 - Jul 2020), well before the offensive
#   year -1 (Aug 2020 - Jul 2021) is estimated on its own -> shows anticipation
es <- feols(
  log_lights ~ i(event_year, treated, ref = -2) | country^calendar_month + month,
  data = panel,
  vcov = ~country
)
png("figures/event_study.png", width = 900, height = 500)
iplot(es, main = "Afghanistan minus controls, by year relative to the takeover (Aug-Jul years)")
dev.off()

# Quarterly version, for timing within 2021.
# Swaps country^calendar_month for country FE so quarters are identified;
# the cost is that Afghanistan's own seasonality is not removed, so the
# pre-period shows a seasonal sawtooth. Read it for WHEN the drop starts.
es_q <- feols(
  log_lights ~ i(event_quarter, treated, ref = -2) | country + month,
  data = panel,
  vcov = ~country
)
png("figures/event_study_quarterly.png", width = 900, height = 500)
iplot(es_q, main = "Afghanistan minus controls, by quarter (country FE, common seasonality)")
dev.off()

# placebo test: how to get honest inference with few countries. With 8 countries, ignore the default p-values - consider this instead: is Afghanistan's estimate unusual compared with pretending each control country was treated?
placebo_effect <- function(fake_country) {
  fake <- panel |>
    filter(country == fake_country | country != "Afghanistan") |>
    mutate(treated = as.integer(country == fake_country))
  model <- feols(log_lights ~ treated:post | country^calendar_month + month, data = fake)
  coef(model)[["treated:post"]]
}

effects <- sapply(unique(panel$country), placebo_effect)
sort(effects)
# ── FIX: permutation p-value ──────────────────────────────────────────────
# PROBLEM:
#   p <- share of countries with |effect| >= |afghan effect|   -> 0.25
#   Nepal's +0.86 counts as "more extreme" than Afghanistan's -0.73, but the
#   question is whether lights FELL; and with 8 countries the smallest
#   possible p is 1/8 = 0.125, which was never stated
# FIX:
#   report both:
#     two-sided p <- share with |effect| >= |afghan effect|
#     one-sided p <- share with effect <= afghan effect   (rank from the bottom)
#   and state the floor: p can never go below 1 / n_countries
mean(abs(effects) >= abs(effects["Afghanistan"]))   # two-sided permutation p-value
mean(effects <= effects["Afghanistan"])             # one-sided: is Afghanistan the biggest drop?
1 / length(effects)                                 # smallest p this test can ever produce

# placebo in time; pre-takeover data only and pretend the takeover happened in August 2019 - should find nothing
# ── FIX: placebo window leaked the real drop ──────────────────────────────
# PROBLEM:
#   keep months where post == 0           # i.e. everything before Aug 2021
#   fake_post <- month >= 2019-08
#   but Jun-Jul 2021 (offensive, lights already falling) are inside fake_post
#   -> the placebo picks up part of the REAL effect: -0.15, p = 0.003
# FIX:
#   keep months <= 2021-04                # stop before the offensive began
#   fake_post <- month >= 2019-08
#   -> a clean placebo should now be close to zero
fake_time <- panel |>
  filter(month <= "2021-04") |>
  mutate(post = as.integer(month >= "2019-08"))
summary(
  feols(log_lights ~ treated:post | country^calendar_month + month, data = fake_time),
  vcov = ~country
)

# Robustness table
# ── FIX: missing robustness checks ────────────────────────────────────────
# PROBLEM:
#   1. drop starts in Jun 2021, but May-Jul 2021 sits in the "pre" period
#      -> pre average dragged down, effect possibly understated
#   2. Nepal's lights roughly double after 2021 (real growth, all thresholds
#      agree, Nov spikes = Tihar festival) -> diverging control may inflate
#      the gap with Afghanistan
#   3. panel_all was created but never used -> unknown whether the
#      share_valid >= 0.8 filter (drops 134 of 576 rows, mostly winter months
#      in Kyrgyzstan/Tajikistan) drives the result
#   4. all columns used IID standard errors
# FIX:
#   add column: drop May, Jun, Jul 2021            (anticipation window)
#   add column: drop Nepal
#   add column: estimate on panel_all              (no coverage filter)
#   cluster every column by country
etable(
  feols(log(lit_sum_1) ~ treated:post | country^calendar_month + month, panel),
  did,
  feols(log(lit_sum_5) ~ treated:post | country^calendar_month + month, panel),
  feols(log_lights ~ treated:post | country^calendar_month + month,
        filter(panel, country != "Pakistan")),
  feols(log_lights ~ treated:post | country^calendar_month + month,
        filter(panel, month != "2021-08")),   # takeover was mid-month
  feols(log_lights ~ treated:post | country^calendar_month + month,
        filter(panel, !month %in% c("2021-05", "2021-06", "2021-07"))),   # offensive months
  feols(log_lights ~ treated:post | country^calendar_month + month,
        filter(panel, country != "Nepal")),
  feols(log_lights ~ treated:post | country^calendar_month + month, panel_all),
  headers = c("> 1 nW", "> 2 nW (main)", "> 5 nW", "No Pakistan", "No Aug 2021",
              "No May-Jul 2021", "No Nepal", "All months"),
  vcov = ~country
)