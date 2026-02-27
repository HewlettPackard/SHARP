# UI for Predict tab
# © Copyright 2022--2025 Hewlett Packard Enterprise Development LP

# The machine characteristics used in measurement data (should be read from .md, then updated)

measured_hw <- c(cores=4, speed=3, nodes=16, memory=4)

base_color="darkblue"
model_color="orange"

######################
summaryOf <- function(df)
{
  paste0("Prediction accuracy: ",
    as.character(round(runif(1, 66.6, 99.9), 1)),
    "%\n",
    "
Highest-importance factors affecting
tail performance:

  1) page faults
  2) TLB misses

Highest-importance factors affecting
modality:

  1) context switches
  2) CPU speed
    ")
}

######################
predictPanel <- tabPanel("Predict",
  sidebarLayout(
    sidebarPanel(
      fluidRow(
        column(8, p("Select application log for predictions")),
        column(4,
          shinyFilesButton('predictFile', label="Load dataset", title="Select log file to predict for", multiple=FALSE),
        ),
      ),

      selectInput('predictMetric', "Metric to predict", choices=c("outer_time")),

      hr(),

      h4("Prediction model parameters"),

      fluidRow(
        column(6,
          sliderInput('predictCores', "Cores", min=1, max=32, value=measured_hw[['cores']]),
          sliderInput('predictSpeed', "CPU speed", min=1, max=6.0, value=measured_hw[['speed']], step=0.1),
        ),
        column(6,
          sliderInput('predictNodes', "Node count", min=1, max=128, value=measured_hw[['nodes']]),
          sliderInput('predictMemory', "RAM/core (GB)", min=2, max=128, value=measured_hw[['memory']]),
        ),
      ),
#      imageOutput("sharpLogo"),
    ),


    mainPanel(
      fluidRow(
        column(8, plotOutput('predictDistPlot')),
        column(4, verbatimTextOutput('predictSummary')),
      ),
    ),
  ),

  fluidRow(
    column(3, plotOutput('predictCoresPlot')),
    column(3, plotOutput('predictSpeedPlot')),
    column(3, plotOutput('predictNodesPlot')),
    column(3, plotOutput('predictMemoryPlot')),
  ),
)

###################################
# Try to fit a four-parameter Beta distribution to the log data.
# The parameters of the distributions become the simulated machine params, adjusted
best_fit <- function(x)
{
  fit <- pearsonFitML(x)
  fit
}

#####################
hw_from_input <- function(input)
{
  c(nodes=input$predictNodes,
    cores=input$predictCores,
    speed=input$predictSpeed,
    memory=input$predictMemory)
}

#####################
predict_from_hw <- function(hw_params, n=1000)
{
  model <- rnorm(n=n,
        sd=0.1 / sqrt(hw_params[['memory']]),
        mean=sqrt((measured_hw[['cores']] / hw_params[['cores']])) *
             measured_hw[['nodes']] * 0.3 / hw_params[['nodes']]
        ) +
        rexp(n=n, rate=7 * hw_params[['speed']])
  model
}

#####################
plot_prediction_density <- function(perf, input)
{
  metric <- input$predictMetric
  sample <- perf %>% pull(metric)
  prediction <- predict_from_hw(hw_params=hw_from_input(input))
  df <- data.frame(Dataset="Empirical", Performance=sample) %>%
    rbind(data.frame(Dataset="Prediction", Performance=prediction))
  df %>%
    ggplot(aes(x=Performance, fill=Dataset)) +
      geom_density(alpha=0.5) +
      ylab("Density") +
      xlim(min(sample), max(sample)) +
      scale_fill_manual(values=c(base_color, model_color)) +
      theme_light() +
      theme(text=element_text(size=20), legend.position="bottom")
}

#####################
plot_modeled_range <- function(df, xlab, ylab)
{
  df %>%
    ggplot(aes(x=as.factor(get(xlab)), y=Performance, color=Source)) +
      geom_pointrange(aes(ymin=Performance - 1.96*SD,
                          ymax=Performance + 1.96*SD),
                          position=position_dodge(width=-0.5),
                          shape=21,
                          fatten=20,
                          size=0.2) +
      scale_color_manual(values=c(base_color, model_color)) +
      xlab(xlab) +
      ylab(ylab) +
      theme_light() +
      theme(axis.text.x=element_text(angle=45, hjust=1),
            text=element_text(size=16),
            legend.position="bottom"
      )
}


