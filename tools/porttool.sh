#!/usr/bin/env bash
# Wrapper for harness/PortTool (see PortTool.java). Build first with tools/build_nexas_dx.sh.
export JAVA_TOOL_OPTIONS= LC_ALL=C.UTF-8
T=/path/to/workspace/tools; B=${BUILD:-$T/nexas_build}; L=/opt/gradle-8.14.3/lib
CP=$B/harness:$B/testclasses:$B/classes:$T/libs/hutool-core-json-5.8.17-src-build.jar:$L/jackson-databind-2.16.1.jar:$L/jackson-core-2.16.1.jar:$L/jackson-annotations-2.16.1.jar:$L/slf4j-api-1.7.36.jar
exec java -Xmx6g -cp "$CP" PortTool "$@" 2>&1 | grep -v '^SLF4J'
