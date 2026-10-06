#!/bin/sh
# Builds the optional window-pulse helper into bin/agtop-pulse.
# agtop finds it there and uses it after a jump; without it, agtop falls back
# to flashing the tab background.
set -eu
root=$(cd "$(dirname "$0")/.." && pwd)
mkdir -p "$root/bin"
swiftc -O "$root/pulse/main.swift" -o "$root/bin/agtop-pulse"
echo "Built $root/bin/agtop-pulse"
