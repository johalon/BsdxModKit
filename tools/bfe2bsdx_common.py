#!/usr/bin/env python3
"""Shared helpers for the BFE (BALDR FORCE EXE) -> BSDX port tools (bfe2bsdx_spm.py, bfe2bsdx_waz.py,
mods/phase3b_tooru/build_phase3b.py). Java side = NeXAS_DX PortTool (b2j / j2b with re-parse check) run from a
private class snapshot (work/tooru_port/nexas_snap) so that concurrent rebuilds of tools/nexas_build do not interfere."""
import json, os, subprocess, collections, struct

# P = この作業ツリーの根（tools/ の 1 つ上）。クラウドでは /path/to/workspace、PC では <PROJECT>/_ws/proj（ビルド用の写し）。
# EXT = NeXAS_DX などの外部リポジトリの置き場（既定は P の隣の ext）。どちらも環境変数で差し替えられる。
P = (os.environ.get('BSDX_PROJ') or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))).replace('\\', '/')
EXT = (os.environ.get('BSDX_EXT') or os.path.dirname(P) + '/ext').replace('\\', '/')
T = P + '/tools'
SNAP = os.environ.get('BFE2BSDX_SNAP', P + '/work/tooru_port/nexas_snap')
L = '/opt/gradle-8.14.3/lib' if os.path.isfile('/opt/gradle-8.14.3/lib/jackson-core-2.16.1.jar') else T + '/libs'   # jars also copied to tools/libs (handoff 2026-10-28)
CP = os.pathsep.join([SNAP + '/harness', SNAP + '/testclasses', SNAP + '/classes', T + '/libs/hutool-core-json-5.8.17-src-build.jar',
               L + '/jackson-databind-2.16.1.jar', L + '/jackson-core-2.16.1.jar', L + '/jackson-annotations-2.16.1.jar',
               L + '/slf4j-api-1.7.36.jar'])
VAN = P + '/work/nexas_rt/json'          # vanilla BSDX data as NeXAS_DX JSON (RoundTrip output)

# ---------------------------------------------------------------- BFE -> DiveX: conventions shared by every mech
# (docs/porting/09_porting_another_mech.md §6 案 7, 2026-11-16: were defined twice in bfe2bsdx_spm / bfe2bsdx_waz, or in the build)
SKILL_BASE = 60                          # mech spm anim = SKILL_BASE + BFE SPR slot (anims 0..47 = DiveX basic motions)
SHARED_WAZ = ['Effect', 'Tama01', 'Tama02', 'Tama03', 'Tama04', 'Tama05', 'Laser', 'Bomb']   # vanilla WazaGroup 0..7 (shared waz)
BULLET_FILE, EFFECT_FILE, LASER_FILE = 4, 2, 6   # shared waz (WazaGroup) receiving converted bullets / effects / laser copies
# BSDX basic anim index -> (name, list of BFE SPR slots whose patterns are concatenated)
BASIC = {
    0: [6], 1: [7], 2: [8], 3: [9], 4: [10],
    5: [11], 6: [12], 7: [13], 8: [14], 9: [15], 10: [16], 11: [17], 12: [18], 13: [19], 14: [20], 15: [21], 16: [22],
    17: [35], 18: [36], 19: [37], 20: [38], 21: [39], 22: [40], 23: [41], 24: [42], 25: [43], 26: [44], 27: [45], 28: [46],
    29: [11], 30: [12], 31: [13],
    32: [26], 33: [27], 34: [28, 29, 30, 31, 32, 33, 34],
    35: [0], 36: [1], 37: [0, 1], 38: [0, 3], 39: [2], 40: [26],
    41: [4], 42: [50], 43: [5], 44: [4], 45: [50], 46: [5], 47: [2],
}
BASIC_ANIM_SLOT = {59: 26}               # Kou 浮遊 (anim 59, used by ブーストダッシュ硬直) -> BFE air slot 26 (anim = SKILL_BASE + 26)


def porttool(*jobs):
    flat = []
    for j in jobs:
        if flat:
            flat.append(';')
        flat += list(j)
    env = dict(os.environ, LC_ALL='C.UTF-8', JAVA_TOOL_OPTIONS='')
    r = subprocess.run(['java', '-Xmx6g', '-cp', CP, 'PortTool'] + flat, capture_output=True, text=True, env=env, encoding='utf-8', errors='replace')
    out = '\n'.join(l for l in r.stdout.splitlines() if not l.startswith('SLF4J'))
    if r.returncode != 0 or 'FAIL' in out:
        raise RuntimeError(out[-4000:] + r.stderr[-2000:])
    return out


def jload(p):
    return json.load(open(p, encoding='utf-8'))


def jsave(o, p):
    os.makedirs(os.path.dirname(p), exist_ok=True)
    json.dump(o, open(p, 'w', encoding='utf-8'), ensure_ascii=False)


def walk(o):
    if isinstance(o, dict):
        yield o
        for v in o.values():
            yield from walk(v)
    elif isinstance(o, list):
        for v in o:
            yield from walk(v)


def glist(g):
    return [v for k, v in g.items() if isinstance(v, list) and k != 'voiceTypeList'][0]


def norm(o):
    """drop parser bookkeeping keys for semantic comparisons"""
    if isinstance(o, dict):
        return {k: norm(v) for k, v in o.items() if k not in ('offset', 'length', 'fileName', 'extensionName')}
    if isinstance(o, list):
        return [norm(x) for x in o]
    return o


class Report:
    def __init__(self):
        self.items = collections.defaultdict(collections.Counter)
        self.log = []          # ordered (kind, msg) — per-weapon provenance (調査記録 15)

    def add(self, kind, msg, n=1):
        self.items[kind][msg] += n
        self.log.append((kind, msg))

    def mark(self):
        return len(self.log)

    def since(self, mark):
        return self.log[mark:]

    def dump(self, out=None):
        lines = []
        for k in sorted(self.items):
            c = self.items[k]
            lines.append('## %s (%d)' % (k, sum(c.values())))
            for m, n in sorted(c.items(), key=lambda x: (-x[1], x[0])):
                lines.append('  %s x%d' % (m, n))
        s = '\n'.join(lines)
        if out:
            open(out, 'w', encoding='utf-8').write(s + '\n')
        return s
