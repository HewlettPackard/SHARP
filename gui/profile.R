# UI for Profile tab
# © Copyright 2024--2024 Hewlett Packard Enterprise Development LP

library("fansi")
library("stringr")
library("tools")
library("regclass")
library("rpart")
library("sparkline")
library("visNetwork")
library("yaml")
library("ggplot2")
library("dplyr")

# Try to load data.table for faster file reading, fallback to readr if not available
if (require("data.table", quietly = TRUE)) {
  fast_read_csv <- function(file, ...) as.data.frame(fread(file, showProgress = FALSE, ...))
} else {
  library("readr")
  fast_read_csv <- function(file, ...) read_csv(file, ...)
}

factors <- read_yaml("factors.yaml")
mitigations <- read_yaml("mitigations.yaml")
MAX_SEARCH <- 100  # Maximum no. of distinct cutoff points to search for
MAX_PREDICTORS <- 100 # Maximum no. of predictors for decision tree
MAX_CORRELATION <- 0.99 # Maximum correlation to include in tree model (excludes >= this value)
not_predictors <- c("repeat", "inner_time", "outer_time", "perf_time")

######################################
optimizePanel <- tabPanel('Profile',
  sidebarLayout(
    sidebarPanel(
      fluidRow(
        column(7, p("Select experiment to profile")),
        column(5,
          div(style="text-align: right;",
            uiOutput("profileFileButton")
          )
        ),
      ),

      conditionalPanel(condition="output.profileDataLoaded",
        fluidRow(
          column(6, selectizeInput('profileMetric', "Outcome metric", choices=NULL, options = list(maxOptions = 50000))),
          column(6,
            div(style="text-align: right; margin-top: 25px;",
              actionButton("selectPredictors", "Exclude predictors", class="btn-secondary", icon=icon("table"))
            )
          ),
        ),
        fluidRow(
          column(6, selectizeInput('profileFilterMetric', "Metric to limit to", choices=NULL, options = list(maxOptions = 50000))),
          column(6, uiOutput('profileFilterUI')),
        ),
        p("Click on density plot to change classifier cutoff"),
        p("Click on a tree node to inspect performance factor"),
        fluidRow(
          column(8,
            p('Click here for an exhustive search for a cutoff point to minimize AIC'),
          ),
          column(4,
            div(style="text-align: right;",
              actionButton("searchForCutoff", label="Search", class="btn-secondary", icon=icon("magnifying-glass"))
            )
          ),
        ),
      ),


      hr(),

      conditionalPanel(condition="input.currentNode != null",
        tabsetPanel(
          id="factorTab",
  #        type="hidden",

          tabPanel("Factor description",
            htmlOutput("factorDescription"),
            p(),
            actionButton("askLlamaAboutFactor", label="Ask Llama", class="btn-info", icon=icon("comments")),
            actionButton("codeHotspots", label="Code hotspots", class="btn-warning", icon=icon("fire")),
          ),

          tabPanel("Suggested mitigations",
            fluidRow(
              column(6, p("Choose mitigation:", style="margin-top: 20px;")),
              column(6, selectInput('mitigationSelector', "", choices=c())),
            ),
            htmlOutput("mitigationDescription"),
            p(),
            actionButton("predictMitigation", label="Predict impact", class="btn-info", icon=icon("chart-line")),
            actionButton("tryMitigation", label="Try it", class="btn-success", icon=icon("play")),

            conditionalPanel(condition="output.mitigationDataLoaded",
              fluidRow(
                column(6, p("Metric to compare:", style="margin-top: 20px;")),
                column(6, selectInput('mitigationCompareMetric', "", choices=c("outer_time"))),
              ),
            ),
          ),
        ),
      ),
    ),

    mainPanel(
      fluidRow(
        column(6,
               plotOutput('profilerOutput', click="profilerClick"),
               textOutput('profileCharacteristics'),
               plotOutput('factorVsPerf'),
              ),

        column(6, visNetworkOutput('profileTreeOutput')),
      ),

      fluidRow(
        column(6, plotOutput('compareMitigationDensity')),
        column(6, tableOutput('compareMitigationTable')),
      ),
    ),
  )
)

######################################
# Suggest a cutoff point for classification based on the character of the
# distribution of the vector x.
suggest_cutoff <- function(x) {
  if (length(x) <= 5) {
    return(median(x, na.rm = TRUE))
  }

  if (is.unimodal(x) || is.amodal(x)) {
    skew <- skewness(x)

    if (is.na(skew)) {
      return(median(x, na.rm = TRUE))
    }

    if (skew <= -0.5) {    # Left-tailed
      return(quantile(x, 0.25, names = FALSE, na.rm = TRUE)[[1]])
    } else if (skew >= 0.5) {   # Right-tailed
      return(quantile(x, 0.75, names = FALSE, na.rm = TRUE)[[1]])
    } else {  # Symmetric distribution
      modes_result <- Modes(x)
      return(modes_result$modes[1])
    }
  } else { # Multimodal, return midpoint between largest two modes
    modes_result <- Modes(x)
    p1 <- modes_result$modes[1]
    p2 <- modes_result$modes[2]
    return((p1 + p2) / 2)
  }
}

