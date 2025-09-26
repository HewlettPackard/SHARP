#
# Common utilities for GUI
#
# © Copyright 2022--2025 Hewlett Packard Enterprise Development LP

library("LaplacesDemon")
library("moments")
library("processx")

bdir <- "../backends/"  # Where to find backend config files
ldir <- "../launcher/"  # Where to find launcher


leftcol="darkgreen"
rightcol="orange"

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

  if (!is.na(divider)) {
    p <- p + geom_vline(xintercept=divider, linetype="dotted", color="blue", linewidth=1.5)
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
# Returns a string that defines the type of the distribution in terms of
# modality and skewness.
characterize_distribution <- function(x, skew_thresh=0.5)
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
  case_when(
    p_option == FALSE        ~ "",
    p_option == "exact"      ~ paste0("p=", p),
    p_option == "stars"      ~ ifelse(p < 0.001, "***", ifelse(p < 0.01, "**", ifelse(p < 0.05, "*", ""))),
    TRUE                     ~ rounded_p(p, rounding)
  )
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
