#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
一致性核对脚本（强制闸门）

用途：把"人记不住要回搜引用点"这类纪律，变成**可执行的检查**。
      每轮检查的末尾、以及每次变更单执行的收尾步骤，都必须跑本脚本；
      **退出码非 0 ⇒ 不得宣布"通过"**。

用法：  python 00-流程/check-consistency.py
退出码：0 = 全部通过；1 = 有失败项

背景（为什么要它）：
  2026-09-19 同一个错误发生两次 —— "在表格里加了一行，忘了改上面引言里的计数"
  （CR-003 的 D-7 → 修了；CR-006 加 AS-005 时又犯一次 → 第 11 轮查出 D-14）
  ⇒ 结论：**纪律要求拦不住，只有可执行的检查拦得住。**
"""

import io
import os
import re
import sys
import glob

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)

failures = []
checks = 0


def ok(msg):
    global checks
    checks += 1
    print(f"  [OK]   {msg}")


def bad(msg):
    global checks
    checks += 1
    failures.append(msg)
    print(f"  [FAIL] {msg}")


def rd(p):
    return io.open(p, encoding="utf-8").read() if os.path.exists(p) else ""


def check_layer(path):
    """对一个冻结物做机械核对"""
    print(f"\n=== 核对 {path} ===")
    s = rd(path)
    if not s:
        bad(f"{path} 不存在")
        return

    # ---- 1. 计数一致性：引言/声明里的数字 vs 表格实际行数 ----
    for m in re.finditer(r"以下 \*\*(\d+) 条\*\*[^\n]*已知的未知", s):
        declared = int(m.group(1))
        actual = len(re.findall(r"\| \*\*AS-\d+\*\* \|", s))
        (ok if declared == actual else bad)(
            f"§三 引言声明 {declared} 条 / 假设表实际 {actual} 行"
        )

    for m in re.finditer(r"不做\*\*（明确排除[^）]*?\*\*(\d+) 项\*\*）\s*\|([^\n]*)", s):
        declared = int(m.group(1))
        actual = len(re.findall(r"[①②③④⑤⑥⑦⑧⑨]", m.group(2)))
        (ok if declared == actual else bad)(
            f"§四 不做：声明 {declared} 项 / 实际列出 {actual} 项"
        )

    for m in re.finditer(r"预留\*\*（有接口[^）]*?\*\*(\d+) 项\*\*）\s*\|([^\n]*)", s):
        declared = int(m.group(1))
        actual = len(re.findall(r"[①②③④⑤⑥⑦⑧⑨]", m.group(2)))
        (ok if declared == actual else bad)(
            f"§四 预留：声明 {declared} 项 / 实际列出 {actual} 项"
        )

    for m in re.finditer(r"^\| \*\*§(\d) ", s, re.M):
        pass
    n_slot = len(re.findall(r"\| \*\*§[1-8] ", s))
    (ok if n_slot == 8 else bad)(f"槽位表行数 = {n_slot}（应为 8）")

    # ---- 2. 引用可达性：文件 ----
    paths = sorted(set(re.findall(r"`\.\./([^`]+?\.md)`", s)))
    base = os.path.dirname(path)
    miss = [p for p in paths if not os.path.exists(os.path.normpath(os.path.join(base, "..", p)))]
    (ok if not miss else bad)(f"文件路径引用 {len(paths)} 个，缺失 {len(miss)}" + (f"：{miss}" if miss else ""))

    # ---- 3. 引用可达性：编号 ----
    homes = {
        "B-": rd("30-待裁决/待裁决队列.md"),
        "AS-": rd("40-假设台账/假设台账.md"),
        "CR-": rd("50-变更单/变更单索引.md")
        + "".join(rd(f) for f in glob.glob("50-变更单/CR-*.md")),
        "BL-": rd("70-Backlog/backlog.md"),
    }
    for pref, src in homes.items():
        ids = sorted(set(re.findall(r"`(" + pref + r"\d+[a-z]?)`", s)))
        if not ids:
            continue
        dangling = [i for i in ids if i not in src]
        (ok if not dangling else bad)(
            f"{pref} 编号引用 {len(ids)} 个，不可达 {len(dangling)}" + (f"：{dangling}" if dangling else "")
        )

    # ---- 4. 空依据栏（3 列以上表格的最后一句为 — 或空）----
    empt = []
    for i, l in enumerate(s.splitlines(), 1):
        if not l.startswith("|"):
            continue
        c = [x.strip() for x in l.split("|")[1:-1]]
        if len(c) >= 3 and c[-1] in ("—", ""):
            empt.append((i, c[0][:16]))
    (ok if not empt else bad)(f"依据栏为空的行 {len(empt)} 处" + (f"：{empt}" if empt else ""))

    # ---- 5. 版本号：摘要与元信息必须一致 ----
    vs = re.findall(r"v1\.\d+", s)
    if vs:
        top = sorted(set(vs), key=lambda x: [int(n) for n in x.lstrip("v").split(".")])[-1]
        meta = re.search(r"\| 版本 \| \*\*(v1\.\d+)\*\*", s)
        if meta:
            (ok if meta.group(1) == top else bad)(
                f"版本号：最高出现 {top} / 元信息声明 {meta.group(1)}"
            )

    # ---- 6. 残留 AI 自拟（已裁定删除的内容不得复活）----
    for token, why in [("### A.2", "附录 A.2 已依 CR-005 删除"), ("后处理特效", "A.2 内容已删除")]:
        (bad if token in s else ok)(f"残留检查「{token}」" + (f" —— {why}" if token in s else "：无残留"))



def _norm(t):
    return re.sub(r"[*`\s]", "", t)


def check_cross_file():
    """跨文件【内容】一致性：不只查引用存在，还查两处写的是不是同一回事"""
    print("\n=== 跨文件内容一致性 ===")
    s1 = rd("10-基线/S-1-立项声明.md")
    lg = rd("40-假设台账/假设台账.md")

    def rows(txt, pref):
        d = {}
        for l in txt.splitlines():
            if l.startswith("| **" + pref):
                c = [x.strip() for x in l.split("|")[1:-1]]
                d[c[0].replace("**", "")] = c
        return d

    a, b = rows(s1, "AS-"), rows(lg, "AS-")
    if set(a) != set(b):
        bad(f"假设集合不一致：S-1 {sorted(a)} / 台账 {sorted(b)}")
    else:
        ok(f"假设集合一致（{len(a)} 条）")
    for k in sorted(set(a) & set(b)):
        if _norm(a[k][2]) != _norm(b[k][3]):
            bad(f"{k} 的「最晚验证时点」两处不一致：S-1「{a[k][2]}」/ 台账「{b[k][3]}」")
    ok("假设「最晚验证时点」逐条一致（已去粗体/空白比较）")

    # 预留清单项数（在两个文件里都应一致：S-1 §四 与 §8 槽位行）
    m4 = re.search(r"预留\*\*（有接口[^）]*?\*\*(\d+) 项\*\*）\s*\|([^\n]*)", s1)
    m8 = re.search(r"预留 (\d+) 项", s1)
    if m4 and m8:
        (ok if m4.group(1) == m8.group(1) else bad)(
            f"预留项数：§四 声明 {m4.group(1)} / §8 槽位行写 {m8.group(1)}"
        )

    # 决策记录必须能查到当前版本
    top = sorted(set(re.findall(r"v1\.\d", s1)), key=lambda x: int(x[3:]))[-1]
    dec = rd("60-决策记录/决策记录.md")
    (ok if top in dec else bad)(f"决策记录中可查到当前版本 {top}")


def main():
    layers = sorted(
        p for p in glob.glob("10-基线/*.md") if os.path.basename(p) != "README.md"
    )
    if not layers:
        print("未找到任何冻结物（10-基线/*.md）")
        return 1
    for p in layers:
        check_layer(p)
    check_cross_file()

    print(f"\n{'=' * 46}")
    print(f"共 {checks} 项检查，失败 {len(failures)} 项")
    if failures:
        print("\n失败明细：")
        for f in failures:
            print(f"  - {f}")
        print("\n⇒ 退出码 1：不得宣布「通过」")
        return 1
    print("⇒ 退出码 0：全部通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
