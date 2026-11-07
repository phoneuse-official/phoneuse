#!/bin/sh
set -eu
experiment_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
build_dir="${TMPDIR:-/tmp}/phoneuse-mirroring-probe"
mkdir -p "$build_dir"
xcrun swiftc -parse-as-library -module-cache-path "$build_dir/modules" "$experiment_dir/probe.swift" -o "$build_dir/mirror-probe"
exec "$build_dir/mirror-probe" "$@"
