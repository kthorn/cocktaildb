#!/usr/bin/env python3
"""Quick test to demonstrate EMD speed improvement with num_threads=1"""
import time
import numpy as np
import ot

print("Testing EMD performance with different thread counts")
print("=" * 60)

# Create a problem similar to cocktail recipe comparisons
n = 300  # Typical size after ingredient hierarchy
np.random.seed(42)
a = np.random.rand(n)
a /= a.sum()
b = np.random.rand(n)
b /= b.sum()
cost = np.random.rand(n, n)

# Test different thread configurations
configs = [1, 2, 4, 'max']
results = {}

for n_threads in configs:
    times = []
    for _ in range(3):  # 3 runs for averaging
        start = time.time()
        result = ot.emd2(a, b, cost, numThreads=n_threads)
        elapsed = time.time() - start
        times.append(elapsed)

    avg_time = np.mean(times)
    results[n_threads] = avg_time
    print(f"numThreads={str(n_threads):>4}: {avg_time:.4f}s (avg of 3 runs)")

print()
print("Speed comparison relative to single-threaded:")
baseline = results[1]
for n_threads in configs:
    speedup = baseline / results[n_threads]
    if speedup > 1:
        print(f"  {str(n_threads):>4}: {speedup:.2f}x FASTER")
    else:
        print(f"  {str(n_threads):>4}: {1/speedup:.2f}x SLOWER")

print()
print(f"✓ Recommendation: Use num_threads=1 for {results[1]:.4f}s performance")
if results['max'] > results[1]:
    overhead_factor = results['max'] / results[1]
    print(f"⚠ Using 'max' threads is {overhead_factor:.1f}x SLOWER due to overhead!")
