#!/usr/bin/env python3
"""Minimal BSDX NeXAS .bin script disassembler / call renderer.
Port of NeXAS_DX BinParser layout + naive R0/arg tracking.
usage: bsdx_bindis.py file.bin [--raw] [--globals __GLOBAL.bin]
Native names from NeXAS_DX Operand.java (parsed at runtime if path exists).
"""
import struct, sys, re, os
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__))).replace('\\', '/')    # この作業ツリーの根（tools/ の 1 つ上）

OPN = {0:'VAL',4:'PUSH',5:'PARAM',6:'POP',7:'CALL',8:'LOAD',9:'ADD',10:'SUB',11:'MUL',12:'DIV',13:'MOD',14:'STORE',
15:'OR',16:'AND',17:'BOR',18:'BAND',19:'XOR',20:'NOT',21:'LE',22:'GE',23:'LT',24:'GT',25:'EQ',26:'NE',27:'START',28:'END',
29:'MARKER',34:'INC',35:'DEC',43:'CMPZ',44:'LINENO',45:'SAR',46:'SHL',47:'LD_ADD',48:'LD_SUB',49:'LD_MUL',50:'LD_DIV',
51:'LD_MOD',52:'LD_OR',53:'LD_AND',54:'LD_XOR',55:'LD_SAR',56:'LD_SHL',61:'TOSTR',62:'RET',63:'JMP',64:'JZ',65:'JNZ'}
BINOP = {9:'+',10:'-',11:'*',12:'/',13:'%',15:'||',16:'&&',17:'|',18:'&',19:'^',21:'<=',22:'>=',23:'<',24:'>',25:'==',26:'!=',45:'>>',46:'<<'}

NATIVE = {}
_op = os.path.dirname(_ROOT) + '/ext/NeXAS_DX/src/main/java/com/giga/nexas/dto/bsdx/bin/consts/Operand.java'
if os.path.exists(_op):
    for m in re.finditer(r'^\s+([A-Za-z_0-9]+)\((\d+)\)', open(_op, encoding='utf-8').read(), re.M):
        NATIVE[int(m.group(2))] = m.group(1)

def cstrs(b, p, n):
    out = []
    for _ in range(n):
        e = b.index(b'\0', p); out.append(b[p:e].decode('cp932', 'replace')); p = e + 1
    return out, p

def parse(b):
    p = 0
    pre, = struct.unpack_from('<i', b, p); p += 4 + pre * 8
    n, = struct.unpack_from('<i', b, p); p += 4
    ins = [struct.unpack_from('<iI', b, p + 8 * i) for i in range(n)]; p += 8 * n
    k, = struct.unpack_from('<i', b, p); p += 4
    strs, p = cstrs(b, p, k)
    k, = struct.unpack_from('<i', b, p); p += 4
    props, p = cstrs(b, p, k)
    k, = struct.unpack_from('<i', b, p); p += 4
    props2, p = cstrs(b, p, k)
    return ins, strs, props, props2

def render(path, raw=False):
    b = open(path, 'rb').read()
    ins, strs, props, props2 = parse(b)
    R = {0: '?', 1: '?'}; stack = []; args = []
    lines = []
    def q(s): return '"' + s.replace('\n', '\\n') + '"'
    def var(i):
        if i < 0 or i >= 0x80000000:
            i2 = i & 0x7fffffff if i >= 0 else i & 0x7fffffff
            return 'S%d' % i2
        return 'V%d' % i
    for idx, (op, opd) in enumerate(ins):
        name = OPN.get(op, 'OP%d' % op)
        if raw:
            lines.append('%5d %-7s %d' % (idx, name, opd if opd < 0x80000000 else opd - 0x100000000))
        if op == 0: R[0] = str(opd if opd < 0x80000000 else opd - 0x100000000)
        elif op == 4: stack.append(R.get(opd, '?'))
        elif op == 6: R[opd] = stack.pop() if stack else '?'
        elif op == 5:
            if opd == 1:
                try: args.append(q(strs[int(R[0])]))
                except Exception: args.append('str(%s)' % R[0])
            else: args.append(R[0])
        elif op == 7:
            argc = opd >> 16; fid = opd & 0xffff
            if fid & 0x8000:
                fn = 'script_%d' % (fid - 0x10000)
            else:
                fn = NATIVE.get(fid, 'native_%d' % fid)
            a = args[-argc:] if argc else []
            args = args[:-argc] if argc else args
            lines.append('%5d  %s(%s)' % (idx, fn, ', '.join(a)))
            R[0] = 'ret(%s)' % fn
        elif op == 8:
            try: R[opd] = 'var[%s]' % R[opd]
            except Exception: R[opd] = 'var[?]'
        elif op == 14:
            if opd == 0xffffffff: lines.append('%5d  var[%s] = %s' % (idx, R[0], R.get(1)))
            else: lines.append('%5d  var[%d] = %s' % (idx, opd, R[0]))
        elif op in BINOP: R[0] = '(%s %s %s)' % (R.get(1), BINOP[op], R[0])
        elif op in (63, 64, 65): lines.append('%5d  %s -> %d   [R0=%s]' % (idx, name, opd, R[0]))
        elif op == 27: lines.append('%5d  ==== START %d' % (idx, opd))
        elif op == 28: lines.append('%5d  ==== END' % idx)
        elif op == 62: lines.append('%5d  return %s' % (idx, R[0]))
        elif op == 44: pass
        elif op in (47,48,49,50,51,52,53,54,55,56): lines.append('%5d  var[%s] %s= %s' % (idx, opd if opd != 0xffffffff else R[0], name[3:], R[0] if opd != 0xffffffff else R.get(1)))
        elif op in (34, 35): lines.append('%5d  %s var[%s]' % (idx, name, opd))
    return lines, strs, props, props2

if __name__ == '__main__':
    raw = '--raw' in sys.argv
    lines, strs, props, props2 = render(sys.argv[1], raw)
    print('# props:', props)
    print('# props2:', props2)
    print('\n'.join(lines))
