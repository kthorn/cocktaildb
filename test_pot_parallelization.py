#!/usr/bin/env python3
"""Test script to verify POT parallelization behavior."""
import time
import os
import numpy as np
import psutil

# Check POT configuration
import ot
print("=" * 70)
print("POT Configuration Check")
print("=" * 70)
print(f"POT version: {ot.__version__}")

# Check backend
try:
    print(f"POT backend: {ot.backend.get_backend()}")
except:
    print("POT backend: (unable to detect)")

# Check if OpenMP is available
try:
    from ot.lp import emd
    print(f"EMD solver available: Yes")
    # Check if compiled with OpenMP support
    import subprocess
    result = subprocess.run(['ldd', ot.lp.__file__], capture_output=True, text=True)
    if 'libgomp' in result.stdout or 'libomp' in result.stdout:
        print("OpenMP support detected: Yes (libgomp/libomp linked)")
    else:
        print("OpenMP support detected: Unknown (check compilation flags)")
except Exception as e:
    print(f"EMD solver check failed: {e}")

print()

# Check system thread configuration
print("=" * 70)
print("System Threading Configuration")
print("=" * 70)
print(f"CPU count (logical): {os.cpu_count()}")
print(f"CPU count (physical): {psutil.cpu_count(logical=False)}")
print(f"OMP_NUM_THREADS: {os.environ.get('OMP_NUM_THREADS', 'not set')}")
print(f"MKL_NUM_THREADS: {os.environ.get('MKL_NUM_THREADS', 'not set')}")
print(f"OPENBLAS_NUM_THREADS: {os.environ.get('OPENBLAS_NUM_THREADS', 'not set')}")
print()

# Test with CPU monitoring
print("=" * 70)
print("CPU Usage Test")
print("=" * 70)
print("Running EMD computation with numThreads='max'...")
print("Monitor CPU usage to see if multiple cores are utilized.")
print()

# Create a moderately-sized problem
n = 500
np.random.seed(42)
a = np.random.rand(n)
a /= a.sum()
b = np.random.rand(n)
b /= b.sum()
cost = np.random.rand(n, n)

# Get initial CPU usage
process = psutil.Process()
cpu_percent_before = process.cpu_percent(interval=0.1)

# Run EMD with numThreads='max'
print(f"Problem size: {n}x{n}")
print(f"Testing ot.emd2 with numThreads='max'...")
start_time = time.time()

# Monitor CPU during computation
cpu_samples = []
def monitor_cpu():
    for _ in range(10):
        cpu_samples.append(process.cpu_percent(interval=0.1))

import threading
monitor_thread = threading.Thread(target=monitor_cpu, daemon=True)
monitor_thread.start()

# Run the computation
distance = ot.emd2(a, b, cost, numThreads='max')

elapsed = time.time() - start_time
monitor_thread.join(timeout=1)

print(f"Computation time: {elapsed:.3f}s")
print(f"EMD distance: {distance:.6f}")

if cpu_samples:
    avg_cpu = np.mean(cpu_samples)
    max_cpu = np.max(cpu_samples)
    print(f"Average CPU usage during computation: {avg_cpu:.1f}%")
    print(f"Peak CPU usage during computation: {max_cpu:.1f}%")

    # Interpretation
    print()
    if max_cpu > 150:  # More than 1.5 cores
        print("✓ RESULT: Multiple cores appear to be in use")
    elif max_cpu > 100:
        print("⚠ RESULT: Some parallel usage detected, but limited")
    else:
        print("✗ RESULT: Likely single-threaded (CPU < 100%)")
        print("  This suggests POT may not be using OpenMP parallelization")

print()
print("=" * 70)
print("Additional Test: Explicit numThreads Values")
print("=" * 70)

# Test with explicit thread counts
n_small = 300
a_small = np.random.rand(n_small)
a_small /= a_small.sum()
b_small = np.random.rand(n_small)
b_small /= b_small.sum()
cost_small = np.random.rand(n_small, n_small)

for n_threads in [1, 2, 4, 'max']:
    try:
        start = time.time()
        result = ot.emd2(a_small, b_small, cost_small, numThreads=n_threads)
        elapsed = time.time() - start
        print(f"numThreads={n_threads:>4}: {elapsed:.3f}s (distance={result:.6f})")
    except Exception as e:
        print(f"numThreads={n_threads:>4}: ERROR - {e}")

print()
print("If times decrease as numThreads increases, parallelization is working.")
print("If times are similar regardless of numThreads, POT may be single-threaded.")
