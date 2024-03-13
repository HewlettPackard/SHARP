# Benchmark: parallel sleep

The goal of this benchmark is to evaluate how the underlying job backend behaves with increasing degrees of parallelism.
We launch a `sleep 1` function in parallel, which should incur virtually no interference across the processes.
So any process that takes longer than about a second to run can attribute the extra run time to backend overheads.
By gradually increasing the concurrency level from 1 to 10, we can observe how many of the processes require a cold start at each step, which exposes how well the backend reacts to the growth in demand.

A typical response is that the backend does not anticipate the growth, so one of the processes always gets to run cold and take much longer than the others.