######################################
# Compute generalized correlation between any predictor and numeric outcome
# Returns value in range [-1, 1] for both numeric and categorical predictors
compute_generalized_correlation <- function(x, y) {
  # Remove rows where either x or y is NA
  complete_cases <- complete.cases(x, y)
  x_clean <- x[complete_cases]
  y_clean <- y[complete_cases]

  # Need at least 2 observations
  if (length(x_clean) < 2 || length(y_clean) < 2) {
    return(NA)
  }

  # Check if predictor has variance
  if (length(unique(x_clean)) <= 1 || length(unique(y_clean)) <= 1) {
    return(NA)
  }

  # For numeric predictors: use Pearson correlation
  if (is.numeric(x_clean) && is.numeric(y_clean)) {
    tryCatch({
      if (sd(x_clean) > 0 && sd(y_clean) > 0) {
        return(suppressWarnings(cor(x_clean, y_clean)))
      }
      return(NA)
    }, error = function(e) NA)
  }

  # For categorical predictors: use eta-squared (effect size) from ANOVA
  # Convert to correlation-like scale: sqrt(eta^2) with sign based on direction
  if (!is.numeric(x_clean) && is.numeric(y_clean)) {
    tryCatch({
      # Convert to factor
      x_factor <- as.factor(x_clean)

      # Need at least 2 groups
      if (length(levels(x_factor)) < 2) {
        return(NA)
      }

      # Compute ANOVA
      aov_result <- aov(y_clean ~ x_factor)
      aov_summary <- summary(aov_result)[[1]]

      # Calculate eta-squared (SS_between / SS_total)
      ss_between <- aov_summary["x_factor", "Sum Sq"]
      ss_total <- sum(aov_summary[, "Sum Sq"])
      eta_squared <- ss_between / ss_total

      # Convert to correlation scale (take square root)
      eta <- sqrt(eta_squared)

      # Determine sign based on whether first level has higher or lower mean
      level_means <- tapply(y_clean, x_factor, mean)
      sign_direction <- ifelse(level_means[1] < level_means[length(level_means)], 1, -1)

      return(eta * sign_direction)
    }, error = function(e) NA)
  }

  # For other cases (y not numeric, etc.)
  return(NA)
}

######################################
# Safely compute correlation on sampled valid pairs
safe_correlation <- function(x, y, min_pairs = 3) {
  valid_idx <- which(!is.na(x) & !is.na(y))
  if (length(valid_idx) <= min_pairs) return(NA)

  x_clean <- x[valid_idx]
  y_clean <- y[valid_idx]

  if (length(unique(x_clean)) <= 1 || length(unique(y_clean)) <= 1) return(NA)

  tryCatch({
    if (sd(x_clean) == 0 || sd(y_clean) == 0) return(NA)
    suppressWarnings(cor(x_clean, y_clean))
  }, error = function(e) NA)
}

######################################
# Compute predictor statistics for the exclusion dialog table
get_predictor_stats_table <- function(data, metric, predictors) {
  if (length(predictors) == 0) return(data.frame())

  # Sample rows for faster correlation
  sample_rows <- if (nrow(data) > 1000) sample(nrow(data), 1000, replace = FALSE) else seq_len(nrow(data))
  set.seed(42)

  stats <- lapply(predictors, function(pred) {
    corr <- tryCatch({
      compute_generalized_correlation(data[[pred]][sample_rows], data[[metric]][sample_rows])
    }, error = function(e) NA)

    data.frame(
      Predictor = pred,
      `Non-NA Count` = sum(!is.na(data[[pred]])),
      Correlation = if (is.na(corr)) NA else sprintf("%.3f", corr),
      AbsCorr = if (is.na(corr)) 0 else abs(corr),
      stringsAsFactors = FALSE,
      check.names = FALSE
    )
  })

  result <- do.call(rbind, stats)

  # Sort by absolute correlation, NAs last
  result <- result[order(-result$AbsCorr, is.na(result$Correlation)), ]
  result$AbsCorr <- NULL
  result
}

######################################
# Selects the best predictors for building a decision tree.
select_tree_predictors <- function(data, metric, exclude, max_predictors = MAX_PREDICTORS, max_correlation = MAX_CORRELATION) {
  # Exclude columns with 1 or fewer unique non-NA values, user-defined exclusions, the metric, and "cat"
  # Optimized for large datasets: sample first 100 rows to find constant columns
  if (ncol(data) > 1000) {
    sample_check <- data[1:min(100, nrow(data)), ]
    constant_cols <- names(sample_check)[sapply(sample_check, function(x) length(unique(na.omit(x)))) <= 1]
  } else {
    constant_cols <- names(data)[sapply(data, function(x) length(unique(na.omit(x)))) <= 1]
  }

  all_exclude <- unique(c(exclude, constant_cols, metric, "cat"))
  potential_predictors <- setdiff(names(data), all_exclude)

  # Separate numeric and non-numeric predictors
  is_numeric_col <- sapply(data[potential_predictors], is.numeric)
  numeric_predictors <- potential_predictors[is_numeric_col]
  non_numeric_predictors <- potential_predictors[!is_numeric_col]

  # Validate max_predictors
  if (is.null(max_predictors) || is.na(max_predictors) || max_predictors <= 0) {
    max_predictors <- MAX_PREDICTORS
  }

  # If we have many numeric predictors, select the top N most correlated ones
  if (length(numeric_predictors) > max_predictors) {
    # Sample rows for faster correlation on large datasets
    sample_rows <- if (nrow(data) > 1000) sample(nrow(data), 1000, replace = FALSE) else seq_len(nrow(data))
    set.seed(42)

    correlations <- sapply(numeric_predictors, function(colname) {
      safe_correlation(data[[colname]][sample_rows], data[[metric]][sample_rows])
    })

    # Filter out NA correlations and get absolute values
    abs_correlations <- abs(correlations[!is.na(correlations)])

    # Filter out correlations >= max_correlation (including perfect correlations)
    filtered_correlations <- abs_correlations[abs_correlations < max_correlation]

    # Fallback if all correlations are >= max_correlation
    if (length(filtered_correlations) == 0) {
      filtered_correlations <- abs_correlations[abs_correlations < 1.0]
      if (length(filtered_correlations) == 0) {
        filtered_correlations <- abs_correlations  # Last resort fallback
      }
    }

    # Select top predictors
    num_to_select <- min(max_predictors, length(filtered_correlations))
    filtered_names <- names(filtered_correlations)
    top_numeric_predictors <- filtered_names[order(filtered_correlations, decreasing = TRUE)[1:num_to_select]]

    # Combine top numeric predictors with any non-numeric ones
    final_predictors <- c(top_numeric_predictors, non_numeric_predictors)
  } else {
    final_predictors <- potential_predictors
  }

  return(final_predictors)
}

