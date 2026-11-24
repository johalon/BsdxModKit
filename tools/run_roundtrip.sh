#!/usr/bin/env bash
# Run the BSDX round-trip (parse -> JSON -> generate -> byte compare) over the real data in NeXAS_DX.
# Usage: run_roundtrip.sh [OUTDIR] [ext ...]     (default OUTDIR=/path/to/workspace/work/nexas_rt, all 6 formats)
set -euo pipefail
export JAVA_TOOL_OPTIONS= LC_ALL=C.UTF-8   # UTF-8 locale needed: some file names are non-ASCII
T=/path/to/workspace/tools
BUILD=${BUILD:-$T/nexas_build}
GAME=${GAME:-/path/to/ext/NeXAS_DX/src/main/resources/game/bsdx}   # read-only use
OUT=${1:-/path/to/workspace/work/nexas_rt}; shift || true
L=/opt/gradle-8.14.3/lib
CP=$BUILD/harness:$BUILD/classes:$T/libs/hutool-core-json-5.8.17-src-build.jar:$L/jackson-databind-2.16.1.jar:$L/jackson-core-2.16.1.jar:$L/jackson-annotations-2.16.1.jar:$L/slf4j-api-1.7.36.jar
java -Xmx6g -cp "$CP" RoundTrip "$GAME" "$OUT" "$@" 2>&1 | grep -v '^SLF4J'
