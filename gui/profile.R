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
not_predictors <- c("repeat", "inner_time", "outer_time", "perf_time")

######################################
optimizePanel <- tabPanel('Profile',
  sidebarLayout(
    sidebarPanel(
      fluidRow(
        column(7, p("Select experiment to profile")),
        column(3,
          shinyFilesButton('profileFile', label="Load metadata", title="Select metadata of experiment to profile", multiple=FALSE, icon=icon("table")),
        ),
      ),

      conditionalPanel(condition="output.profileDataLoaded",
        fluidRow(
          column(6, selectInput('profileMetric', "Outcome metric", choices=c("perf_time"))),
          column(6, selectizeInput('excludePredictors', "Predictors to exclude", multiple=T, choices=c("repeat"))),
        ),
        fluidRow(
          column(6, selectInput('profileFilterMetric', "Metric to limit to", choices=c(NULL))),
          column(6, uiOutput('profileFilterUI')),
        ),
        p("Click on density plot to change classifier cutoff"),
        p("Click on a tree node to inspect performance factor"),
        fluidRow(
          column(8,
            p('Click here for an exhustive search for a cutoff point to minimize AIC'),
          ),
          column(4,
            actionButton("searchForCutoff", label="Search", class="btn-secondary", icon=icon("magnifying-glass")),
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
# Selects the best predictors for building a decision tree.
select_tree_predictors <- function(data, metric, exclude, max_predictors = MAX_PREDICTORS) {
  # Exclude columns with 1 or fewer unique non-NA values, user-defined exclusions, the metric, and "cat"
  constant_cols <- names(data)[sapply(data, function(x) length(unique(na.omit(x)))) <= 1]
  all_exclude <- unique(c(exclude, constant_cols, metric, "cat"))

  potential_predictors <- setdiff(names(data), all_exclude)

  # Separate numeric and non-numeric predictors
  is_numeric_col <- sapply(data[potential_predictors], is.numeric)
  numeric_predictors <- potential_predictors[is_numeric_col]
  non_numeric_predictors <- potential_predictors[!is_numeric_col]

  # If we have many numeric predictors, select the top N most correlated ones
  if (length(numeric_predictors) > max_predictors) {
    correlations <- sapply(data[numeric_predictors], function(x) {
      # Check for variance in this specific column and metric
      x_clean <- na.omit(x)
      metric_clean <- na.omit(data[[metric]])

      if (length(x_clean) <= 1 || length(unique(x_clean)) <= 1 ||
          length(metric_clean) <= 1 || length(unique(metric_clean)) <= 1) {
        return(NA)
      }

      # Additional check for zero standard deviation to prevent warnings
      tryCatch({
        if (sd(x_clean) == 0 || sd(metric_clean) == 0) {
          return(NA)
        }
      }, error = function(e) {
        return(NA)  # If sd() fails for any reason
      })

      # Calculate correlation only if both have variance
      if (is.numeric(x) && is.numeric(data[[metric]])) {
        # Suppress warnings about zero standard deviation
        return(suppressWarnings(cor(x, data[[metric]], use = "pairwise.complete.obs")))
      } else {
        return(NA)
      }
    })

    # Filter out NA correlations and get absolute values
    abs_correlations <- abs(correlations[!is.na(correlations)])

    # Filter out perfect correlations (likely duplicates of the outcome metric)
    filtered_correlations <- abs_correlations[abs_correlations < 0.999]

    # Fallback if all correlations are perfect
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
compute_tree <- function(data, metric, cutoff, exclude) {
  # 1. Prepare data and perform initial checks
  metric_values <- data[[metric]]
  comparison_result <- metric_values > cutoff
  data$cat <- ifelse(comparison_result, "RIGHT", "LEFT")
  data$cat <- as.factor(data$cat)

  # Check if all data falls into one category
  right_count <- sum(data$cat == "RIGHT", na.rm = TRUE)
  left_count <- sum(data$cat == "LEFT", na.rm = TRUE)
  total_rows <- nrow(data)

  if (right_count == total_rows || left_count == total_rows) {
    return(NULL) # All data is in one category
  }

  if (!(metric %in% colnames(data))) {
    showModal(modalDialog(
      title = "Error: Missing Metric Column",
      paste("The metric column '", metric, "' is not present in the filtered data.", sep=""),
      easyClose = TRUE
    ))
    return(NULL)
  }

  # 2. Select the most relevant predictors
  final_predictors <- select_tree_predictors(data, metric, exclude)

  if (length(final_predictors) == 0) {
    showModal(modalDialog(title = "Error", "No suitable predictors found to build a model."))
    return(NULL)
  }

  # 3. Build the formula and compute the tree
  formula_str <- build_tree_formula(final_predictors)

  rpart(as.formula(formula_str), data=data)
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
search_for_cutoff <- function(profdata, metric, exclude)
{
  min_aic <- 1e10
  perf <- profdata[[metric]]
  max_points <- min(MAX_SEARCH, length(perf))
  best_pt <- perf[1]

  for (pt in seq(min(perf), max(perf), length.out=max_points)) {
    tr <- compute_tree(profdata, metric, pt, exclude)
    if (!is.null(tr) && nrow(tr$cptable) > 1) {  # Only search for valid trees with more than one node
      aic <- summarize_tree(tr)$aic
      if (aic < min_aic) {
        min_aic <- aic
        best_pt <- pt
      }
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
render_optimize <- function(input, output) {
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
      # Use fast CSV reader
      global$rawdata <- fast_read_csv(proffn())
      incProgress(0.7, detail = "Processing columns")
      mnames <- colnames(global$rawdata)
    # Only allow metrics with >1 unique non-NA value
    valid_metrics <- mnames[sapply(global$rawdata[mnames], function(x) length(unique(na.omit(x))) > 1)]
    sel <- ifelse("inner_time" %in% valid_metrics, "inner_time", "perf_time")
    updateSelectInput(inputId='profileMetric', choices=valid_metrics, selected=sel)
    valid_predictors <- select_tree_predictors(global$rawdata, sel, exclude = character(0))
    updateSelectInput(inputId='excludePredictors', choices=valid_predictors, selected=intersect(not_predictors, valid_predictors))
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
      global$rawdata <- fast_read_csv(proffn())
      incProgress(0.9, detail = "Processing columns")
      mnames <- colnames(global$rawdata)
    # Only allow metrics with >1 unique non-NA value
    valid_metrics <- mnames[sapply(global$rawdata[mnames], function(x) length(unique(na.omit(x))) > 1)]
    sel <- ifelse("perf_time" %in% valid_metrics, "perf_time", valid_metrics[1])
    updateSelectInput(inputId='profileMetric', choices=valid_metrics, selected=sel)
    valid_predictors <- select_tree_predictors(global$rawdata, sel, exclude = character(0))
    updateSelectInput(inputId='excludePredictors', choices=valid_predictors, selected=intersect(not_predictors, valid_predictors))
    })
  })


  # Upon loading profile data or changing metric, update slider input range and predictor choices
  dataListeners = reactive({list(global$rawdata, input$profileMetric)})
  observeEvent(dataListeners(), {
    req(nrow(global$rawdata) > 0)
    nonunique <- global$rawdata %>%
      select(where(~ length(unique(.x)) > 1))
    updateSelectInput(inputId='profileFilterMetric', choices=c('None', colnames(nonunique)))

    # Update predictor choices based on current metric
    if (!is.null(input$profileMetric) && input$profileMetric != "") {
      valid_predictors <- select_tree_predictors(global$rawdata, input$profileMetric, exclude = character(0))
      updateSelectInput(inputId='excludePredictors', choices=valid_predictors, selected=intersect(input$excludePredictors, valid_predictors))
    }
  })

  # Whenever a new filter metric is selected, updated filtering choices
  observeEvent(input$profileFilterMetric, {
    req(nrow(global$rawdata) > 0)
    output$profileFilterUI <- renderUI(
      metric_value_ui(global$rawdata[[input$profileFilterMetric]], "profileFilterValue", animate=F)
    )
  })


  # Finally, use filters to update perf data when everything is ready
  observe({
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
      theme(text=element_text(size=20), plot.title=element_text(size=12)) +
      ggtitle(characterize_distribution(perf))
  })

  # Recompute cutoff point by search for the lowest-AIC cutoff in a range.
  observeEvent(input$searchForCutoff, {
    req(nrow(global$filtered) > 1)

    cutoff <- search_for_cutoff(global$filtered, input$profileMetric, input$excludePredictors)
    global$cutoff <- cutoff
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

    tr <- compute_tree(global$filtered, input$profileMetric, global$cutoff, input$excludePredictors)
    if (!is.null(tr)) {
      plot_tree(tr)
    }
  })

  observeEvent(input$currentNode, {
    updateSelectInput(inputId='mitigationSelector', choices=factors[[input$currentNode$label]]$mitigations)
    visNetworkProxy("profileTreeOutput") %>% visNodes(title="foo", color="red")
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
    req(nrow(global$filtered) > 0)
    req(input$currentNode)

    label <- input$currentNode$label
    if (label %in% names(factors)) {
      updateTabsetPanel(inputId="factorTab")
      render_factor_data(label)
    }
    else {
      modalDialog(paste("No information available for factor", label, "-- please choose another factor"), easyClose=TRUE)
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
