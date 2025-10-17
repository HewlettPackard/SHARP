#
# Common utilities for GUI
#
# © Copyright 2022--2025 Hewlett Packard Enterprise Development LP

library("LaplacesDemon")
library("moments")
library("processx")
library("changepoint")

bdir <- "../backends/"  # Where to find backend config files
ldir <- "../launcher/"  # Where to find launcher


leftcol="darkgreen"
rightcol="orange"

###############################################################################
# Helper to get filename from shinyFiles - uses stored value if available, otherwise reactive
# This prevents issues when parseFilePaths() returns empty values due to stale state
#
# Usage:
#   fn <- reactive(parseFilePaths(...)$datapath)
#   get_fn <- make_file_getter(fn, storage)
#   storage$filename <- fn()  # Store when file is selected
#   get_fn()                   # Use later to retrieve
make_file_getter <- function(reactive_fn, storage, storage_key = "filename") {
  function() {
    stored <- storage[[storage_key]]
    if (!is.null(stored) && length(stored) > 0) stored else reactive_fn()
  }
}

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
    p95 = quantile(x, 0.95, names=FALSE, na.rm=TRUE),
    p99 = quantile(x, 0.99, names=FALSE, na.rm=TRUE),
    max = max(x),
    stddev = sd(x),
    stderr = se
  ) %>% round(digits=digits)
}


