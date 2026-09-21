#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check-deps.py —— S1 依赖边表机械核对（方法见 20-设计/S1-#5依赖图方法-定稿.md）
验四项：① A 层无环 ② 无禁边 ③ 端点合法 ④ 出处非空
后续（S4 之后）：再加"源码 #include 交叉校验"（本骨架已留位）
"""
import io, os, re, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EDGES = os.path.join(ROOT, '20-设计', 'S1-依赖边表.txt')

MODULES = {
 'app/main_window','app/scene3d','app/dashboard','app/dialogs','app/replay',
 'core/program','core/execution','core/statemachine','core/device','core/concurrency',
 'core/alarm','core/stats','core/error','core/vision','core/mapping',
 'comm/interface','comm/modbus','data/store','data/log',
 'infra/build','infra/config','infra/eventbus','infra/lifecycle','infra/telemetry',
 'apps/virtual-device'}
EXTERNAL = {'E1','E2','E3','E4','E5','E6','E7','qt','vtk','main'}   # main = 装配点/组合根（不是模块）
NODES = MODULES | EXTERNAL

# 🔴 环豁免：每条必须带理由。空字典是默认值 —— 禁止为了让脚本变绿而往里加东西。
ALLOWED_CYCLES = {
 # 依法 §六：每条必须带理由，且经用户裁决
 ('core/concurrency','core/device'):
   '§五 硬约束①：core/concurrency 只投递、不持有（enqueue，非同步调用）⇒ 该 2-环是「每设备一线程 + 唯一事实源」的必然形状（2026-09-20 用户裁 A）。'
   '⚠️ 该豁免的安全性依赖「SPSC 无锁」这一机制，而本脚本**不校验机制** ⇒ 若实现层在环两侧加互斥锁，将真死锁而本脚本不报警。'
   '   ⇒ 机制验证挂 #6 运行时视图（2026-09-21 loop2-b CT-2）。',
}

def is_infra_like(n):  return n.startswith('infra/')
def is_comm(n):        return n.startswith('comm/')
def is_business(n):    return n.startswith(('app/','core/','data/')) or n == 'apps/virtual-device'

def forbidden(a, b, layer):
    """返回禁边理由，或 None。【按层区分】—— B 层 `core → app` 合法（事件就是向上通知）"""
    # 所有层都禁：infra 认识业务 / 虚拟下位机反向依赖
    if is_infra_like(a) and is_business(b):           return 'infra → 业务（§7.2.1②）'
    if a == 'apps/virtual-device' and b in MODULES and not b.startswith('comm/'):
        return '虚拟下位机 → 上位机模块（§14.2 E2）'
    if layer != 'A': return None   # ↓ 以下仅 A 层（静态依赖）适用
    if a.startswith('core/') and b.startswith('app/'):                return 'core → app（§17.1 主干③④⑤）'
    if is_comm(a) and is_business(b):                                 return 'comm → 业务（§17.1 主干④）'
    if a.startswith(('core/','comm/','data/')) and b in ('qt','vtk'): return '核心/通信/数据 → 第三方库（模块划分轮 32）'
    return None

def main():
    fails = []
    edges = []
    for ln, raw in enumerate(io.open(EDGES, encoding='utf-8').read().splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith('#'): continue
        m = re.match(r'^(\S+)\s*->\s*(\S+)\s*\|\s*([ABD])\s*\|\s*(\S+)\s*\|\s*(.+?)\s*$', line)
        if not m:
            fails.append('[① 格式] 第 %d 行不符合 `<A> -> <B> | <层> | <类型> | <出处>`：%s' % (ln, line[:60]))
            continue
        a, b, layer, kind, src = m.groups()
        edges.append((a, b, layer, kind, src, ln))

    # ③ 端点合法
    for a, b, layer, kind, src, ln in edges:
        for n in (a, b):
            if n not in NODES:
                fails.append('[③ 端点] 第 %d 行端点 `%s` 不在 %d 模块 ∪ {E1~E7,qt,vtk} 内' % (ln, n, len(MODULES)))
    # ④ 出处非空（正则已保证非空，这里查禁用行号）
    for a, b, layer, kind, src, ln in edges:
        if re.search(r'L\d{2,}|:\d+$|行\s*\d+', src):
            fails.append('[④ 出处] 第 %d 行「出处」含行号（全文禁行号）：%s' % (ln, src))

    # ② 禁边
    for a, b, layer, kind, src, ln in edges:
        why = forbidden(a, b, layer)
        if why: fails.append('[② 禁边] 第 %d 行 `%s -> %s` 违反：%s' % (ln, a, b, why))

    # ① A 层无环
    adj = {}
    for a, b, layer, kind, src, ln in edges:
        if layer != 'A': continue
        adj.setdefault(a, set()).add(b)
    WHITE, GRAY, BLACK = 0, 1, 2
    color = {n: WHITE for n in adj}
    cycles = []
    stack = []
    def dfs(u):
        color[u] = GRAY; stack.append(u)
        for v in adj.get(u, ()):
            if color.get(v, WHITE) == GRAY:
                i = stack.index(v)
                cycles.append(list(stack[i:]) + [v])
            elif color.get(v, WHITE) == WHITE:
                dfs(v)
        stack.pop(); color[u] = BLACK
    for n in list(adj):
        if color.get(n, WHITE) == WHITE: dfs(n)
    # 去重（同一环的旋转等价）
    uniq = []
    for c in cycles:
        key = frozenset(c)
        if key not in [frozenset(x) for x in uniq]: uniq.append(c)
    truth = []
    for c in uniq:
        key = tuple(sorted(set(c)))
        if key in ALLOWED_CYCLES: continue
        truth.append(c)
    for c in truth:
        fails.append('[① 环] A 层存在环：' + ' → '.join(c))

    nA = sum(1 for e in edges if e[2] == 'A')
    nB = sum(1 for e in edges if e[2] == 'B')
    nD = sum(1 for e in edges if e[2] == 'D')
    print('=' * 62)
    print('依赖边表核对：共 %d 条边（A 层 %d · B 层 %d · D 层 %d）｜ 节点 %d 个'
          % (len(edges), nA, nB, nD, len({x for a, b, *_ in [(e[0], e[1]) for e in edges] for x in (a, b)})))
    print('-' * 62)
    if fails:
        for f in fails: print('✗ ' + f)
        print('-' * 62)
        print('失败 %d 项 ⇒ 退出码 1' % len(fails)); return 1
    print('✅ ① A 层无环  ② 无禁边  ③ 端点合法  ④ 出处无行号')
    print('⇒ 退出码 0'); return 0

if __name__ == '__main__':
    sys.exit(main())
