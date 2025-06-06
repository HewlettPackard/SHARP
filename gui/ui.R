# Top-level UI definition for SHARP GUI
# © Copyright 2022--2025 Hewlett Packard Enterprise Development LP

source("measure.R")
source("explore.R")
source("compare.R")

PAGE_TITLE <- "SHARP"

ui <- fluidPage(theme=shinytheme("spacelab"),
                #shinythemes::themeSelector(),

  tags$head(    # Tag for fields in-line with table
    tags$style(type="text/css", "#inline label{ display: table-cell; text-align: left; vertical-align: middle; } 
              #inline .form-group { display: table-row;}")
  ),

  navbarPage(windowTitle="SHARP",
             title=div(img(src="sharp.png", height=30, width=90), ""),

    measurePanel, explorePanel, comparePanel
  )
)