# Builds a formula string for rpart from a list of predictors.
build_tree_formula <- function(predictors) {
  if (length(predictors) == 0) {
    return(NULL)
  }
  # Wrap predictor names in backticks for safety (e.g., against reserved keywords)
  paste("cat ~", paste0("`", predictors, "`", collapse = " + "))
}

######################################
# Create a plot of influential factors based on a decision tree
compute_tree <- function(data, metric, cutoff, exclude, max_correlation = MAX_CORRELATION, max_predictors = MAX_PREDICTORS) {
  # Create binary classification
  data$cat <- factor(ifelse(data[[metric]] > cutoff, "RIGHT", "LEFT"))

  # Check for single-category data or missing metric
  if (length(unique(data$cat)) < 2 || !(metric %in% colnames(data))) {
    return(NULL)
  }

  # Select predictors
  final_predictors <- select_tree_predictors(data, metric, exclude, max_predictors, max_correlation)
  if (length(final_predictors) == 0) return(NULL)

  # Build model data: subset columns and remove zero-variance predictors
  model_data <- data[, intersect(c(final_predictors, "cat"), colnames(data)), drop = FALSE]
  model_data <- model_data[, sapply(model_data, function(x) length(unique(na.omit(x))) > 1), drop = FALSE]

  if (!"cat" %in% colnames(model_data) || ncol(model_data) <= 1) return(NULL)

  # Fit tree using na.rpart to handle sparse data
  tryCatch({
    rpart(as.formula(build_tree_formula(setdiff(colnames(model_data), "cat"))),
          data = model_data,
          na.action = na.rpart)
  }, error = function(e) NULL)
}

######################################
# Create a plot of influential factors based on a decision tree
plot_tree <- function(tr)
{
  visTree(tr,
          legend=FALSE,
          fallenLeaves=TRUE,
          colorY=c(leftcol, rightcol),
   #, main="Performance classification tree", width="100%")
          ) %>%
#    visOptions(nodesIdSelection = list(enabled=TRUE)) %>%
    visEvents(selectNode="function(e) {
                Shiny.onInputChange('currentNode', this.body.data.nodes.get(e.nodes[0])); }")
}

######################################
# Create a scatter plot showing the relationship between the selected performance
# metric and the select perf factor from the profiler.
plot_factor_perf <- function(data, cutoff, performance_metric, profiler_factor)
{
  data$cat <- ifelse(data[[performance_metric]] > cutoff, "RIGHT", "LEFT")
  data$cat <- as.factor(data$cat)
  varmodel <- glm(data=data, as.formula(paste(performance_metric, "~", profiler_factor)))
  logmodel <- glm(data=data, as.formula(paste("cat ~", profiler_factor)), family="binomial")
  title <- paste0(profiler_factor, " explains ",
                     round(100 * rsquared(varmodel), 2),
                     "% of the variation in ", performance_metric, " and\n",
                     round(100 * rsquared(logmodel), 2),
                     "% of the variation in the performance classes.")

  data %>%
    ggplot(aes(x=.data[[profiler_factor]], y=.data[[performance_metric]], color=cat)) +
      geom_point() +
      scale_color_manual(breaks=c("LEFT", "RIGHT"), values=c(leftcol, rightcol)) +
      ylab(performance_metric) +
      xlab(profiler_factor) +
      guides(color = "none") +
      theme_light() +
      theme(text=element_text(size=20), plot.title=element_text(size=12)) +
      ggtitle(title)
}

######################################
# Define a search space for cutoff points and find within it the point that mimimizes
# the decision tree's AIC. The search space is limited to MAX_SEARCH points.
# Return the point in the search space that had the lowest AIC.
search_for_cutoff <- function(profdata, metric, exclude, max_correlation = MAX_CORRELATION, max_predictors = MAX_PREDICTORS)
{
  min_aic <- 1e10
  perf <- profdata[[metric]]
  max_points <- min(MAX_SEARCH, length(perf))
  best_pt <- perf[1]

  search_points <- seq(min(perf), max(perf), length.out=max_points)

  for (i in seq_along(search_points)) {
    pt <- search_points[i]
    tr <- compute_tree(profdata, metric, pt, exclude, max_correlation, max_predictors)
    if (!is.null(tr) && nrow(tr$cptable) > 1) {  # Only search for valid trees with more than one node
      aic <- summarize_tree(tr)$aic
      if (aic < min_aic) {
        min_aic <- aic
        best_pt <- pt
      }
    }

    # Update progress if we're in a Shiny context
    if (exists("incProgress", where = parent.frame(), mode = "function")) {
      incProgress(1/max_points, detail = paste("Point", i, "of", max_points))
    }
  }

  best_pt
}


######################################
# Generate an HTML list of hyperlinks from a named list of references
link_list <- function(refs)
{
  links <- "<br/><b>References:</b> "
  for (l in names(refs)) {
    links <- paste0(links, '[<a href="', refs[[l]], '" target="-blank">', l, '</a>] ')
  }
  links
}


######################################
# Extract all the text and links for a given factor and return as an HTML string
render_factor_data <- function(factor)
{
  title <- paste0("<h4>", factor, "</h4>")
  descr <- factors[[factor]]$description
  links <- link_list(factors[[factor]]$references)
  HTML(paste(title, descr, links, sep='<br/>'))
}

######################################
# HELPER FUNCTIONS FOR PREDICTOR MANAGEMENT
######################################

