# Top-level server functionality for SHARP GUI
# © Copyright 2022--2025 Hewlett Packard Enterprise Development LP

server <- function(input, output) {
  render_measure(input, output)
  render_explore(input, output)
  render_compare(input, output)
}