###############################################################################
# Create a distribution graph for a given numeric vector and summary
# If a "divider" value is passed, it's depicted as a horizontal divider, and the
# points on either side of it are painted in different colors.
create_distribution_plot <- function(x, metric, divider=NA)
{
  df <- data.frame(val = x, col = x > divider)
  df[is.na(df)] <- TRUE

  # Count non-NA samples for annotation
  n_count <- sum(!is.na(x))

  p <- ggplot(df, aes(x = val)) +
    stat_halfeye(point_interval = mode_hdi,
                 .width = c(.67, .95),
                 color = "deeppink",
                 trim = F,
                 .point = Mode) +
    geom_boxplot(alpha = 0.2,
                 width = 0.1,
                 outlier.shape = NA,
                 position = position_nudge(y = -.08)) +
    geom_point(aes(y = -.08, color=col),
               fill = "black",
               alpha = 0.6,
               position = position_jitter(seed = 1, height = .04)) +
    scale_color_manual(breaks=c(FALSE, TRUE), values=c(leftcol, rightcol)) +
    xlab(metric) +
    ylab("Density") +
    guides(color = "none") +
    theme_light() +
    theme(text=element_text(size=20))

  # Annotate sample size in the top-right corner
  # Use x=Inf,y=Inf with hjust/vjust to place inside plot margins
  p <- p + annotate("text", x = Inf, y = Inf,
                    label = paste0("n=", fmt(n_count)),
                    hjust = 1.05, vjust = 1.5,
                    size = 5, colour = "black")

  if (!is.na(divider)) {
    p <- p + geom_vline(xintercept=divider, linetype="dotted", color="blue", linewidth=1.5)

    # Add text label with cutoff value
    p <- p + annotate("text", x = divider, y = Inf,
                      label = sprintf("%.2f", divider),
                      hjust = -0.1, vjust = 1.5,
                      angle = 270,
                      size = 5, colour = "blue")
  }

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

############################
# Estimate R^2 from a glm model
rsquared <- function(model)
{
  deviance <- summary(model)$deviance
  null_deviance <- summary(model)$null.deviance
  rsquared <- 1 - (deviance / null_deviance)
}

############################
# Return a list with all the metric names in a dataframe,
# assuming that all numeric columns can be used as metrics.
metric_names <- function(df)
{
  names(select_if(df, is.numeric))
}

############################
# Detect change points using PELT algorithm
# Returns list of change point indices (segment end positions)
detect_change_points <- function(x, model="rbf", pen=NULL, min_size=NULL) {
  # Remove NAs
  x_clean <- na.omit(x)
  n <- length(x_clean)

  if (n < 10) return(list(cps=integer(0), n=n))

  # Set defaults
  if (is.null(min_size)) {
    min_size <- max(3, floor(0.05 * n))  # 5% of sample size
  }
  if (is.null(pen)) {
    # More conservative penalty: 3 * log(n) instead of 2 * log(n)
    pen <- 3 * log(n)
  }

  tryCatch({
    # Use changepoint package's cpt.meanvar for distributional changes
    # or cpt.mean for mean-only changes
    if (model == "rbf" || model == "meanvar") {
      result <- cpt.meanvar(x_clean, method="PELT", penalty="Manual", pen.value=pen, minseglen=min_size)
    } else {
      result <- cpt.mean(x_clean, method="PELT", penalty="Manual", pen.value=pen, minseglen=min_size)
    }
    cps <- cpts(result)
    list(cps=cps, n=n, min_size=min_size, pen=pen)
  }, error = function(e) {
    list(cps=integer(0), n=n, error=e$message)
  })
}

############################
# Estimate autocorrelation lag (where ACF drops below threshold)
estimate_acf_lag <- function(x, threshold=0.2, max_lag=NULL) {
  x_clean <- na.omit(x)
  n <- length(x_clean)

  if (n < 10) return(list(lag=0, max_acf=NA))

  if (is.null(max_lag)) {
    max_lag <- min(floor(n/4), 50)
  }

  tryCatch({
    acf_result <- acf(x_clean, lag.max=max_lag, plot=FALSE)
    acf_vals <- as.numeric(acf_result$acf[-1])  # Exclude lag 0

    # Find first lag where ACF drops below threshold
    below_thresh <- which(abs(acf_vals) < threshold)
    lag <- if (length(below_thresh) > 0) below_thresh[1] else max_lag

    list(lag=lag, max_acf=max(abs(acf_vals), na.rm=TRUE))
  }, error = function(e) {
    list(lag=0, max_acf=NA, error=e$message)
  })
}

############################
# Characterize warmup, cooldown, and change points in a time series
# Returns a narrative string describing temporal patterns
characterize_changepoints <- function(x, model="rbf", pen=NULL, min_size=NULL,
                                     acf_threshold=0.2, warmup_pct=0.3, cooldown_pct=0.7) {
  x_clean <- na.omit(x)
  n <- length(x_clean)

  if (n < 10) return("")

  narrative <- c()

  # ACF analysis
  acf_info <- estimate_acf_lag(x_clean, threshold=acf_threshold)
  if (!is.na(acf_info$max_acf)) {
    if (acf_info$max_acf > 0.5) {
      narrative <- c(narrative, sprintf("Strong autocorrelation detected (max ACF=%.2f at lag ~%d), suggesting performance samples are not truly independent or the system preserves state between runs.",
                                       acf_info$max_acf, acf_info$lag))
    } else if (acf_info$max_acf > 0.2) {
      narrative <- c(narrative, sprintf("Moderate autocorrelation present (max ACF=%.2f), indicating some temporal dependency in measurements.",
                                       acf_info$max_acf))
    }
  }

  # Change point detection
  cp_result <- detect_change_points(x_clean, model=model, pen=pen, min_size=min_size)

  if (length(cp_result$cps) == 0) {
    narrative <- c(narrative, "No significant change points detected; series appears stationary.")
    return(paste(narrative, collapse=" "))
  }

  cps <- cp_result$cps
  n_cps <- length(cps)

  # Identify potential warmup (first CP in early portion)
  warmup_threshold <- floor(warmup_pct * n)
  early_cps <- cps[cps <= warmup_threshold & cps >= cp_result$min_size]

  if (length(early_cps) > 0) {
    warmup_idx <- early_cps[1]
    warmup_pct_actual <- round(100 * warmup_idx / n)

    # Compute median difference and p-value
    warmup_data <- x_clean[1:warmup_idx]
    remainder_data <- x_clean[(warmup_idx+1):n]
    median_diff <- median(remainder_data) - median(warmup_data)
    median_diff_fmt <- if (abs(median_diff) < 0.01 && median_diff != 0) {
      formatC(median_diff, format="e", digits=2)
    } else {
      sprintf("%.2f", median_diff)
    }
    median_diff_pct <- 100 * median_diff / median(warmup_data)

    # Wilcoxon test (robust to non-normality)
    test_result <- tryCatch({
      wilcox.test(warmup_data, remainder_data)
    }, error = function(e) NULL)

      if (!is.null(test_result)) {
        p_str <- format_p_value(test_result$p.value, rounding=3, p_option="rounded")
        narrative <- c(narrative, sprintf(
          "Potential warm-up period detected: first %d samples (%d%% of data; median difference = %s (%.1f%%), %s).",
          warmup_idx, warmup_pct_actual, median_diff_fmt, median_diff_pct, p_str))
      } else {
        narrative <- c(narrative, sprintf(
          "Potential warm-up period detected: first %d samples (%d%% of data).",
          warmup_idx, warmup_pct_actual))
      }
  }

  # Identify potential cooldown (last CP in late portion)
  cooldown_threshold <- floor(cooldown_pct * n)
  late_cps <- cps[cps >= cooldown_threshold & cps <= (n - cp_result$min_size)]

  if (length(late_cps) > 0) {
    cooldown_idx <- late_cps[length(late_cps)]
    cooldown_pct_actual <- round(100 * (n - cooldown_idx) / n)

    # Compute median difference and p-value
    cooldown_data <- x_clean[(cooldown_idx+1):n]
    remainder_data <- x_clean[1:cooldown_idx]
    median_diff <- median(cooldown_data) - median(remainder_data)
    median_diff_fmt <- if (abs(median_diff) < 0.01 && median_diff != 0) {
      formatC(median_diff, format="e", digits=2)
    } else {
      sprintf("%.2f", median_diff)
    }
    median_diff_pct <- 100 * median_diff / median(remainder_data)

    # Wilcoxon test
    test_result <- tryCatch({
      wilcox.test(cooldown_data, remainder_data)
    }, error = function(e) NULL)

      if (!is.null(test_result)) {
        p_str <- format_p_value(test_result$p.value, rounding=3, p_option="rounded")
        narrative <- c(narrative, sprintf(
          "Potential cool-down period detected: last %d samples (%d%% of data; median difference = %s (%.1f%%), %s).",
          n - cooldown_idx, cooldown_pct_actual, median_diff_fmt, median_diff_pct, p_str))
      } else {
        narrative <- c(narrative, sprintf(
          "Potential cool-down period detected: last %d samples (%d%% of data).",
          n - cooldown_idx, cooldown_pct_actual))
      }
  }

  # Report middle change points if any
  middle_cps <- cps[cps > warmup_threshold & cps < cooldown_threshold]
  if (length(middle_cps) > 0) {
    narrative <- c(narrative, sprintf("%d regime change(s) detected in steady-state region.",
                                     length(middle_cps)))
  }

  # Overall summary
  if (n_cps == 1) {
    narrative <- c(narrative, "Single change point suggests a phase transition in the data.")
  }

  paste(narrative, collapse=" ")
}

############################
# Returns a string that defines the type of the distribution in terms of
# modality and skewness.
characterize_distribution <- function(x, skew_thresh=0.5, include_changepoints=TRUE,
                                     cp_model="rbf", cp_pen=NULL, cp_min_size=NULL)
{
  ret <- "Distribution appears to be"
  if (is.amodal(x)) {
    ret <- paste(ret, "amodal,")
  } else if (is.unimodal(x)) {
    ret <- paste(ret, "unimodal,")
  } else if (is.bimodal(x)) {
    ret <- paste(ret, "bimodal,")
  } else if (is.trimodal(x)) {
    ret <- paste(ret, "trimodal,")
  } else if (is.multimodal(x)) {
    ret <- paste(ret, "multimodal,")
  }

  sk <- skewness(x)

  if (is.na(sk)) {
    ret <- paste(ret, "unknown skew.")
  } else if (sk <= -skew_thresh) {
    ret <- paste(ret, "left-skewed.")
  } else if (sk >= skew_thresh) {
    ret <- paste(ret, "right-skewed.")
  } else {
    ret <- paste(ret, "unskewed.")
  }

  # Add change point analysis if requested and sufficient data
  if (include_changepoints && length(na.omit(x)) >= 10) {
    cp_narrative <- characterize_changepoints(x, model=cp_model, pen=cp_pen, min_size=cp_min_size)
    if (nchar(cp_narrative) > 0) {
      ret <- paste(ret, cp_narrative)
    }
  }

#  ret <- paste(ret, "Modes at:")
#  ret <- paste(ret, toString(round(Modes(x)$modes), 2))

  ret
}

############################
# Create a UI selector for a metric depending on its type.
# Adapted from https://mastering-shiny.org/action-dynamic.html
metric_value_ui <- function(x, var, animate=T) {
  label <- "Filter value"

  if (length(unique(x)) <= 1) {
    NULL

  } else if (is.factor(x)) {
    levs <- levels(x)
    selectInput(var, label, choices=levs, selected=levs, multiple=T)

  } else if (is.numeric(x)) {
    # Check that all values are integer and that they're not too diverse:
    if (all(floor(x) == x) && length(x)/length(unique(x)) > 3) {
      sliderInput(var, label, min=min(x), max=max(x), value=min(x), animate=animate)
    } else {
      rng <- range(x, na.rm=T)
      sliderInput(var, label, min=rng[1], max=rng[2], value=rng)
    }

  } else {
    # Not supported
    NULL
  }
}


############################
# Filter a list based on a range of values or value
# Adapted from https://mastering-shiny.org/action-dynamic.html
filter_var <- function(x, val) {
  if (is.numeric(x) && length(unique(x)) > 1) {
    if (length(val) == 1) {
      val[2] = val[1]
    }
    !is.na(x) & x >= val[1] & x <= val[2]
  } else if (is.factor(x)) {
    x %in% val
  } else {
    # No control, so don't filter
    TRUE
  }
}

# Run SHARP in a piped shell with the given command and arguments.
# Monitor its output and show progress as a progress bar.
# Returns filename with base filename for logs.
run_sharp <- function(args, nruns, experiment)
{
  patrun <- paste("Completed run ([0-9]+) for experiment", experiment)
  cmd <- paste0(ldir, "launch.py")
  proc <- process$new(cmd, args, stdout="|")
  logpat <- "Logging runs to: (.*) at"

  print("Running SHARP with args:")
  print(args)

  withProgress(message="Running benchmarks...", value=0, min=1, max=nruns, {
    if (!proc$is_alive()) {
      procout <- proc$read_output_lines()
      print(procout)
      tmp <- str_match(procout, logpat)[,2]
      if (any(!is.na(tmp))) {
        basefn <- tmp[which(!is.na(tmp))]
      }

    } else while (proc$is_alive()) {
      proc$poll_io(-1)
      procout <- proc$read_output_lines()
      print(procout)

      tmp <- str_match(procout, logpat)[,2]
      if (any(!is.na(tmp))) {
        basefn <- tmp[which(!is.na(tmp))]
      }

      if (any(!is.na(str_match(procout, "Warning: task timeout exceeded!")))) {
        showModal(modalDialog("Function timed out, results unusable!"))
      }

      done <- str_match(procout, patrun)[,2]
      incProgress(sum(!is.na(done)))
    }
  })

  if (!exists("basefn")) {
    showModal(modalDialog("Error: Failed to parse program output!"))
    basefn <- ""
  }

  basefn
}


#####################
# Compare (plot) two distribution of a given metric using empirical CDF
ecdf_comparison <- function(baseline, treatment, metric)
{
  perf1 <- baseline %>% pull(metric)
  perf2 <- treatment %>% pull(metric)
  df <- data.frame(Dataset="Baseline", Performance=perf1) %>%
    rbind(data.frame(Dataset="Treatment", Performance=perf2))
  df %>%
    ggplot(aes(x=Performance, color=Dataset)) +
      stat_ecdf(show.legend=TRUE) +
      xlab(metric) +
      ylab("ECDF") +
      scale_color_manual(values=c(base_color, treat_color)) +
      theme_light() +
      theme(text=element_text(size=20), legend.position="bottom")
}

#####################
# Compare two distributions of a given metric using density plots
density_comparison <- function(baseline, treatment, metric)
{
  perf1 <- baseline %>% pull(metric)
  perf2 <- treatment %>% pull(metric)
  df <- data.frame(Dataset="Baseline", Performance=perf1) %>%
    rbind(data.frame(Dataset="Treatment", Performance=perf2))
  df %>%
    ggplot(aes(x=Performance, fill=Dataset)) +
      geom_density(alpha=0.5) +
#      geom_histogram(aes(y=after_stat(count / sum(count))), position=position_dodge()) +
      scale_y_continuous(labels=scales::percent) +
      xlab(metric) +
#      ylab("Relative count") +
      ylab("Density") +
      scale_fill_manual(values=c(base_color, treat_color)) +
      theme_light() +
      theme(text=element_text(size=20), legend.position="bottom")
}


#####################
# Compare two distributions of a given metric in a summary table
comparison_table <- function(baseline, treatment, metric)
{
  perf1 <- baseline %>% pull(metric)
  perf2 <- treatment %>% pull(metric)
  stats1 <- compute_summary(perf1, 10)
  stats2 <- compute_summary(perf2, 10)
  data.frame(Statistic=names(stats1), Baseline=stats1, Treatment=stats2)
}

#####################
# Wrap any UI element (typically a button) with a tooltip
# ui_element: The Shiny UI element to wrap (e.g., actionButton, shinyFilesButton)
# tooltip_text: The text to display on hover
# Returns: A div containing the element with tooltip functionality
with_tooltip <- function(ui_element, tooltip_text) {
  tags$div(
    title = tooltip_text,
    ui_element
  )
}

###############################################################################
######## Statistical test reporting, borrowed from https://github.com/eitanf/sysconf
###############################################################################

####################
# Add separating commas to large numbers:
fmt <- function(x) { format(x, big.mark = ',') }

####################
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

####################
# Compute a string based on p value and a p_option as follows:
# NULL shows nothing (empty string)
# "exact" shows the p value as is
# "stars" returns either "", "*", "**", "***" based on the significance levels *<0.05, **<0.01, ***<0.001
# The default option "rounded" rounds p value or shows it as less than the given precision threshold.
format_p_value <- function(p, rounding = 2, p_option = "rounded") {
  if (p_option == FALSE) {
    return("")
  } else if (p_option == "exact") {
    return(paste0("p=", p))
  } else if (p_option == "stars") {
    return(ifelse(p < 0.001, "***", ifelse(p < 0.01, "**", ifelse(p < 0.05, "*", ""))))
  } else {
    return(rounded_p(p, rounding))
  }
}

####################
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
