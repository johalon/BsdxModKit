#!/usr/bin/env bash
# Rebuild NeXAS_DX (non-GUI part) on Linux without Maven Central / lombok.
#  - copies /path/to/ext/NeXAS_DX -> $WORK (default /path/to/workspace/work/nexas_dx)
#  - delomboks sources with tools/delombok (DelombokLite, javac-tree based)
#  - compiles everything except JavaFX GUI classes against hutool (built from source, tools/libs),
#    jackson 2.16 + slf4j from the local Gradle install
#  - builds the RoundTrip / Direct harness
# Then run:  tools/run_roundtrip.sh [ext...]
set -euo pipefail
export JAVA_TOOL_OPTIONS= LC_ALL=C.UTF-8
T=/path/to/workspace/tools
WORK=${WORK:-/path/to/workspace/work/nexas_dx}
BUILD=${BUILD:-$T/nexas_build}
L=/opt/gradle-8.14.3/lib
CP=$T/delombok/build/stubs:$T/libs/hutool-core-json-5.8.17-src-build.jar:$L/jackson-databind-2.16.1.jar:$L/jackson-core-2.16.1.jar:$L/jackson-annotations-2.16.1.jar:$L/slf4j-api-1.7.36.jar

[ -d "$WORK" ] || cp -r /path/to/ext/NeXAS_DX "$WORK"

# lombok stubs + delombok tool
mkdir -p $T/delombok/build/stubs $T/delombok/build/tool
javac -d $T/delombok/build/stubs $(find $T/delombok/stubs -name '*.java')
javac -d $T/delombok/build/tool $T/delombok/DelombokLite.java

rm -rf "$BUILD"; mkdir -p "$BUILD"
java -cp $T/delombok/build/tool DelombokLite "$WORK/src/main/java" "$BUILD/src-main"
cd "$BUILD"
# drop JavaFX GUI + GUI-only model classes
rm -f src-main/com/giga/nexas/MainApplication.java src-main/com/giga/nexas/controller/*Controller.java \
      src-main/com/giga/nexas/controller/model/WorkspaceState.java src-main/com/giga/nexas/controller/model/WorkspaceCategory.java \
      src-main/com/giga/nexas/controller/model/WorkspaceTreeNode.java src-main/com/giga/nexas/controller/support/*.java
# ---- PROJECT PATCHES (BHE->BSDX experiment fixes; upstream untouched) ----
cp -r $T/patches/. src-main/
python3 $T/patches_py/fix_bhe_hitbox.py src-main   # BHE->BSDX spm hit-area kind/rect fix (調査記録 06 §3.3, 調査記録 08)
OBJ=src-main/com/giga/nexas/dto/bsdx/waz/wazfactory/wazinfoclass/obj
for f in CEventCpuButton CEventEffect CEventHeight CEventHit CEventEscape CEventCharge CEventScreenLine CEventRadialLine CEventStatus; do
  sed -i -E 's/(cn\.hutool\.core\.bean\.)?BeanUtil\.copyProperties\(/com.giga.nexas.util.ProjJsonCopy.copy(/' $OBJ/$f.java
done
sed -i 's/        bsdx.setAttackTargetType(bhe.getShort1());/        bsdx.setStartFrame(bhe.getStartFrame()); bsdx.setEndFrame(bhe.getEndFrame()); \/\/ PATCH(proj)\n        bsdx.setAttackTargetType(bhe.getShort1());/' $OBJ/CEventHit.java
# positional BHE unit lookup -> lookup by unitSlotNum (BHE lists hold only present units)
for f in CEventCharge CEventEscape CEventHeight CEventRadialLine CEventScreenLine CEventStatus; do
  sed -i -E 's/bheUnits\.size\(\) > i/com.giga.nexas.util.ProjJsonCopy.slotIndex(bheUnits, i) >= 0/; s/var bheUnit = bheUnits\.get\(i\);/var bheUnit = bheUnits.get(com.giga.nexas.util.ProjJsonCopy.slotIndex(bheUnits, i));/' $OBJ/$f.java
done
# Effect: FreeParam->CEventVal inner object never got start/end frame
sed -i 's/                        if (inner instanceof CEventVal valTarget) {/                        if (inner instanceof CEventVal valTarget) { valTarget.setStartFrame(bheFree.getStartFrame()); valTarget.setEndFrame(bheFree.getEndFrame()); valTarget.setInt1(0); valTarget.setInt2(0); valTarget.setInt3(0); valTarget.setInt4(0); \/\/ PATCH(proj)/' $OBJ/CEventEffect.java
mkdir -p classes
javac -nowarn -encoding UTF-8 -proc:none -d classes -cp "$CP" $(find src-main -name '*.java')
mkdir -p harness
javac -nowarn -d harness -cp "classes:$CP" $T/harness/RoundTrip.java $T/harness/Direct.java $T/harness/CloneMech.java $T/harness/BheRoundTrip.java $T/harness/JsonTransWaz.java
# experimental TransMeka (test source) for RunTsukuyomiPipeline
java -cp $T/delombok/build/tool DelombokLite "$WORK/src/test/java" src-test
mkdir -p testclasses
javac -nowarn -proc:none -encoding UTF-8 -d testclasses -cp "classes:$CP" src-test/com/giga/nexas/bhe2bsdx/steps/TransMeka.java
javac -nowarn -d harness -cp "testclasses:classes:$CP" $T/harness/RunTsukuyomiPipeline.java $T/harness/PortTool.java
echo "build ok: $BUILD"
