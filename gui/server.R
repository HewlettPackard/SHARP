# Top-level server functionality for SHARP GUI
# © Copyright 2022--2025 Hewlett Packard Enterprise Development LP

server <- function(input, output, session) {
  render_measure(input, output, session)
  render_explore(input, output, session)
  render_compare(input, output, session)
  render_optimize(input, output, session)
}
