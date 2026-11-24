#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""build_packs.py — 透パック 4 つ（3b / waz110 / modified / waz110 modified）をビルドし、照合して配置する。

  python tools/build_packs.py              … 同期 → 通常・--waz110 を 2 回ずつビルド → 2 回の sha256 が一致するか確認
                                              → pac と自動生成ファイルを <PROJECT> に戻す → SHA256SUMS.txt を更新
  python tools/build_packs.py --once       … 各 1 回だけビルド（試行用。2 回一致の確認をしない）
  python tools/build_packs.py --no-copy    … <PROJECT> に戻さない（ビルド用の写しの中だけ）
  python tools/build_packs.py --sync-only  … 同期だけ
  python tools/build_packs.py --status     … 記録（SHA256SUMS.txt）と、いま置いてある pac の sha256 を比べるだけ

表示は英数字だけ（PowerShell 越しでも文字化けしないように）。same = 前回の記録と同じ / CHANGED (was XXXXXXXX) = 変わった。
制作記録 などに貼る日本語の 1 行は _ws/build_logs/summary.txt（UTF-8）に書く。

PC（Windows）: <PROJECT> は git の作業ツリーで、ゲーム由来のデータを持たない。ビルドは <PROJECT>/_ws/proj（データを持つ写し）で行う。
  「同期」= git から見えるファイル（追跡中 + 未追跡で .gitignore 対象外）を _ws/proj に重ねること。
  Pillow などは <PROJECT>/_ws/s_tmp/py、SE の ogg は <PROJECT>/_ws/s_tmp/ogg（環境変数 S_TMP で場所を変えられる）。
クラウド: 作業ツリー自体がデータを持つ（_ws/proj が無い）ので、同期も配置もせず、その場でビルドして照合だけ行う。