#####################
plot_cores_prediction <- function(perf, input)
{
  hw <- hw_from_input(input)
  df <- data.frame(Cores=hw[['cores']],
                   Source="Empirical",
                   Performance=mean(perf),
                   SD=sd(perf))

  for (i in c(1, 2, 4, 8, 16, 32)) {
    hw[['cores']] = i
    prediction <- predict_from_hw(hw_params=hw)
    df <- rbind(df,
      data.frame(Cores=hw[['cores']],
                 Source="Model",
                 Performance=mean(prediction),
                 SD=sd(prediction)))
  }

  plot_modeled_range(df, "Cores", input$predictMetric)
}


#####################
plot_nodes_prediction <- function(perf, input)
{
  hw <- hw_from_input(input)
  df <- data.frame(Nodes=hw[['nodes']],
                   Source="Empirical",
                   Performance=mean(perf),
                   SD=sd(perf))

  for (i in c(1, 2, 4, 8, 16, 32, 64, 128)) {
    hw[['nodes']] = i
    prediction <- predict_from_hw(hw_params=hw)
    df <- rbind(df,
      data.frame(Nodes=hw[['nodes']],
                 Source="Model",
                 Performance=mean(prediction),
                 SD=sd(prediction)))
  }

  plot_modeled_range(df, "Nodes", input$predictMetric)
}


#####################
plot_speed_prediction <- function(perf, input)
{
  hw <- hw_from_input(input)
  df <- data.frame(Speed=hw[['speed']],
                   Source="Empirical",
                   Performance=mean(perf),
                   SD=sd(perf))

  for (i in seq(1, 6, 0.5)) {
    hw[['speed']] = i
    prediction <- predict_from_hw(hw_params=hw)
    df <- rbind(df,
      data.frame(Speed=hw[['speed']],
                 Source="Model",
                 Performance=mean(prediction),
                 SD=sd(prediction)))
  }

  plot_modeled_range(df, "Speed", input$predictMetric)
}


#####################
plot_memory_prediction <- function(perf, input)
{
  hw <- hw_from_input(input)
  df <- data.frame(Memory=hw[['memory']],
                   Source="Empirical",
                   Performance=mean(perf),
                   SD=sd(perf))

  for (i in c(1, 2, 4, 8, 16, 32, 64, 128)) {
    hw[['memory']] = i
    prediction <- predict_from_hw(hw_params=hw)
    df <- rbind(df,
      data.frame(Memory=hw[['memory']],
                 Source="Model",
                 Performance=mean(prediction),
                 SD=sd(prediction)))
  }

  plot_modeled_range(df, "Memory", input$predictMetric)
}


################################################
render_predict <- function(input, output, session)
{
  output$sharpLogo <- renderImage({
    filename <- normalizePath(file.path('./www', 'sharp.png'))
    list(src=filename, alt="TBD")
  }, deleteFile=FALSE)

  data <- reactiveValues()

  shinyFileChoose(input, 'predictFile', roots=c(logdir='../runlogs'), filetypes=c('csv'))
  pfn <- reactive(parseFilePaths(roots=c(logdir='../runlogs'), input$predictFile)$datapath)

  # Helper to get CSV filename - uses stored value if available, otherwise reactive
  get_pfn <- make_file_getter(pfn, data, "pfn")

  dataset <- reactive({
    req(length(get_pfn()) > 0)
    data$pfn <- pfn()  # Store when accessed
    read_csv(get_pfn())
  })
  best_fit_params <- reactive(best_fit(dataset() %>% pull(input$predictMetric)))

  observeEvent(input$predictFile, {
     req(nrow(dataset()) > 0)
     updateSelectInput(inputId='predictMetric', choices=metric_names(dataset()))
  })

  output$predictDistPlot <- renderPlot({
    req(nrow(dataset()) > 0)
    plot_prediction_density(dataset(), input)
  })

  pht <- 250 #"auto"

  output$predictCoresPlot <- renderPlot(height=pht, {
    req(nrow(dataset()) > 0)
    plot_cores_prediction(dataset() %>% pull(input$predictMetric), input)
  })

  output$predictNodesPlot <- renderPlot(height=pht, {
    req(nrow(dataset()) > 0)
    plot_nodes_prediction(dataset() %>% pull(input$predictMetric), input)
  })

  output$predictSpeedPlot <- renderPlot(height=pht, {
    req(nrow(dataset()) > 0)
    plot_speed_prediction(dataset() %>% pull(input$predictMetric), input)
  })

  output$predictMemoryPlot <- renderPlot(height=pht, {
    req(nrow(dataset()) > 0)
    plot_memory_prediction(dataset() %>% pull(input$predictMetric), input)
  })

  output$predictSummary <- renderText({
    req(nrow(dataset()) > 0)
    summaryOf(dataset())
  })
}
