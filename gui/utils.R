#
# Common utilities for GUI
#
# © Copyright 2022--2024 Hewlett Packard Enterprise Development LP


###############################################################################
# Compute summary statistics for a given vector and precision and return as vector
compute_summary <- function(x, digits=5)
{
  t.score <- qt(0.025, df=length(x)-1, lower.tail=FALSE)
  se <- sd(x) / sqrt(length(x))

  c(
    n = length(x),
    min = min(x),
    median = median(x),
    mode = Mode(x),
    mean = mean(x),
    CI95_low = mean(x) - t.score * se,
    CI95_high = mean(x) + t.score * se,
    p95 = quantile(x, 0.95, names=FALSE),
    p99 = quantile(x, 0.99, names=FALSE),
    max = max(x),
    stddev = sd(x),
    stderr = se
  ) %>% round(digits=digits)
}


###############################################################################
# Create a distribution graph for a given numeric vector and summary
create_distribution_plot <- function(x, metric)
{
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
    xlab(metric) +
    ylab("Density") +
    theme_light() +
    theme(text=element_text(size=20))

  return(p)
}

###############################################################################
# Read metric data from markdown file
read_metrics <- function(filename)
{
  message(filename)
  txt <- readLines(filename)
  message(txt)
  pat <- ".*?`(?<metric>.*?)` \\((?<type>.*?)\\): (?<desc>.*?) \\((?<units>.*?)\\); (?<better>.*?) is better"
  matches <- str_match_all(txt[grepl("* `", txt)], pat)
  df <- data.frame(do.call(rbind, matches))
  colnames(df)[1] <- "line"
  rownames(df) <- df$metric
  print(df)
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
      return (paste0("p<", 1/(10^rounding)))
    }
    while (p < 10^(-rounding) & rounding < 10) {
      rounding = rounding + 1
    }
    return (paste0("p<10^{", -rounding+1, "}"))
  } else {
    return (paste0("p=", format(round(p, rounding), scientific = F)))
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
    p_option == "exact"      ~ paste0("p=", p),
    p_option == "stars"      ~ ifelse(p < 0.001, "***", ifelse(p < 0.01, "**", ifelse(p < 0.05, "*", ""))),
    TRUE                     ~ rounded_p(p, rounding)
  )
}

###############################################################################
# Return a string to properly format a statistical test.
# Currently supported tests: t.test, cor.test, chisq.test, wilcox.test.
# p_option can be FALSE (don't print p value), "rounded" based on rounding, "exact" for no rounding, or "stars".
report_test <- function(test, rounding = 2, p_option = "rounded") {
  base_str <- ""
  df_str <- ""
  p_str <- format_p_value(test$p.value, rounding, p_option)

  if (test$method == "Welch Two Sample t-test") {
    base_str <- paste0("t=", round(test$statistic, min(rounding, 4)))
  }
  else if (grepl("Pearson's Chi-squared test", test$method)) {
    base_str <- paste0("\\chi{}^2=", round(test$statistic, min(rounding, 4)))
  }
  else if (grepl("Wilcoxon rank sum", test$method)) {
    base_str <- paste0("W=", round(test$statistic, min(rounding, 4)))
  }
  else if (grepl("Pearson's product-moment correlation", test$method)) {
    base_str <- paste0("r=", round(test$estimate, min(rounding, 4)))
  }
  else if (grepl("Kolmogorov-Smirnov test", test$method)) {
    base_str <- paste0("KS=", round(test$statistic, min(rounding, 4)))
  }
  else {
    return(paste("Unsupported test:", test$method))
  }

  ret = paste0(base_str, df_str, ", ", p_str)
}

############################
# Return a list with all the metric names in a dataframe,
# assuming the first metric is called 'outer_time'
metric_names <- function(df)
{
  nms <- colnames(df)
  start <- grep('outer_time', nms)
  nms[c(start:length(nms))]
}