終了コード 0 = 成功。ビルドの失敗、2 回の sha256 の不一致、置いてある pac が記録と違う（他の作業が書き換えた）ときは 0 以外。
"""
import os, sys, subprocess, hashlib, shutil, zipfile, time, functools

print = functools.partial(print, flush=True)     # 途中経過をすぐ出す（パイプ越しでも見えるように）

R = os.path.dirname(os.path.dirname(os.path.abspath(__file__))).replace('\\', '/')
WS = R + '/_ws/proj'
PC = os.path.isdir(WS)                   # True: PC（写しでビルド） / False: 作業ツリーでそのままビルド
B = WS if PC else R                      # ビルドする場所
S_TMP = (os.environ.get('S_TMP') or R + '/_ws/s_tmp').replace('\\', '/')
MOD = 'mods/phase3b_tooru'
PACS = [('3b', MOD + '/Update3.pac'),
        ('waz110', MOD + '/variantB_waz110/Update3.pac'),
        ('modified', MOD + '/modified/Update3.pac'),
        ('modified waz110', MOD + '/variantB_waz110/modified/Update3.pac')]
SUMS = MOD + '/SHA256SUMS.txt'           # 配置した pac の記録（git に入れる。pac 自体は入れない）
GENERATED = ['notes/15_provenance_tooru_table.md', 'notes/15b_balance_tooru_table.md', 'notes/15c_modified_tweaks.md',
             'work/tooru_port/report.txt', 'work/tooru_port/balance_table.md', 'work/tooru_port/balance_table_waz110.md']
LOCK = 'work/tooru_port/BUILD.lock'
LOCK_STALE = 30 * 60                     # これより古いロックは消してよい（制作記録）


def sha(p):
    h = hashlib.sha256()
    with open(p, 'rb') as f:
        for c in iter(lambda: f.read(1 << 20), b''):
            h.update(c)
    return h.hexdigest().upper()


def read_sums():
    d = {}
    if os.path.isfile(R + '/' + SUMS):
        for l in open(R + '/' + SUMS, encoding='utf-8'):
            if l.strip() and not l.startswith('#'):
                h, p = l.split(None, 1)
                d[p.strip()] = h
    return d


def sync():
    """git から見えるファイルを _ws/proj に重ねる（消したファイルは _ws/proj からも消す）。"""
    out = subprocess.run(['git', '-c', 'core.quotepath=false', 'ls-files', '-co', '--exclude-standard', '-z'], cwd=R,
                         capture_output=True, check=True).stdout.decode('utf-8')
    files = [f for f in out.split('\0') if f]
    n = 0
    for f in files:
        s, d = R + '/' + f, WS + '/' + f
        if not os.path.isfile(s):
            continue                     # 作業ツリーで消してあるファイル
        if os.path.isfile(d) and os.path.getsize(s) == os.path.getsize(d) and open(s, 'rb').read() == open(d, 'rb').read():
            continue
        os.makedirs(os.path.dirname(d), exist_ok=True)
        shutil.copyfile(s, d); n += 1
    # 前回の同期で入れて、今回 git から見えなくなったファイルを消す（消したツールが import され続けるのを防ぐ）
    man = WS + '/.synced_files.txt'
    old = set(open(man, encoding='utf-8').read().split('\n')) if os.path.isfile(man) else set()
    gone = [f for f in old - set(files) if f and os.path.isfile(WS + '/' + f) and not os.path.isfile(R + '/' + f)]
    for f in gone:
        os.remove(WS + '/' + f)
    open(man, 'w', encoding='utf-8', newline='\n').write('\n'.join(sorted(files)))
    # Java 17 で読めるように、同梱 jar の class 版数を 61 に下げる（1 回当てれば以後は何もしない）
    jar = WS + '/tools/libs/hutool-core-json-5.8.17-src-build.jar'
    if os.path.isfile(jar):
        with zipfile.ZipFile(jar) as a:
            newer = any(i.filename.endswith('.class') and a.read(i)[7] > 61 for i in a.infolist())
        if newer:
            with zipfile.ZipFile(jar) as a, zipfile.ZipFile(jar + '.new', 'w', zipfile.ZIP_DEFLATED) as b:
                for i in a.infolist():
                    d = a.read(i)
                    if i.filename.endswith('.class') and d[7] > 61:
                        d = d[:7] + bytes([61]) + d[8:]
                    b.writestr(i, d)
            os.replace(jar + '.new', jar)
    print('sync: %d files updated, %d removed -> %s' % (n, len(gone), WS))


def build(args, tag):
    env = dict(os.environ, PYTHONUTF8='1')
    if PC:
        env['PYTHONPATH'] = S_TMP + '/py' + (os.pathsep + env['PYTHONPATH'] if env.get('PYTHONPATH') else '')
        if os.path.isdir(S_TMP + '/ogg'):     # PC は以前に作った ogg を使う（ffmpeg の版でバイトが変わるのを避ける）
            env['OGG_CACHE'] = S_TMP + '/ogg'
    logdir = (R + '/_ws/build_logs') if PC else (B + '/work/tooru_port/build_logs')
    os.makedirs(logdir, exist_ok=True)
    log = '%s/%s.log' % (logdir, tag)
    t = time.time()
    with open(log, 'w', encoding='utf-8') as f:
        r = subprocess.run([sys.executable, MOD + '/build_phase3b.py'] + args, cwd=B, env=env, stdout=f, stderr=subprocess.STDOUT)
    print('build %-12s %s  %.0fs  log: %s' % (tag, 'ok' if r.returncode == 0 else 'FAILED', time.time() - t, log))
    if r.returncode != 0:
        print(''.join(open(log, encoding='utf-8', errors='replace').readlines()[-25:]))
        sys.exit(1)


def status():
    rec = read_sums(); bad = 0
    for name, p in PACS:
        cur = sha(R + '/' + p) if os.path.isfile(R + '/' + p) else None
        ok = cur is not None and rec.get(p) == cur
        bad += not ok
        print('%-16s %s  %s' % (name, (cur or '(none)')[:8], '= recorded' if ok else 'DIFFERS from recorded %s' % (rec.get(p) or '(none)')[:8]))
    return bad


def main():
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    a = sys.argv[1:]
    unknown = [x for x in a if x not in ('--once', '--no-copy', '--sync-only', '--status', '--force')]
    if unknown:
        sys.exit('unknown option: %s\n%s' % (' '.join(unknown), __doc__))
    if '--status' in a:
        sys.exit(1 if status() else 0)
    lock = B + '/' + LOCK
    if os.path.isfile(lock):
        age = time.time() - os.path.getmtime(lock)
        if age < LOCK_STALE and '--force' not in a:
            sys.exit('LOCKED: BUILD.lock があります（%d 分前。他の作業がビルド中かもしれません）。待つか、--force を付けてください。' % (age // 60))
        os.remove(lock)
    if PC:
        sync()
    if '--sync-only' in a:
        return
    open(lock, 'w').write('build_packs.py %s\n' % time.strftime('%Y-%m-%d %H:%M:%S'))
    try:
        runs = 1 if '--once' in a else 2
        res = []
        for i in range(runs):
            build([], 'build_%d' % (i + 1))
            build(['--waz110'], 'build_%d_waz110' % (i + 1))
            res.append({p: sha(B + '/' + p) for _, p in PACS})
        if runs == 2 and res[0] != res[1]:
            for name, p in PACS:
                if res[0][p] != res[1][p]:
                    print('MISMATCH %s: %s / %s' % (name, res[0][p][:8], res[1][p][:8]))
            sys.exit('NONDETERMINISTIC: 2 回のビルドで sha256 が一致しません（決定的でない変更が入っています）。配置しません。')
    finally:
        if os.path.isfile(lock):
            os.remove(lock)
    new = res[-1]; rec = read_sums()
    if PC and '--no-copy' not in a:
        # 置いてある pac が記録と違う = 他の作業が置き換えた。黙って上書きしない
        moved = [p for _, p in PACS if os.path.isfile(R + '/' + p) and rec.get(p) and sha(R + '/' + p) != rec[p]]
        if moved and '--force' not in a:
            sys.exit('PLACED-PAC-CHANGED: 置いてある pac が SHA256SUMS.txt の記録と違います（他の作業が置き換えた可能性）: %s\n確認のうえ --force で上書き。'
                     % ', '.join(moved))
        for _, p in PACS:
            os.makedirs(os.path.dirname(R + '/' + p), exist_ok=True)
            shutil.copyfile(B + '/' + p, R + '/' + p)
            assert sha(R + '/' + p) == new[p], 'copy verify failed: ' + p
        for g in GENERATED:
            if os.path.isfile(B + '/' + g):
                shutil.copyfile(B + '/' + g, R + '/' + g)
        with open(R + '/' + SUMS, 'w', encoding='utf-8', newline='\n') as f:
            f.write('# 配置済みパックの sha256（tools/build_packs.py が書く。pac 自体は git に入れない）\n')
            for _, p in PACS:
                f.write('%s  %s\n' % (new[p], p))
        print('placed: 4 pacs + generated notes -> %s' % R)
    print()
    for name, p in PACS:
        old = rec.get(p)
        print('%-16s %s  %s' % (name, new[p][:8], 'same' if old == new[p] else 'CHANGED (was %s)' % (old or 'none')[:8]))
    s = lambda n: new[dict(PACS)[n]][:8]
    same = all(rec.get(dict(PACS)[n]) == new[dict(PACS)[n]] for n in ('3b', 'waz110'))
    line = ('3b %s / waz110 %s%s、modified %s / waz110 %s（%s）'
            % (s('3b'), s('waz110'), '（不変）' if same and rec else '', s('modified'), s('modified waz110'),
               '2 回ビルド一致' if runs == 2 else '1 回だけビルド'))
    summ = ((R + '/_ws/build_logs') if PC else (B + '/work/tooru_port/build_logs')) + '/summary.txt'
    open(summ, 'w', encoding='utf-8', newline='\n').write(line + '\n')      # 制作記録 に貼る 1 行（UTF-8）
    print('\nsummary line (UTF-8): %s' % summ)

if __name__ == '__main__':
    main()
