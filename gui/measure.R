# UI for Measure tab
# © Copyright 2022--2025 Hewlett Packard Enterprise Development LP


library("stringr")

available.configs <- gsub(".yaml", "", list.files(path=bdir, pattern="\\.yaml$"))

in_docker <- length(system("awk ' {print $4; } ' /proc/self/mountinfo | grep '^/docker'", intern=T)) > 0
if (in_docker) {
  backend_choices <- c("local")
} else {
  backend_choices <- c('local', 'ssh', 'fission', 'knative', 'docker', 'mpi')
}

#################################################
measurePanel <- tabPanel('Measure',
  sidebarLayout(
    sidebarPanel(
      textInput('experiment', "Experiment name", "misc"),

      fluidRow(
        column(6, textInput('func', "Program & arguments")),
        column(6, textInput('task', "Task name (optional)")),
      ),

      fluidRow(
        column(6,
          selectInput('stopping', "When to stop?",
                      choices=c('Exact count'="MAX",
                                'Standard error'="SE",
                                'Confidence interval'="CI",
                                'High-density interval'="HDI",
                                'Gaussian mixture'="GMM",
                                'Kolmogorov-Smirnov'="KS",
                                'Auto-stop'="DC"
                                )),
        ),
        column(4,
          numericInput('n', "Maximum runs", 1),
        ),
      ),

      tags$div(id="inline",
        selectInput('backend', "Where to run it?\U02001", choices=backend_choices),

        numericInput('mpl', "How many parallel copies?\U02001", 1),

        selectInput('start', "How to start each run?",
                    choices=c("as-is", "cold", "warm")),

        numericInput('timeout', "How long before timeout (sec)?\U02001", 60),

        selectInput('configs', "Which config to include?", multiple=TRUE,
                    choices=available.configs,
                    selected=c("default_config"),
                    selectize=FALSE,
                    size=2),
      ),

      textInput('moreopts', "Any other arguments to pass along to SHARP?"),

      fluidRow(column(12, align="right", style="margin-top: 50px;",
          actionButton('runButton', "Run", class="btn-success", icon=icon("circle-play"))
      ))
    ),

    mainPanel(
      DT::dataTableOutput('runData'),
#      fluidRow(
#        column(2, downloadButton('downloadRunData', label="Download run data", icon=icon("up"))),
#        column(8, hr()),
#        column(2, downloadButton('downloadMetadata', label="Download metadata", icon=icon("down"))),
#      ),
      verbatimTextOutput('mdData')
    )
  )
)


#################################################
compute_args <- function(input)
{
  # Basic arguments:
  args <- c("-v")
  args = c(args, "-e", input$experiment)
  args = c(args, "-b", input$backend)
  args = c(args, "-r", input$stopping)
  args = c(args, "--mpl", input$mpl)
  args = c(args, "--timeout", input$timeout)

  if (input$moreopts != "") {
    args = c(args, scan(text=input$moreopts, what='character', quiet=TRUE))
  }

  if (input$task != "") {
    args = c(args, "-t", input$task)
  }

  if (input$start == "cold") {
    args = c(args, "-c")
  } else if (input$start == "warm") {
    args = c(args, "-w")
  }


  # Configs, including custom backends and a temporary one with stopping max:
  if (input$backend == "knative") {
    args = c(args, "-f", paste0(bdir, "knative.yaml"))
  }
  if (input$backend == "fission") {
    args = c(args, "-f", paste0(bdir, "fission.yaml"))
  }

  for (cfg in input$configs) {
    args = c(args, "-f", paste0(bdir, cfg, ".yaml"))
  }
  write(paste('{ "repeater_options": { "max":', input$n, '} }'), file="/tmp/max.yaml")
  args = c(args, "-f", "/tmp/max.yaml")

  # Finally, function/cmd to run with its arguments:
  args = c(args, scan(text=input$func, what='character', quiet=TRUE))
}


#################################################
measure <- function(input)
{
  n <- input$n
  patrun <- paste("Completed run ([0-9]+) for experiment", input$experiment)

  cmd <- paste0(ldir, "launch.py")
  args <- compute_args(input)
  print(args)
  proc <- process$new(cmd, args, stdout="|")
  logpat <- "Logging runs to: (.*) at"

  withProgress(message="Running benchmarks...", value=0, min=1, max=n, {
    if (!proc$is_alive()) {
      print("Output:")
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
    showModal(modalDialog("Error: Failed to find parse program output!"))
    basefn <- ""
  }

  basefn
}

#################################################
getRunData <- function(fn)
{
  read_csv(fn)
}

#################################################
getMetadata <- function(fn)
{
  readChar(fn, file.info(fn)$size)
}

#################################################
render_measure <- function(input, output) {
  observeEvent(input$runButton, {
    if (input$func == "") {
      showModal(modalDialog("Function or executable required"))
    } else {
      basefn <- run_sharp(compute_args(input), input$n, input$experiment)
      output$runData <- DT::renderDataTable(getRunData(paste0(basefn, '.csv')), options=list(pageLength=5))
      output$mdData <- renderText(getMetadata(paste0(basefn, '.md')))
    }
  })
}