# Find the best default metric by selecting the numeric column with highest kurtosis
select_default_metric <- function(data, valid_metrics, preferred_metrics = c("perf_time", "inner_time")) {
  # Check preferred metrics first
  for (pref in preferred_metrics) {
    if (pref %in% valid_metrics) {
      return(pref)
    }
  }

  # Find numeric column with highest kurtosis
  numeric_metrics <- valid_metrics[sapply(data[valid_metrics], is.numeric)]
  if (length(numeric_metrics) > 0) {
    kurtosis_values <- sapply(data[numeric_metrics], function(x) {
      x_clean <- na.omit(x)
      if (length(x_clean) < 4) return(NA)  # Need at least 4 values for kurtosis
      tryCatch({
        kurtosis(x_clean)
      }, error = function(e) NA)
    })
    # Filter out NA values
    valid_kurtosis <- kurtosis_values[!is.na(kurtosis_values)]
    if (length(valid_kurtosis) > 0) {
      return(names(which.max(valid_kurtosis)))
    }
  }

  # Fallback to first valid metric
  return(valid_metrics[1])
}

# Calculate high-correlation predictors that should be auto-excluded
find_high_correlation_predictors <- function(data, metric, base_excluded, threshold) {
  potential_predictors <- setdiff(colnames(data), c(base_excluded, metric, "cat"))

  # Sample rows if dataset is large to speed up correlation computation
  sampled_data <- if (nrow(data) > 1000) data[sample(nrow(data), 1000), ] else data

  high_corr_predictors <- c()
  for (pred in potential_predictors) {
    corr <- compute_generalized_correlation(sampled_data[[pred]], sampled_data[[metric]])
    if (!is.na(corr) && abs(corr) >= threshold) {
      high_corr_predictors <- c(high_corr_predictors, pred)
    }
  }

  return(high_corr_predictors)
}

# Initialize or reset predictor dialog state to defaults
reset_predictor_dialog_state <- function(global) {
  global$predictor_max_corr <- MAX_CORRELATION
  global$predictor_max_predictors <- MAX_PREDICTORS
  global$predictor_search <- ""
  global$full_stats_table <- NULL
}

# Initialize excluded predictors with base exclusions and high-correlation auto-exclusions
initialize_excluded_predictors <- function(global, data, metric) {
  base_excluded <- intersect(not_predictors, colnames(data))

  if (!is.null(metric) && metric != "") {
    if (is.null(global$predictor_max_corr)) {
      global$predictor_max_corr <- MAX_CORRELATION
    }
    high_corr <- find_high_correlation_predictors(data, metric, base_excluded, global$predictor_max_corr)
    global$excluded_predictors <- unique(c(base_excluded, high_corr))
  } else {
    global$excluded_predictors <- base_excluded
  }
}

# Determine if a predictor checkbox should be checked
is_predictor_excluded <- function(predictor, correlation, max_corr, excluded_list) {
  # Check if correlation exceeds threshold (handle NA correlations)
  if (!is.na(correlation)) {
    exceeds_threshold <- abs(as.numeric(correlation)) >= max_corr
    if (exceeds_threshold) {
      return(TRUE)  # Must be checked if correlation exceeds threshold
    }
  }

  # Otherwise, only check if manually excluded
  return(predictor %in% excluded_list)
}

# Create a single table row for predictor dialog
create_predictor_table_row <- function(row_index, stats_table, max_corr, excluded_list) {
  pred <- stats_table$Predictor[row_index]
  corr_val <- stats_table$Correlation[row_index]
  is_excluded <- is_predictor_excluded(pred, corr_val, max_corr, excluded_list)

  checkbox_ui <- checkboxInput(paste0("exclude_", pred), label = NULL, value = is_excluded)

  tags$tr(
    tags$td(stats_table$Predictor[row_index]),
    tags$td(stats_table$`Non-NA Count`[row_index]),
    tags$td(stats_table$Correlation[row_index]),
    tags$td(checkbox_ui)
  )
}

# Get predictor parameters with fallback to defaults
get_excluded_predictors <- function(global) {
  if (!is.null(global$excluded_predictors)) global$excluded_predictors else character(0)
}

get_max_correlation <- function(global, input) {
  val <- if (!is.null(input$predictorMaxCorr)) input$predictorMaxCorr else if (!is.null(global$predictor_max_corr)) global$predictor_max_corr else MAX_CORRELATION
  # Ensure valid numeric value between 0 and 1
  if (is.na(val) || !is.numeric(val) || val <= 0 || val > 1) MAX_CORRELATION else val
}

get_max_predictors <- function(global, input) {
  val <- if (!is.null(input$predictorMaxPredictors)) input$predictorMaxPredictors else if (!is.null(global$predictor_max_predictors)) global$predictor_max_predictors else MAX_PREDICTORS
  # Ensure valid numeric value
  if (is.na(val) || !is.numeric(val) || val <= 0) MAX_PREDICTORS else val
}

# Load and initialize profile data with smart defaults
load_profile_data <- function(global, filepath, input, session) {
  global$rawdata <- fast_read_csv(filepath)
  mnames <- colnames(global$rawdata)

  # Only allow metrics with >1 unique non-NA value
  valid_metrics <- mnames[sapply(global$rawdata[mnames], function(x) length(unique(na.omit(x))) > 1)]

  # Select default metric using helper function
  sel <- select_default_metric(global$rawdata, valid_metrics)

  updateSelectizeInput(session, inputId='profileMetric', choices=valid_metrics, selected=sel, server = TRUE)
  global$excluded_predictors <- intersect(not_predictors, colnames(global$rawdata))
  reset_predictor_dialog_state(global)
}

