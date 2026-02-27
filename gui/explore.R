# UI for Explore tab
# © Copyright 2022--2025 Hewlett Packard Enterprise Development LP

explorePanel <- tabPanel("Explore",
  fluidRow(
    column(2, p("Select experiment to explore")),
    column(2,
      uiOutput('exploreFileButton'),
    ),
    column(2,
      selectInput('exploreMetric', "Metric to visualize", choices=c("outer_time"))
    ),
    column(2,
      selectInput('compareMetrics',
                  "Metrics to compare",
                  choices=c("repeat", "outer_time"),
                  multiple=TRUE,
                  selectize=TRUE,
                 ),
    ),
    column(2, selectInput('exploreFilterMetric', "Metric to filter", choices=c(NULL))),
    column(2, uiOutput('exploreFilterUI')),
  ),

  hr(),

  fluidRow(
    column(7,
      plotOutput('explorePlot', click='exploreClick'),
      textOutput('exploreCharacteristics')
    ),
    column(5,
      h4("Summary statistics"),
      tableOutput('exploreTable')
    ),
  ),

  hr(),

  fluidRow(
    h4("Pairwise comparisons"),
    plotOutput('corPlot'),
  ),
)


#####################
render_explore <- function(input, output, session) {
  digits <- 4
  shinyFileChoose(input, 'exploreFile', roots=c(logdir='../runlogs'), filetypes=c('csv'))
  cfn <- reactive(parseFilePaths(roots=c(logdir='../runlogs'), input$exploreFile)$datapath)
  data <- reactiveValues(raw=NULL, selected=NULL, dataset=NULL, perf=NULL)

  # Helper to get CSV filename - uses stored value if available, otherwise reactive
  get_cfn <- make_file_getter(cfn, data, "cfn")

  # Dynamic file button that shows filename when loaded
  output$exploreFileButton <- renderUI({
    # Render initial button
    if (is.null(data$raw)) {
      shinyFilesButton('exploreFile', label="Load dataset", title="Select log file to explore", multiple=FALSE, icon=icon('file-lines'))
    } else {
      # Show filename after data is loaded
      file_path <- get_cfn()
      fname <- basename(file_path)
      with_tooltip(
        actionButton('exploreFileLoaded', label=fname, icon=icon('file-lines'), class='btn-primary'),
        file_path
      )
    }
  })

  ### Read raw data from file whenever Load dataset is clicked:
  observeEvent(input$exploreFile, {
    req(length(cfn()) > 0)
    # Store the filename for later use
    data$cfn <- cfn()
    freezeReactiveValue(input, "exploreMetric")

    raw_data <- read_csv(get_cfn()) %>%
      mutate(across(where(is.character), factor))
    mnames <- metric_names(raw_data)
    nonunique <- raw_data %>%
      select(where(~ length(unique(.x)) > 1))

    view_metric <- ifelse("inner_time" %in% mnames, "inner_time", "outer_time")

    updateSelectInput(inputId='exploreMetric', choices=mnames, selected=view_metric)
    updateSelectInput(inputId='compareMetrics', choices=mnames)
    updateSelectInput(inputId='exploreFilterMetric', choices=c('None', colnames(nonunique)))
    data$raw <- raw_data
  })

  ### Change dataset whenever filter metric changes:
  observe({
    req(data$raw)
    if (req(input$exploreFilterMetric) != "None") {
      req(input$exploreFilterValue)
    }
    filtered <- filter_var(data$raw[[input$exploreFilterMetric]], input$exploreFilterValue)
    data$dataset <- data$raw[filtered,]
    data$perf <- data$dataset %>% pull(input$exploreMetric)
  })

  output$exploreFilterUI <- renderUI(
    metric_value_ui(data$raw[[input$exploreFilterMetric]], "exploreFilterValue")
  )

  #########
  output$exploreTable <- renderTable(digits=digits, striped=TRUE, colnames=FALSE, {
    req(data$perf)
    stats <- compute_summary(data$perf, digits)
    data.frame(stat=names(stats), values=stats)
  })

  #########
  output$exploreCharacteristics <- renderText({
    req(data$perf)
    data$perf %>% characterize_distribution()
  })

  #########
  output$explorePlot <- renderPlot({
    req(data$perf)
    create_distribution_plot(data$perf, input$exploreMetric)
  })

  #########
  output$corPlot <- renderPlot({
    req(data$dataset)
    req(length(input$compareMetrics) > 0)

    data$dataset %>%
      dplyr::select(input$compareMetrics) %>%
      ggpairs() + theme(strip.text.x=element_text(size=14),
                        strip.text.y=element_text(size=14))
  })
}
