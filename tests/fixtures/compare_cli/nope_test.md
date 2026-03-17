Experiment completed at 2025-12-08 20:47:58.361608+00:00 (total experiment time: 4s, total rows: 10).

This file describes the conditions for the runs captured in nope_test.csv. The measurements were run on etc2, starting at 2025-12-08 20:47:54.262929+00:00 (UTC).
SHARP version: 4.0.0
SHARP's source code version used was from git hash: 63c95a4
Executable checksum (sha256): ba2d50188...

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
  "metrics": {
    "inner_time": {
      "description": "Run time as reported by the function",
      "extract": "grep '@@@ Time' | awk '{ print $(NF); }'",
      "lower_is_better": true,
      "type": "numeric",
      "units": "seconds"
    }
  },
  "mpl": 1,
  "entry_point": "/home/frachten/sharp/build/appimages/nope-x86_64.AppImage",
  "args": [],
  "task": "nope_test",
  "repeats": "10",
  "repeater_options": {
    "max": 10
  }
}
```

## CSV field description

  * `launch_id` (string): Unique identifier for the launch (links to Invariant parameters).
  * `repeat` (int): Iteration/repeat number.
  * `rank` (int): MPI rank (0 for non-MPI).
  * `outer_time` (float): outer_time.
  * `inner_time` (float): inner_time.


## Invariant field description

  * `task` (string): Task/benchmark name.
  * `start` (string): Warm, cold, or as-is start.
  * `concurrency` (int): Concurrent copies (MPL).

## Invariant parameters

Values are keyed by launch ID.

```json
{
  "63d47b55": {
    "task": "nope_test",
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
    "scaling_cur_freq_khz": "1690514",
    "architecture": "x86_64"
  },
  "memory": {
    "total_memory_kb": "1056554032",
    "available_memory_kb": "1023983576",
    "free_memory_kb": "992850972",
    "cached_memory_kb": "32231644",
    "swap_total_kb": "0",
    "swap_free_kb": "0"
  },
  "gpu": {
    "vendor": "NVIDIA\n/usr/bin/nvidia-smi",
    "name": "Tesla P4",
    "total_memory_mb": "7680",
    "free_memory_mb": "7593",
    "temperature_celsius": "39"
  },
  "load_average": {
    "one_minute": "2.36",
    "five_minute": "2.58",
    "fifteen_minute": "2.11"
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
    "uptime_seconds": "3292041",
    "running_processes": "1853",
    "hostname": "etc2"
  }
}
```
