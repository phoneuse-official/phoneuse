#!/bin/sh
set -eu
experiment_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
build_dir="${TMPDIR:-/tmp}/phoneuse-scroll-route"
mkdir -p "$build_dir"
xcrun swiftc -module-cache-path "$build_dir/modules" "$experiment_dir/scroll_route.swift" -o "$build_dir/scroll-route"
exec "$build_dir/scroll-route" "$@"
