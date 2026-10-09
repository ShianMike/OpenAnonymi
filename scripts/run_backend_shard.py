"""Run one of four balanced pytest module groups, each on its own CI database."""

import collections
import subprocess
import sys


def main():
    shard = int(sys.argv[1])
    assert 0 <= shard < 4
    collected = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q"],
        capture_output=True, text=True, check=False,
    )
    if collected.returncode:
        print(collected.stdout)
        print(collected.stderr, file=sys.stderr)
        return collected.returncode
    nodes = [line for line in collected.stdout.splitlines()
             if line.startswith("tests/") and "::" in line]
    assert nodes, "No backend tests collected"
    counts = collections.Counter(node.split("::", 1)[0] for node in nodes)
    # ponytail: balance by case count; use reported durations if costly modules skew a shard.
    groups, weights = [[] for _ in range(4)], [0] * 4
    for module in sorted(counts, key=lambda module: (-counts[module], module)):
        index = min(range(4), key=weights.__getitem__)
        groups[index].append(module)
        weights[index] += counts[module]
    assert sorted(module for group in groups for module in group) == sorted(counts)
    assert sum(weights) == len(nodes) and all(groups)
    print(f"Backend shard {shard + 1}/4: {weights[shard]} of {len(nodes)} cases; "
          f"balanced counts {weights}", flush=True)
    return subprocess.call([sys.executable, "-m", "pytest", "-q", "--durations=20",
                            *groups[shard], *sys.argv[2:]])


if __name__ == "__main__":
    sys.exit(main())
