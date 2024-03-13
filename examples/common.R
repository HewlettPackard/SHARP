#
# Common utilities for reporting functions
#
# © Copyright 2022--2023 Hewlett Packard Enterprise Development LP

require('tidyverse')
require('ggdist')
require('knitr')
require('stringr')


###############################################################################
# Compute summary statistics for a given vector, metric name, and precision
# Append summary to the global all.summary (mus be pre-initialized outside).
compute_summary <- function(x, metric, digits = 4)
{
  df <- data.frame(Metric = metric,
                   n = length(x),
                   min = round(min(x), digits),
                   median = round(median(x), digits),
                   mode = round(Mode(x), digits),
                   mean = round(mean(x), digits),
                   max = round(max(x), digits),
                   SE = sd(x) / length(x))
  if (exists("all.summary")) {
    all.summary <<- bind_rows(all.summary, df)
  }
  return(df)
}


###############################################################################
# Create a distribution graph for a given numeric vector and summary
create_distribution_plot <- function(x, smry)
{
  ydist <- 0.07
  p <- data.frame(val = x) %>%
    ggplot(aes(x = val)) +
      stat_halfeye(point_interval = mode_hdi,
                   .width = c(.67, .95),
                   color = "deeppink",
                   trim = F,
                   .point = Mode) +
      geom_boxplot(alpha = 0.2,
                   width = 0.1,
                   outlier.shape = NA,
                   position = position_nudge(y = -.08)) +
      geom_point(aes(y = -.08),
                 fill = "black",
                 color = "orange",
                 alpha = 0.4,
                 position = position_jitter(seed = 1, height = .04)) +
      geom_text(aes(x = max(val)),
                    y = 1 - ydist * 0,
                label = paste0("n=", smry$n),
                hjust = 0.5) +
      geom_text(aes(x = max(val)),
                    y = 1 - ydist * 1,
                label = paste0("M=", format(smry$mean, digits = 4)),
                hjust = 0.5) +
      geom_text(aes(x = max(val)),
                    y = 1 - ydist * 2,
                label = paste0("Mdn=", format(smry$median, digits = 4)),
                hjust = 0.5) +
      geom_text(aes(x = max(val)),
                    y = 1 - ydist * 3,
                label = paste0("Mode=", format(smry$mode, digits = 4)),
                hjust = 0.5) +
    xlab(smry$Metric) +
    ylab("Density") +
    theme_light()

  return(p)
}

###############################################################################
# Read metric data from markdown file
read_metrics <- function(filename)
{
  txt <- readLines(filename)
  pat <- ".*?`(?<metric>.*?)` \\((?<type>.*?)\\): (?<desc>.*?) \\((?<units>.*?)\\); (?<better>.*?) is better"
  matches <- str_match_all(txt[grepl("* `", txt)], pat)
  df <- data.frame(do.call(rbind, matches))
  colnames(df)[1] <- "line"
  rownames(df) <- df$metric
  return(df)
}

###############################################################################
######## Statistical test reporting, borrowed from https://github.com/eitanf/sysconf
###############################################################################

###############################################################################
# Add separating commas to large numbers:
fmt <- function(x) { format(x, big.mark = ',') }

###############################################################################
# Return a string that properly formats a p-value (too small becomes <)
rounded_p <- function(p, rounding) {
  if (p < 10^(-rounding)) {
    if (p > 10^(-(rounding+1))) {
      return (paste0("$p<", 1/(10^rounding), "$"))
    }
    while (p < 10^(-rounding) & rounding < 10) {
      rounding = rounding + 1
    }
    return (paste0("$p<10^{", -rounding+1, "}$"))
  } else {
    return (paste0("$p=", format(round(p, rounding), scientific = F), "$"))
  }
}

###############################################################################
# Compute a string based on p value and a p_option as follows:
# NULL shows nothing (empty string)
# "exact" shows the p value as is
# "stars" returns either "", "*", "**", "***" based on the significance levels *<0.05, **<0.01, ***<0.001
# The default option "rounded" rounds p value or shows it as less than the given precision threshold.
format_p_value <- function(p, rounding = 2, p_option = "rounded") {
  case_when(
    p_option == FALSE        ~ "",
    p_option == "exact"      ~ paste0("$p=", p, "$"),
    p_option == "stars"      ~ ifelse(p < 0.001, "***", ifelse(p < 0.01, "**", ifelse(p < 0.05, "*", ""))),
    TRUE                     ~ rounded_p(p, rounding)
  )
}

###############################################################################
# Return a string to properly format a statistical test.
# Currently supported tests: t.test, cor.test, chisq.test, wilcox.test.
# p_option can be FALSE (don't print p value), "rounded" based on rounding, "exact" for no rounding, or "stars".
# stat_stat either reports the value of the test statistic or noot (boolean).
# show_df eith reports degrees of freedom.
report_test <- function(test, rounding = 2, p_option = "rounded", show_stat = TRUE, show_df = FALSE) {
  base_str <- ""
  df_str <- ""
  p_str <- format_p_value(test$p.value, rounding, p_option)

  if (show_stat) {
    if (test$method == "Welch Two Sample t-test") {
      base_str <- paste0("$t=", round(test$statistic, min(rounding, 4)), "$")
    }
    else if (grepl("Pearson's Chi-squared test", test$method)) {
      base_str <- paste0("$\\chi{}^2=", round(test$statistic, min(rounding, 4)), "$")
    }
    else if (grepl("Wilcoxon rank sum test", test$method)) {
      base_str <- paste0("$W=", round(test$statistic, min(rounding, 4)), "$")
    }
    else if (test$method == "Pearson's product-moment correlation") {
      base_str <- paste0("$r=", round(test$estimate, min(rounding, 4)), "$")
    }
    else {
      return("Unsupported test!")
    }
  }

  if (show_df) {
      df_str <- paste0(ifelse(show_stat, ", ", ""), "$df=", round(test$parameter, 0), "$")
  }

  ret = paste0(base_str, df_str)
  if (p_option != "stars" & p_option != FALSE & show_stat) {
    ret = paste0(ret, ", ")
  }
  paste0(ret, p_str)
}
