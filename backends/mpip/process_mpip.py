#!/usr/bin/env python3

import sys
import re
from collections import defaultdict

def parse_mpip_file(filename):
    # Data structures to store aggregated values
    time_mean_stats = defaultdict(lambda: defaultdict(float))
    msg_mean_stats = defaultdict(lambda: defaultdict(float))
    time_count_stats = defaultdict(lambda: defaultdict(int))
    msg_count_stats = defaultdict(lambda: defaultdict(int))

    # Track which section we're in
    in_time_section = False
    in_msg_section = False

    with open(filename, 'r') as f:
        for line in f:
            line = line.strip()

            # Detect section headers
            if '@--- Callsite Time statistics' in line:
                in_time_section = True
                in_msg_section = False
                continue
            elif '@--- Callsite Message Sent statistics' in line:
                in_time_section = False
                in_msg_section = True
                continue
            elif '@--- End of Report' in line: # or line.startswith('-----------'):
                in_time_section = False
                in_msg_section = False
                continue

            # Skip header lines and empty lines
            if not line or line.startswith('Name') or len(line.split()) < 3:
                continue

            # Process lines in the time statistics section
            if in_time_section:
                parts = line.split()
                if len(parts) >= 6 and '*' not in parts[2]:
                    try:
                        op_name = parts[0]
                        rank = int(parts[2])
                        count = int(parts[3])
                        mean_time = float(parts[5])  # Mean time column
                        time_mean_stats[rank][op_name] += mean_time
                        time_count_stats[rank][op_name] += count
                    except (ValueError, IndexError):
                        pass

            # Process lines in the message statistics section
            if in_msg_section:
                parts = line.split()
                if len(parts) >= 6 and '*' not in parts[2]:
                    try:
                        op_name = parts[0]
                        rank = int(parts[2])
                        count = int(parts[3])
                        mean_size = float(parts[5])  # Mean size column
                        msg_mean_stats[rank][op_name] += mean_size
                        msg_count_stats[rank][op_name] += count
                    except (ValueError, IndexError):
                        pass

    return time_mean_stats, time_count_stats, msg_mean_stats, msg_count_stats

def print_results(time_mean_stats, time_count_stats, msg_mean_stats, msg_count_stats):
    # Print time statistics
    print("=== TIME STATISTICS (milliseconds) ===")
    ranks = sorted(time_mean_stats.keys())

    for rank in ranks:
        print(f"Rank {rank}:")
        for op, value in sorted(time_mean_stats[rank].items()):
            print(f"MPIP_perf_data time_mean_{op} {value/time_count_stats[rank][op]}")
            print(f"MPIP_perf_data time_count_{op} {time_count_stats[rank][op]}")
        for op, value in sorted(msg_mean_stats[rank].items()):
            print(f"MPIP_perf_data msg_mean_{op} {value/msg_count_stats[rank][op]}")
            print(f"MPIP_perf_data msg_count_{op} {msg_count_stats[rank][op]}")

def main():
    if len(sys.argv) != 2:
        print(f"Usage: {sys.argv[0]} <mpip_file>")
        sys.exit(1)

    filename = sys.argv[1]

    # Add some debug output
    print(f"Parsing file: {filename}")

    time_mean_stats, time_count_stats, msg_mean_stats, msg_count_stats = parse_mpip_file(filename)
    print_results(time_mean_stats, time_count_stats, msg_mean_stats, msg_count_stats)

if __name__ == "__main__":
    main()
