# UI for Compare tab
# © Copyright 2022--2025 Hewlett Packard Enterprise Development LP

base_color="darkblue"
treat_color="orange"

comparePanel <- tabPanel("Compare",
  withMathJax(),
  fluidRow(

    column(2,
      shinyFilesButton('compareBaseline', label="Load baseline", title="Select baseline log file", multiple=FALSE),
    ),
    column(3,
      textOutput('baselineName'),
    ),

    column(2,
      shinyFilesButton('compareTreatment', label="Load treatment", title="Select treatment log file", multiple=FALSE),
    ),
    column(3,
      textOutput('treatmentName'),
    ),

    column(2,
      tags$div(id="inline",
        selectInput('compareMetric', "Metric to visualize:\U02001", choices=c("outer_time")))
    ),
  ),

  hr(),

  fluidRow(
    column(3, plotOutput('compareDensityPlot')),
    column(3, plotOutput('compareCDFPlot')),
    column(2, tableOutput('compareTable')),
    column(4, uiOutput('compareNarrative')),
  ),
)


#####################
narrative_comparison <- function(baseline, treatment, metric)
{
  perf1 <- baseline %>% pull(metric)
  perf2 <- treatment %>% pull(metric)
  ret <- "$$"
  p_thresh <- 0.01

  # Compare means:
  t_test <- t.test(perf2, perf1)
  sig <- ifelse(t_test$p.value < p_thresh, "significantly", "")
  higher <- ifelse(t_test$p.value >= 0.3, "about the same as",
                   ifelse(mean(perf2) > mean(perf1), "higher than", "lower than"))
  ret <- paste(ret,
    "\\text{Treatment mean is", sig, higher, "baseline}\\\\",
    report_test(t_test),
    "\\\\"
  )

  # Compare medians:
  w_test <- wilcox.test(perf2, perf1)
  sig <- ifelse(w_test$p.value < p_thresh, "significantly", "")
  higher <- ifelse(w_test$p.value >= 0.3, "about the same as",
                   ifelse(median(perf2) > median(perf1), "higher than", "lower than"))
  ret <- paste(ret,
    "\\text{Treatment median is", sig, higher, "baseline}\\\\",
    report_test(w_test),
    "\\\\"
  )

  # Evaluate Kolmogorov-Smirnov distance
  ks_test <- ks.test(perf2, perf1)
  ret <- paste(ret, "\\text{Distributions appear to be")
  if (ks_test$statistic <= 0.1) {
    ret <- paste(ret, "very")
  }
  if (ks_test$statistic <= 0.3) {
    ret <- paste(ret, "similar}\\\\")
  } else {
    ret <- paste(ret, "dissimilar}\\\\")
  }
  ret <- paste0(ret, report_test(ks_test), "\\\\")

  # Correlate samples of same length:
  if (length(perf1) == length(perf2)) {
    c_test <- cor.test(perf2, perf1)
    ret <- paste(ret, "\\text{Samples appear to be")
    if (abs(c_test$estimate) <= 0.3) ret <- paste(ret, "uncorrelated")
    else {
      ret <- paste(ret, ifelse(abs(c_test$estimate) > 0.7, "strongly", "somewhat"))
      ret <- paste(ret, ifelse(c_test$estimate > 0, "correlated", "anti-correlated"))
    }
    ret <- paste(ret, "}\\\\", report_test(c_test), "\\\\")
  }

  # Compute fused mean performance with Kalman Filtering
  sumv <- var(perf1) + var(perf2)
  fused <- (var(perf2)*mean(perf1) + var(perf1)*mean(perf2))/sumv
  ret <- paste(ret, "\\text{Mean performance fused with Kalman Filter}\\\\")
  ret <- paste0(ret, "\\mu{}=", round(fused, 4))
#  ret <- paste0(ret, "}\\\\")

  withMathJax(paste0(ret, "$$"))
}

#####################
render_compare <- function(input, output, session) {
  digits <- 4
  data <- reactiveValues()

  shinyFileChoose(input, 'compareBaseline', roots=c(logdir='../runlogs'), filetypes=c('csv'))
  shinyFileChoose(input, 'compareTreatment', roots=c(logdir='../runlogs'), filetypes=c('csv'))

  bfn <- reactive(parseFilePaths(roots=c(logdir='../runlogs'), input$compareBaseline)$datapath)
  tfn <- reactive(parseFilePaths(roots=c(logdir='../runlogs'), input$compareTreatment)$datapath)

  # Helpers to get CSV filenames - use stored values if available, otherwise reactive
  get_bfn <- make_file_getter(bfn, data, "bfn")
  get_tfn <- make_file_getter(tfn, data, "tfn")

  baseline <- reactive({
    req(length(get_bfn()) > 0)
    data$bfn <- bfn()  # Store when accessed
    read_csv(get_bfn())
  })
  treatment <- reactive({
    req(length(get_tfn()) > 0)
    data$tfn <- tfn()  # Store when accessed
    read_csv(get_tfn())
  })

  output$baselineName <- renderText(get_bfn())
  output$treatmentName <- renderText(get_tfn())


  observeEvent(input$compareTreatment, {
    req(nrow(baseline()) > 0 & nrow(treatment()) > 0)
     mnames <- intersect(metric_names(baseline()), metric_names(treatment()))
     sel <- ifelse("inner_time" %in% mnames, "inner_time", "outer_time")
     updateSelectInput(inputId='compareMetric', choices=mnames, selected=sel)
  })

  output$compareDensityPlot <- renderPlot({
    req(nrow(baseline()) > 0 & nrow(treatment()) > 0)
    density_comparison(baseline(), treatment(), input$compareMetric)
  })

  output$compareCDFPlot <- renderPlot({
    req(nrow(baseline()) > 0 & nrow(treatment()) > 0)
    ecdf_comparison(baseline(), treatment(), input$compareMetric)
  })

  output$compareTable <- renderTable(digits=digits, striped=TRUE, colnames=TRUE, {
    req(nrow(baseline()) > 0 & nrow(treatment()) > 0)
    comparison_table(baseline(), treatment(), input$compareMetric)
  })

  output$compareNarrative <- renderUI({
    req(nrow(baseline()) > 0 & nrow(treatment()) > 0)
    narrative_comparison(baseline(), treatment(), input$compareMetric)
  })
}
