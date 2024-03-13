# UI for Explore tab
# © Copyright 2022--2024 Hewlett Packard Enterprise Development LP

explorePanel <- tabPanel("Explore",
  fluidRow(
    column(2, p("Select experiment to explore")),
    column(2,
      shinyFilesButton('exploreFile', label="Load dataset", title="Select log file to explore", multiple=FALSE),
    ),
    column(4,
      tags$div(id="inline",
        selectInput('exploreMetric', "Metric to visualize:\U02001", choices=c("outer_time")))
    ),
  ),

  hr(),

  fluidRow(
    column(7, plotOutput('explorePlot'), click='exploreClick'),
    column(5,
      h4("Summary statistics"),
      tableOutput('exploreTable')
    ),
  ),
)


#####################
render_explore <- function(input, output) {
  digits <- 4
  shinyFileChoose(input, 'exploreFile', roots=c(logdir='../runlogs'), filetypes=c('csv'))
  cfn <- reactive(parseFilePaths(roots=c(logdir='../runlogs'), input$exploreFile)$datapath)
  dataset <- reactive(read_csv(cfn()))

  observeEvent(input$exploreFile, {
     req(nrow(dataset()) > 0)
     updateSelectInput(inputId='exploreMetric', choices=metric_names(dataset()))
  })

  output$exploreTable <- renderTable(digits=digits, striped=TRUE, colnames=FALSE, {
    req(nrow(dataset()) > 0)
    print(metric_names(dataset()))
    perf <- dataset() %>% pull(input$exploreMetric)
    stats <- compute_summary(perf, digits)
    data.frame(stat=names(stats), values=stats)
  })

  output$explorePlot <- renderPlot({
    req(nrow(dataset()) > 0)
    perf <- dataset() %>% pull(input$exploreMetric)
    create_distribution_plot(perf, input$exploreMetric)
  })
}
