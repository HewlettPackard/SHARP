#!/usr/bin/env python3
"""
A function to extract and aggregate the power metrics.

This function extracts the required key-value pairs from the JSON. It uses the
pairs to find the maximum, minimum and average power conusumed across all the
observations. It multiplies the average power with the total runtime to get
the estimate of the energy consumed.

All values are printed on the terminal which are then extracted with SHARP's
metric collector.

© Copyright 2022--2025 Hewlett Packard Enterprise Development LP
"""

import json
import argparse

# Append the required values to be displayed into the below list
lst = ['Average', 'Maximum', 'Minimum']


def json_val(filename, lst):
    val_lst = {'Average': [], 'Maximum': [], 'Minimum': []}
    with open(filename, "r") as f:
        for line in f:
            if line.startswith("{\"@"):
                obj = json.loads(line)
                for k in obj.items():
                    if k[0] in lst:
                        val_lst[k[0]].append(k[1])
    return val_lst

parser = argparse.ArgumentParser()
parser.add_argument('-st', '--start_time', required=True,
                    help='Starting time of the experiment')
parser.add_argument('-et', '--end_time', required=True,
                    help='Ending time of the experiment')
parser.add_argument('-of', '--output_file', required=True,
                    help='Output log file for iLO')

args = parser.parse_args()

start_time = int(args.start_time)
end_time = int(args.end_time)
output_file = args.output_file

power_val = json_val(output_file, lst)
average = sum(power_val['Average'])/len(power_val['Average'])
print("Average:", average)
print("Maximum:", max(power_val['Maximum']))
print("Minimum:", min(power_val['Minimum']))
print("Energy:", average * (end_time - start_time))
