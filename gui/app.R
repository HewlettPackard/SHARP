# Top-level source file for SHARP GUI
# © Copyright 2022--2024 Hewlett Packard Enterprise Development LP


library(DT)
library(ggdist)
library(PearsonDS)
library(processx)
library(shiny)
library(shinyFiles)
library(shinythemes)
library(stringr)
library(tidyverse)


source("utils.R")
source("ui.R")
source("server.R")

shinyApp(ui=ui, server=server)
