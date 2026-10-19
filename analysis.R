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
    event_quarter = floor(event_time / 3),  
    event_year = floor(event_time / 12)     
  )
panel_all <- panel                              
panel <- panel |> filter(share_valid >= 0.8)    

takeover <- as.Date("2021-08-01")

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

did <- feols(
  log_lights ~ treated:post | country^calendar_month + month,
  data = panel
)
summary(did, vcov = ~country)
exp(coef(did)) - 1  

es <- feols(
  log_lights ~ i(event_year, treated, ref = -2) | country^calendar_month + month,
  data = panel,
  vcov = ~country
)
png("figures/event_study.png", width = 900, height = 500)
iplot(es, main = "Afghanistan minus controls, by year relative to the takeover (Aug-Jul years)")
dev.off()

es_q <- feols(
  log_lights ~ i(event_quarter, treated, ref = -2) | country + month,
  data = panel,
  vcov = ~country
)
png("figures/event_study_quarterly.png", width = 900, height = 500)
iplot(es_q, main = "Afghanistan minus controls, by quarter (country FE, common seasonality)")
dev.off()

placebo_effect <- function(fake_country) {
  fake <- panel |>
    filter(country == fake_country | country != "Afghanistan") |>
    mutate(treated = as.integer(country == fake_country))
  model <- feols(log_lights ~ treated:post | country^calendar_month + month, data = fake)
  coef(model)[["treated:post"]]
}

effects <- sapply(unique(panel$country), placebo_effect)
sort(effects)

mean(abs(effects) >= abs(effects["Afghanistan"]))   
mean(effects <= effects["Afghanistan"])             
1 / length(effects)                                 

fake_time <- panel |>
  filter(month <= "2021-04") |>
  mutate(post = as.integer(month >= "2019-08"))
summary(
  feols(log_lights ~ treated:post | country^calendar_month + month, data = fake_time),
  vcov = ~country
)

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