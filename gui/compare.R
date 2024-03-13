# UI for Compare tab
# © Copyright 2022--2024 Hewlett Packard Enterprise Development LP

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
ecdf_comparison <- function(baseline, treatment, metric)
{
  perf1 <- baseline() %>% pull(metric)
  perf2 <- treatment() %>% pull(metric)
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
density_comparison <- function(baseline, treatment, metric)
{
  perf1 <- baseline() %>% pull(metric)
  perf2 <- treatment() %>% pull(metric)
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
comparison_table <- function(baseline, treatment, metric)
{
  perf1 <- baseline() %>% pull(metric)
  perf2 <- treatment() %>% pull(metric)
  stats1 <- compute_summary(perf1, 10)
  stats2 <- compute_summary(perf2, 10)
  data.frame(Statistic=names(stats1), Baseline=stats1, Treatment=stats2)
}

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
    ret <- paste0(ret, "}\\\\", report_test(c_test))
  }

  withMathJax(paste0(ret, "$$"))
}

#####################
render_compare <- function(input, output) {
  digits <- 4

  shinyFileChoose(input, 'compareBaseline', roots=c(logdir='../runlogs'), filetypes=c('csv'))
  shinyFileChoose(input, 'compareTreatment', roots=c(logdir='../runlogs'), filetypes=c('csv'))

  bfn <- reactive(parseFilePaths(roots=c(logdir='../runlogs'), input$compareBaseline)$datapath)
  tfn <- reactive(parseFilePaths(roots=c(logdir='../runlogs'), input$compareTreatment)$datapath)
  baseline <- reactive(read_csv(bfn()))
  treatment <- reactive(read_csv(tfn()))

  output$baselineName <- renderText(bfn())
  output$treatmentName <- renderText(tfn())


  observeEvent(input$compareTreatment, {
    req(nrow(baseline()) > 0 & nrow(treatment()) > 0)
     updateSelectInput(inputId='compareMetric',
                       choices=intersect(metric_names(baseline()), metric_names(treatment())))
  })

  output$compareDensityPlot <- renderPlot({
    req(nrow(baseline()) > 0 & nrow(treatment()) > 0)
    density_comparison(baseline, treatment, input$compareMetric)
  })

  output$compareCDFPlot <- renderPlot({
    req(nrow(baseline()) > 0 & nrow(treatment()) > 0)
    ecdf_comparison(baseline, treatment, input$compareMetric)
  })

  output$compareTable <- renderTable(digits=digits, striped=TRUE, colnames=TRUE, {
    req(nrow(baseline()) > 0 & nrow(treatment()) > 0)
    comparison_table(baseline, treatment, input$compareMetric)
  })

  output$compareNarrative <- renderUI({
    req(nrow(baseline()) > 0 & nrow(treatment()) > 0)
    narrative_comparison(baseline(), treatment(), input$compareMetric)
  })
}
