# Benchmark: start latency

This benchmark evaluates the overhead of launching an empty function in the underlying job backend.
Both a cold start (no pods currently running) and a warm start (right after a previous start) are measured against a local (shell) function start that ignores the backend altogether.
Comparing warm-start times to local times gives you a measure of how efficient function launching is at its best.
Comparing cold-start times to warm-start times gives you a measure of how efficient function launching is at its worst.

Note that all types of runs occur in sequences of three: cold, normal (warm), local---not as a series of all cold starts, all normal, etc.
This sequencing, similar to the DUET benchmarking method, lets us compare correlations and isolate transitory effects such as OS jitter.
Pay attention to the computed correlations between the three types.
If it's significant, it may indicate a transitory factor or another problem with the performance measurement.
