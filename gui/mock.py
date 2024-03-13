#!/usr/bin/env python3 
#
# Mock program to pretend to be SHARP's launcher, for testing.
# Takes number of iterations as argument.

import sys
import time

n: int = int(sys.argv[1])
print(sys.argv)

for i in range(n):
    time.sleep(0.5)
    print(f"Completed run {i+1} for experiment mock and task sleep")
    sys.stdout.flush()