######################################
render_optimize <- function(input, output, session) {
  global <- reactiveValues()
  shinyFileChoose(input, 'profileFile', roots=c(logdir='../runlogs'), filetypes=c('md'))
  mdfn <- reactive(parseFilePaths(roots=c(logdir='../runlogs'), input$profileFile)$datapath)

  # Helpers to get metadata filenames - use stored values if available, otherwise reactive
  get_mdfn <- make_file_getter(mdfn, global, "mdfn")
  get_mitigation_mdfn <- make_file_getter(mdfn, global, "mitigation_mdfn")

  proffn <- reactive(gsub(".md", "-prof.csv", get_mdfn()))
  markdown <- reactive(scan(get_mdfn(), what="character", sep="\n"))
  dataset <- reactive({
    req(length(get_mdfn()) > 0)  # Require that a file is selected
    csv_file <- gsub(".md", ".csv", get_mdfn())
    if (file.exists(csv_file)) {
      fast_read_csv(csv_file)
    } else {
      data.frame()
    }
  })
  mitfn <- reactive(gsub(".md", sprintf("-%s.csv", input$mitigationSelector), mdfn()))

  observeEvent(input$profileFile, {
    req(nrow(dataset()) > 0)
    # Store the metadata filename for later use
    global$mdfn <- mdfn()
    # If dataset contains profile data, ask to pick another file
    if ("perf_time" %in% names(dataset())) {
      showModal(modalDialog(
        title = "Profile data exists",
        "This file already has profiler data. Pick another file with raw performance data.",
        easyClose = TRUE,
      ))
    }

    # If -prof exist, reuse, rerun, or cancel
    else if (file.exists(gsub(".md", "-prof.md", get_mdfn()))) {
      showModal(modalDialog(
        title = "Profile data already exists for this run",
        "What to do with existing profile data?",
        footer = tagList(
          modalButton("Cancel"),
          actionButton("useProfileData", "Use data", class="btn-primary", icon=icon("recycle")),
          actionButton("runProfiler", "Rerun profile", class="btn-success", icon=icon("fingerprint"))
        )
      ))
    }

    # Otherwise, confirm profiling and execute
    else {
      orig_t <- str_extract(markdown()[1], "total experiment time: ([:digit:]+)s", group=1)
      showModal(modalDialog(
        title = "Confirm rerun",
        paste("Confirm rerunning with profling data.\nOriginal experiment took", orig_t, "seconds."),
        footer = tagList(
          modalButton("Cancel"),
          actionButton("runProfiler", "Run", class="btn-success", icon=icon("fingerprint"))
        )
      ))
    }
  })

  # Load profiling data from existing, previous file:
  observeEvent(input$useProfileData, {
    withProgress(message = 'Loading profile data...', value = 0, {
      incProgress(0.3, detail = "Reading CSV file")
      incProgress(0.7, detail = "Processing columns")
      global$loaded_filename <- proffn()
      load_profile_data(global, proffn(), input, session)
      removeModal()
    })
  })

  # Launch SHARP to rerun experiment with profiling data:
  observeEvent(input$runProfiler, {
    task <- paste0(tools::file_path_sans_ext(basename(get_mdfn())), "-prof")
    reps <- as.numeric(first(na.omit(str_extract(markdown(), '"max": ([:digit:]+)', group=1))))
    experiment <- first(na.omit(str_extract(markdown(), '"experiment": "(.*)"', group=1)))
    print(paste("Running profiler for", task, "experiment:", experiment, "with repetitions:", reps))
    args <- c("-v",
              "--repro", unname(get_mdfn()),
              "-f", paste0(bdir, "perf.yaml"),
              "-b", "perf",
              "-t", task)

    removeModal()
    run_sharp(args, reps, experiment)

    withProgress(message = 'Loading new profile data...', value = 0, {
      incProgress(0.5, detail = "Reading CSV file")
      incProgress(0.9, detail = "Processing columns")
      load_profile_data(global, proffn(), input, session)
    })
  })


  # Show dialog for predictor selection when button is clicked
  observeEvent(input$selectPredictors, {
    req(nrow(global$rawdata) > 0)
    req(!is.null(input$profileMetric) && input$profileMetric != "")

    # Initialize reactive values for dialog
    if (is.null(global$predictor_max_corr)) {
      global$predictor_max_corr <- MAX_CORRELATION
    }
    if (is.null(global$predictor_max_predictors)) {
      global$predictor_max_predictors <- MAX_PREDICTORS
    }
    if (is.null(global$predictor_search)) {
      global$predictor_search <- ""
    }

    # Get ALL potential predictors without correlation filtering for the dialog
    # Use isolate to prevent reactive dependencies on current selections
    all_predictors <- isolate(select_tree_predictors(global$rawdata, input$profileMetric, exclude = character(0), max_predictors = global$predictor_max_predictors, max_correlation = 1.0))
    stats_table <- isolate(get_predictor_stats_table(global$rawdata, input$profileMetric, all_predictors))

    # Store full table for filtering
    global$full_stats_table <- stats_table

    # Create checkbox inputs for each predictor
    checkbox_ui <- lapply(1:nrow(stats_table), function(i) {
      pred <- stats_table$Predictor[i]
      is_excluded <- pred %in% global$excluded_predictors
      checkboxInput(paste0("exclude_", pred), label = NULL, value = is_excluded)
    })

    showModal(modalDialog(
      title = paste("Select Predictors to Exclude from", input$profileMetric, "Model"),
      size = "l",
      easyClose = FALSE,
      fluidRow(
        column(4,
          sliderInput("predictorMaxCorr", "Max correlation to include:",
                     min = 0, max = 1.0, value = global$predictor_max_corr, step = 0.01)
        ),
        column(4,
          numericInput("predictorMaxPredictors", "Max predictors to show:",
                      value = global$predictor_max_predictors, min = 1, max = 1000, step = 1)
        ),
        column(4,
          textInput("predictorSearch", "Search predictor:", value = global$predictor_search,
                   placeholder = "Type to filter...")
        )
      ),
      uiOutput("predictorTableUI"),
      footer = tagList(
        modalButton("Cancel"),
        actionButton("applyPredictorExclusion", "Apply", class = "btn-success")
      )
    ))
  })

  # Render predictor table dynamically based on filters
  output$predictorTableUI <- renderUI({
    req(!is.null(global$full_stats_table))
    req(nrow(global$full_stats_table) > 0)

    stats_table <- global$full_stats_table

    # Apply search filter if present
    if (!is.null(input$predictorSearch) && input$predictorSearch != "" && nchar(input$predictorSearch) > 0) {
      search_pattern <- tolower(input$predictorSearch)
      matches <- grepl(search_pattern, tolower(stats_table$Predictor))
      stats_table <- stats_table[matches, , drop = FALSE]
    }

    if (nrow(stats_table) == 0) {
      return(tags$p("No predictors match the search criteria.", style = "color: #999; padding: 20px;"))
    }

    # Get max correlation threshold
    max_corr <- if (!is.null(input$predictorMaxCorr)) input$predictorMaxCorr else global$predictor_max_corr

    # Create table rows using helper function
    table_rows <- lapply(1:nrow(stats_table), function(i) {
      create_predictor_table_row(i, stats_table, max_corr, global$excluded_predictors)
    })

    # Get list of predictor IDs for the select/deselect all functionality
    predictor_ids <- paste0("exclude_", stats_table$Predictor)
    predictor_ids_js <- paste0("['", paste(predictor_ids, collapse = "','"), "']")

    tags$div(
      style = "max-height: 500px; overflow-y: auto;",
      tags$table(
        class = "table table-striped table-hover",
        tags$thead(
          tags$tr(
            tags$th("Predictor"),
            tags$th("Non-NA Count"),
            tags$th("Correlation"),
            tags$th(
              tags$div(
                "Exclude",
                checkboxInput("selectAllPredictors", label = "All", value = FALSE)
              ),
              tags$script(HTML(sprintf("
                $('#selectAllPredictors').on('change', function() {
                  var checked = $(this).prop('checked');
                  var ids = %s;
                  ids.forEach(function(id) {
                    $('#' + id).prop('checked', checked).trigger('change');
                  });
                });
              ", predictor_ids_js)))
            )
          )
        ),
        tags$tbody(table_rows)
      )
    )
  })

  # Update table when correlation filter changes
  observeEvent(input$predictorMaxCorr, {
    req(!is.null(input$predictorMaxCorr))

    # Validate and convert to numeric
    max_corr_val <- as.numeric(input$predictorMaxCorr)
    req(!is.na(max_corr_val) && max_corr_val > 0 && max_corr_val <= 1)

    global$predictor_max_corr <- max_corr_val

    # Keep the full table - don't recalculate, just let the UI filter it
    # The renderUI will auto-check boxes for predictors exceeding threshold
  })

  # Update table when max predictors changes
  observeEvent(input$predictorMaxPredictors, {
    req(!is.null(input$predictorMaxPredictors))
    req(nrow(global$rawdata) > 0)

    # Validate and convert to numeric
    max_preds_val <- as.numeric(input$predictorMaxPredictors)
    req(!is.na(max_preds_val) && max_preds_val > 0)

    global$predictor_max_predictors <- max_preds_val

    # Recalculate predictors with new max_predictors limit
    all_predictors <- select_tree_predictors(global$rawdata, input$profileMetric, exclude = character(0), max_predictors = max_preds_val, max_correlation = 1.0)
    stats_table <- get_predictor_stats_table(global$rawdata, input$profileMetric, all_predictors)
    global$full_stats_table <- stats_table
  })

  # Apply predictor exclusion when user clicks Apply
  observeEvent(input$applyPredictorExclusion, {
    req(nrow(global$rawdata) > 0)
    max_corr <- get_max_correlation(global, input)
    max_preds <- get_max_predictors(global, input)
    valid_predictors <- select_tree_predictors(global$rawdata, input$profileMetric, exclude = character(0), max_predictors = max_preds, max_correlation = max_corr)

    # Collect all checked predictors
    excluded <- c()
    for (pred in valid_predictors) {
      checkbox_id <- paste0("exclude_", pred)
      if (!is.null(input[[checkbox_id]]) && input[[checkbox_id]]) {
        excluded <- c(excluded, pred)
      }
    }

    global$excluded_predictors <- excluded
    # Save the search text for next time dialog opens
    if (!is.null(input$predictorSearch)) {
      global$predictor_search <- input$predictorSearch
    }
    removeModal()
  })

  # Upon loading profile data or changing metric, update slider input range and predictor choices
  dataListeners = reactive({list(global$rawdata, input$profileMetric)})
  observeEvent(dataListeners(), {
    req(nrow(global$rawdata) > 0)
    nonunique <- global$rawdata %>%
      select(where(~ length(unique(.x)) > 1))
    updateSelectizeInput(session, inputId='profileFilterMetric', choices=c('None', colnames(nonunique)), server = TRUE)

    # Initialize max correlation threshold if not set
    if (is.null(global$predictor_max_corr)) {
      global$predictor_max_corr <- MAX_CORRELATION
    }
    if (is.null(global$predictor_max_predictors)) {
      global$predictor_max_predictors <- MAX_PREDICTORS
    }

    # Initialize excluded predictors with auto-exclusion logic (isolated to prevent cascade)
    isolate({
      initialize_excluded_predictors(global, global$rawdata, input$profileMetric)
    })
  })

  # Whenever a new filter metric is selected, updated filtering choices
  observeEvent(input$profileFilterMetric, {
    req(nrow(global$rawdata) > 0)
    output$profileFilterUI <- renderUI(
      metric_value_ui(global$rawdata[[input$profileFilterMetric]], "profileFilterValue", animate=F)
    )
  })


  # Finally, use filters to update perf data when everything is ready
  # Priority=10 ensures this completes before render functions (priority=0)
  observe(priority = 10, {
    req(nrow(global$rawdata) > 0)
    req(!is.null(input$profileMetric) && input$profileMetric != "")
    if (req(input$profileFilterMetric) != "None") {
      req(input$profileFilterValue)
    }

    filtered_indices <- filter_var(global$rawdata[[input$profileFilterMetric]], input$profileFilterValue)
    temp_filtered <- global$rawdata[filtered_indices,]

    # Remove columns with no variance (<=1 unique non-NA values) - optimized for large datasets
    if (ncol(temp_filtered) > 1000) {
      # Use data.table for faster variance checking on large datasets
      dt <- as.data.table(temp_filtered)
      variance_check <- dt[, lapply(.SD, function(x) length(unique(na.omit(x))) > 1)]
      variance_check <- as.logical(variance_check[1,])
    } else {
      variance_check <- sapply(temp_filtered, function(x) length(unique(na.omit(x))) > 1)
    }
    global$filtered <- temp_filtered[, variance_check, drop = FALSE]

    # Check selected metric still exists and has variance
    if (input$profileMetric %in% colnames(global$filtered)) {
      global$cutoff <- suggest_cutoff(global$filtered[[input$profileMetric]])
    }
  })



  # Plot the output of the profiling run, with cutoff point
  output$profilerOutput <- renderPlot({
    req(nrow(global$filtered) > 0)
    req(!is.null(input$profileMetric) && input$profileMetric != "")
    req(input$profileMetric %in% colnames(global$filtered))
    req(!is.null(global$cutoff) && !is.na(global$cutoff))

    perf <- global$filtered %>% pull(input$profileMetric)
    create_distribution_plot(perf, input$profileMetric, global$cutoff) +
      theme(text=element_text(size=20))
  })

  # Display distribution characteristics below the plot
  output$profileCharacteristics <- renderText({
    req(nrow(global$filtered) > 0)
    req(!is.null(input$profileMetric) && input$profileMetric != "")
    req(input$profileMetric %in% colnames(global$filtered))

    perf <- global$filtered %>% pull(input$profileMetric)
    characterize_distribution(perf)
  })

  # Recompute cutoff point by search for the lowest-AIC cutoff in a range.
  observeEvent(input$searchForCutoff, {
    req(nrow(global$filtered) > 1)

    excluded <- get_excluded_predictors(global)
    max_corr <- get_max_correlation(global, input)
    max_preds <- get_max_predictors(global, input)

    withProgress(message = 'Searching for optimal cutoff...', value = 0, {
      cutoff <- search_for_cutoff(global$filtered, input$profileMetric, excluded, max_corr, max_preds)
      global$cutoff <- cutoff
    })
  })


  # Change classifier cutoff point upon click on graph
  observeEvent(input$profilerClick, {
    global$cutoff <- input$profilerClick$x
  })


  # Plot decision tree of performance classification based on cutoff point
  output$profileTreeOutput <- renderVisNetwork({
    req(nrow(global$filtered) > 0)
    req(!is.null(input$profileMetric) && input$profileMetric != "")
    req(input$profileMetric %in% colnames(global$filtered))
    req(!is.null(global$cutoff) && !is.na(global$cutoff))

    excluded <- get_excluded_predictors(global)
    max_corr <- get_max_correlation(global, input)
    max_preds <- get_max_predictors(global, input)
    tr <- compute_tree(global$filtered, input$profileMetric, global$cutoff, excluded, max_corr, max_preds)
    if (!is.null(tr)) {
      plot_tree(tr)
    }
  })

  observeEvent(input$currentNode, {
    updateSelectInput(inputId='mitigationSelector', choices=factors[[input$currentNode$label]]$mitigations)
    visNetworkProxy("profileTreeOutput") %>% visNodes(title="foo", color="red")
  })

  # Dynamic file button that shows filename when loaded
  output$profileFileButton <- renderUI({
    if (!is.null(global$loaded_filename)) {
      filename <- basename(global$loaded_filename)
      # Truncate filename to fit in button (max ~20 chars to prevent column overflow)
      if (nchar(filename) > 20) {
        button_label <- paste0(substr(filename, 1, 17), "...")
      } else {
        button_label <- filename
      }
      tooltip_text <- paste0("Experiment loaded: ", global$loaded_filename)
      with_tooltip(
        shinyFilesButton('profileFile',
                        label=button_label,
                        title=tooltip_text,
                        multiple=FALSE,
                        icon=icon("file")),
        tooltip_text
      )
    } else {
      with_tooltip(
        shinyFilesButton('profileFile',
                        label="Load metadata",
                        title="Select metadata of experiment to profile",
                        multiple=FALSE,
                        icon=icon("folder-open")),
        "Select metadata of experiment to profile"
      )
    }
  })


  # Control visibility of elements only after data is loaded
  output$profileDataLoaded <- reactive({ !is.null(global$rawdata) })
  outputOptions(output, "profileDataLoaded", suspendWhenHidden=FALSE)
  output$mitigationDataLoaded <- reactive({ !is.null(global$mitdata) })
  outputOptions(output, "mitigationDataLoaded", suspendWhenHidden=FALSE)

  # Plot a scatter plot of performance vs. selected factor
  output$factorVsPerf <- renderPlot({
    req(nrow(global$filtered) > 0)
    req(global$cutoff)
    req(input$currentNode)

    plot_factor_perf(global$filtered, global$cutoff, input$profileMetric, input$currentNode$label)
  })


  # Explain the selected factor
  output$factorDescription <- renderUI({
    req(input$currentNode)

    # Don't require filtered data for showing the message
    if (is.null(global$filtered) || nrow(global$filtered) == 0) {
      return(tags$p("No data available", style="color: #999; padding: 20px;"))
    }

    label <- input$currentNode$label
    if (label %in% names(factors)) {
      updateTabsetPanel(inputId="factorTab")
      render_factor_data(label)
    }
    else {
      tags$p(paste("No information available for factor", label, "-- please choose another factor"),
             style="color: #999; padding: 20px;")
    }
  })


  # Run a Llama query to explain factor
  observeEvent(input$askLlamaAboutFactor, {
      query <- paste("Explain", gsub("_", " ", input$currentNode$label), "and how to mitigate it")

      showModal(modalDialog(
        title = "Query Llama on performance factor",
        easyClose = TRUE,
        textInput("factorQuery", "Llama query", value=query),
        actionButton("submitFactorQuery", "Submit", class="btn-success", icon=icon("circle-play")),
        hr(),
        htmlOutput("llamaFactorOutput"),
      ))
  })

  observeEvent(input$submitFactorQuery, {
    ascii2html <- function(txt) {
      html <- HTML(sprintf("%s", gsub("\n", "<br/>",
                           as.character(sgr_to_html(txt)))))
      iconv(html, to="ASCII", sub="")
    }

    cmd <- "/usr/local/bin/ollama"
    args <- c("run", "llama3", input$factorQuery)
    proc <- process$new(cmd, args, stdout="|", stderr="2>&1")
    out <- ""

    while (proc$is_alive()) {
      Sys.sleep(1)
      lines <- proc$read_output_lines()
      if (length(lines) > 1) {
        out <- paste0(out, lines)
        print(lines)
      }
    }
    out <- paste0(out, proc$read_output_lines())
    output$llamaFactorOutput <- renderUI(ascii2html(out))
  })


  # Inspect code hotspots related to the selected factor
  observeEvent(input$codeHotspots, {
    showModal(modalDialog(
      title = paste("Code areas with worst", input$currentNode$label),
      easyClose = TRUE,
      footer = NULL,
      verbatimTextOutput("worstCode"),
      p("You can ask Llama to suggest ways to mitigate this part of the code"),
      hr(),
      actionButton("askLlamaAboutCode", label="Ask Llama", class="btn-info", icon=icon("comments")),
      modalButton("Dismiss"),
    ))

    output$worstCode <- renderText({ "This feature not yet implemented" })
  })


  # Update output for selected mitigation:
  output$mitigationDescription <- renderUI({
    m <- input$mitigationSelector
    if (m %in% names(mitigations)) {
      descr <- mitigations[[m]]$description
    } else {
      descr <- paste("No description available for", m)
    }
    links <- link_list(mitigations[[m]]$references)
    HTML(paste(descr, links, sep='<br/>'))
  })


  # Produce a performance prediction for a selected mitigation:
  observeEvent(input$predictMitigation, {
    showModal(modalDialog(title="", "This functionality not implemented yet"))
  })

  # Rerun benchmark with selected mitigation:
  observeEvent(input$tryMitigation, {
    req(input$mitigationSelector, length(get_mdfn()) > 0, nzchar(get_mdfn()))

    # Store for use in other handlers
    global$mitigation_mdfn <- get_mdfn()

    # First, check if we already have the data:
    mitfn_path <- gsub(".md", sprintf("-%s.csv", input$mitigationSelector), get_mdfn())
    if (file.exists(mitfn_path)) {
      showModal(modalDialog(title="Mitigation data exists",
        "A file with mitigation data exists. Do you want to use it or rerun it?",
        footer = tagList(
          modalButton("Cancel"),
          actionButton("useMitigationData", "Use data", class="btn-primary", icon=icon("recycle")),
          actionButton("runMitigation", "Rerun it", class="btn-success", icon=icon("play")),
        )
      ))
    }
    else {

      # No data, no problem. Let's rerun SHARP with mitigation to get it:
      m <- input$mitigationSelector
      msg <- ifelse (m %in% names(mitigations$backend_options),
               "Are you sure you want to rerun benchmark? this could take a while",
                paste0("This mitigation cannot be automated. ",
                       "To run it manually, back up your current setup and application and apply the mitigation yourself. ",
                       "(If recompiling the application, make sure to use the same path and binary name as before.) ",
                       "When ready, click 'Run it' to get the new data. This could take a while. ",
                       "Remember to restore system state to normal after the run if needed.")
      )

      showModal(modalDialog(title="Attempt mitigation on program", msg,
                  footer = tagList(
                    modalButton("Cancel"),
                    actionButton("runMitigation", "Run it!", class="btn-success", icon=icon("play")),
                )))
    }
  })

  # Launch SHARP to rerun experiment with profiling data:
  observeEvent(input$runMitigation, {
    m <- input$mitigationSelector
    task <- paste0(tools::file_path_sans_ext(basename(get_mitigation_mdfn())), "-", m)
    reps <- as.numeric(first(na.omit(str_extract(markdown(), '"max": ([:digit:]+)', group=1))))
    experiment <- first(na.omit(str_extract(markdown(), '"experiment": "(.*)"', group=1)))
    print(paste("Running profiler for", task, "experiment:", experiment, "with repetitions:", reps))
    args <- c("-v", "--repro", unname(get_mitigation_mdfn()), "-t", task)
    if (m %in% names(mitigations$backend_options)) {
      args <- c(args, "-f",  "mitigations.yaml", "-b", m)
    }

    removeModal()
    run_sharp(args, reps, experiment)
    mitfn_path <- gsub(".md", sprintf("-%s.csv", m), get_mitigation_mdfn())
    global$mitdata <- fast_read_csv(mitfn_path)
  })


  # Load mitigation data from existing, previous file:
  observeEvent(input$useMitigationData, {
    m <- input$mitigationSelector
    mitfn_path <- gsub(".md", sprintf("-%s.csv", m), get_mitigation_mdfn())
    global$mitdata <- fast_read_csv(mitfn_path)
    sel <- ifelse("inner_time" %in% metric_names(global$mitdata), "inner_time", "outer_time")
    updateSelectInput(inputId='mitigationCompareMetric', choices=metric_names(global$mitdata), selected=sel)
    removeModal()
  })


  # Once mitigation data is loaded, compare it to original data:
  output$compareMitigationDensity <- renderPlot({
    req(nrow(dataset()) > 0 & nrow(global$mitdata) > 0)
    density_comparison(dataset(), global$mitdata, input$mitigationCompareMetric)
  })

  output$compareMitigationTable <- renderTable(digits=4, striped=TRUE, colnames=TRUE, {
    req(nrow(dataset()) > 0 & nrow(global$mitdata) > 0)
    comparison_table(dataset(), global$mitdata, input$mitigationCompareMetric)
  })
}
