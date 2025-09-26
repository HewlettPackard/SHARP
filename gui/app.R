# Top-level source file for SHARP GUI
# © Copyright 2022--2025 Hewlett Packard Enterprise Development LP


library(DT)
library(GGally)
library(ggdist)
library(PearsonDS)
library(processx)
library(shiny)
library(shinybusy)
library(shinyFiles)
library(shinythemes)
library(stringr)
library(tidyverse)


source("utils.R")
source("ui.R")
source("server.R")

shinyApp(ui=ui, server=server)
