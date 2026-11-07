#!/bin/sh
set -eu
source_dir="${1:-/tmp/phoneuse-direct-review}"
revision=$(git -C "$source_dir" rev-parse HEAD)
test "$revision" = 6bf94902f1c30aac712ae594a9a3a08136157a48 || {
  echo 'Expected the reviewed pinned source revision' >&2; exit 1;
}
experiment_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
remote_dir="$source_dir/Sources/iphone-use/Remote"
xcrun swiftc -parse-as-library -module-cache-path /tmp/phoneuse-direct-hid-modules \
  "$experiment_dir/coredevice_hid_probe.swift" \
  "$remote_dir/CoreDeviceClient.swift" "$remote_dir/RemoteServiceDiscovery.swift" \
  "$remote_dir/RemoteXPCConnection.swift" "$remote_dir/HTTP2.swift" \
  "$remote_dir/XPCObject.swift" "$remote_dir/XPCWrapper.swift" "$remote_dir/HIDService.swift" \
  -o /tmp/phoneuse-direct-hid-probe
