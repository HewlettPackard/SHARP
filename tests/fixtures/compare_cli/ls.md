Experiment completed at 2025-12-09 02:09:32.914383+00:00 (total experiment time: 0s, total rows: 3).

This file describes the conditions for the runs captured in ls.csv. The measurements were run on etc2, starting at 2025-12-09 02:09:32.009889+00:00 (UTC).
SHARP version: 4.0.0
SHARP's source code version used was from git hash: 63c95a4
Executable checksum (sha256): 148f5ab30...

## Initial runtime options

```json
{
  "backend_names": [
    "local"
  ],
  "backend_options": {
    "local": {
      "run": "$CMD $ARGS",
      "reset": "sudo sh -c '/usr/bin/sync; /sbin/sysctl vm.drop_caches=3'",
      "run_sys_spec": "$SPEC_COMMAND"
    }
  },
  "timeout": 3600,
  "verbose": false,
  "directory": "runlogs",
  "start": "normal",
  "mode": "w",
  "skip_sys_specs": false,
  "metrics": {},
  "mpl": 1,
  "entry_point": "/usr/bin/ls",
  "args": [],
  "task": "ls",
  "repeats": "COUNT",
  "repeater_options": {
    "max": 3
  }
}
```

## CSV field description

  * `launch_id` (string): Unique identifier for the launch (links to Invariant parameters).
  * `repeat` (int): Iteration/repeat number.
  * `rank` (int): MPI rank (0 for non-MPI).
  * `outer_time` (float): outer_time.


## Invariant field description

  * `task` (string): Task/benchmark name.
  * `start` (string): Warm, cold, or as-is start.
  * `concurrency` (int): Concurrent copies (MPL).

## Invariant parameters

Values are keyed by launch ID.

```json
{
  "a4cab45f": {
    "task": "ls",
    "start": "normal",
    "concurrency": 1
  }
}
```

## Initial system configuration

```json
{
  "cpu": {
    "processor_count": "128",
    "model_name": "Intel(R) Xeon(R) Gold 6448H",
    "vendor": "GenuineIntel",
    "cpu_cores": "32",
    "cache_size": "61440 KB",
    "cpu_temperature_celsius": "39.0",
    "fan_speed_rpm": "NA",
    "scaling_governor": "ondemand",
    "scaling_min_freq_khz": "800000",
    "scaling_max_freq_khz": "4100000",
    "scaling_cur_freq_khz": "800008",
    "architecture": "x86_64"
  },
  "memory": {
    "total_memory_kb": "1056554032",
    "available_memory_kb": "1023243620",
    "free_memory_kb": "991924772",
    "cached_memory_kb": "32382820",
    "swap_total_kb": "0",
    "swap_free_kb": "0"
  },
  "gpu": {
    "vendor": "NVIDIA\n/usr/bin/nvidia-smi",
    "name": "Tesla P4",
    "total_memory_mb": "7680",
    "free_memory_mb": "7593",
    "temperature_celsius": "40"
  },
  "load_average": {
    "one_minute": "5.20",
    "five_minute": "3.10",
    "fifteen_minute": "2.82"
  },
  "virtual_memory": {
    "swappiness": "60",
    "dirty_ratio": "20",
    "dirty_background_ratio": "10",
    "overcommit_memory": "1",
    "overcommit_ratio": "50"
  },
  "network": {
    "rmem_max": "212992",
    "wmem_max": "212992",
    "netdev_max_backlog": "1000",
    "somaxconn": "4096"
  },
  "filesystem": {
    "file_max": "9223372036854775807",
    "root_available_gb": "4645"
  },
  "kernel": {
    "version": "6.8.0-86-generic",
    "pid_max": "4194304",
    "threads_max": "8253638"
  },
  "scheduler": {
    "autogroup_enabled": "1",
    "cfs_bandwidth_slice_us": "5000",
    "rr_timeslice_ms": "100",
    "rt_period_us": "1000000",
    "rt_runtime_us": "950000"
  },
  "system": {
    "uptime_seconds": "3311335",
    "running_processes": "1825",
    "hostname": "etc2"
  }
}
```
