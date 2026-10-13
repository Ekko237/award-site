#!/usr/bin/env python3
"""定标卷校正 + 两个评审取平均，算出这一批能写进日志的分数。

用法：
  python3 calibrate.py --anchor anchor.json --reviews r1.json r2.json [--best best.json] [--save best.json]

anchor.json：定标卷的标准分（定下后不改），例如
  {"排版": 7, "留白": 7, "视觉层级": 6, "色彩": 7, "动效": 5, "微互动": 5, "响应式": 6, "原创性": 6, "好用程度": 7, "留存吸引力": 5}

r1.json / r2.json：每个评审输出末尾的 JSON 块，存成文件。评审不知道哪组是定标卷，所以两组叫「甲」「乙」：
  {"甲": {十项分}, "乙": {十项分}, "awwwards": {"设计": 6.8, "可用性": 7.0, "创意": 6.5, "内容": 6.9}}
（awwwards 一组可选：评审按 Awwwards 真实尺度给当前版本打的四项分，会单独算加权总分，不参与校正）
用 --anchor-key 说明哪组是定标卷（另一组就是当前版本），默认 甲。

校正：每项 当前分 + (标准分 − 这位评审给定标卷的分)，两位评审校正后取平均，保留一位小数。
每项校正量最多 ±1（--max-shift 可改），防止看定标卷的条件和当初不同时把分数带偏。
默认认为定标卷是静态截图：动效、微互动、好用程度、留存吸引力这四项截图里看不出来，不校正，直接取评审原分。
定标卷是能打开、能点的本地构建时加 --live-anchor，十项全部校正。
--best：上一个最好版本的校正分（同格式的十项字典），会逐项比较。
--save：这一批总分比 best 高时，把这一批的分数存成新的 best。
"""
import argparse, json, sys

DIMS = ["排版", "留白", "视觉层级", "色彩", "动效", "微互动", "响应式", "原创性", "好用程度", "留存吸引力"]

def load(p):
    return json.load(open(p, encoding='utf-8'))

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--anchor', required=True)
    ap.add_argument('--reviews', nargs='+', required=True)
    ap.add_argument('--best')
    ap.add_argument('--save')
    ap.add_argument('--anchor-key', default='甲')
    ap.add_argument('--max-shift', type=float, default=1.0)
    ap.add_argument('--live-anchor', action='store_true')
    a = ap.parse_args()
    std = load(a.anchor)
    missing = [d for d in DIMS if d not in std]
    if missing: sys.exit(f'定标卷缺这几项：{missing}')
    corrected, awards, raws = [], [], []
    for path in a.reviews:
        r = load(path)
        aw = r.pop('awwwards', None)
        if aw: awards.append(aw)
        keys = list(r.keys())
        if a.anchor_key not in r or len(keys) != 2: sys.exit(f'{path} 要正好两组分，其中一组叫 {a.anchor_key}')
        cur_key = [k for k in keys if k != a.anchor_key][0]
        r = {'anchor': r[a.anchor_key], 'current': r[cur_key]}
        for part in ('anchor', 'current'):
            lack = [d for d in DIMS if d not in r.get(part, {})]
            if lack: sys.exit(f'{path} 的 {part} 缺：{lack}')
        NOSTATIC = {'动效', '微互动', '好用程度', '留存吸引力'}
        def shift(d):
            if not a.live_anchor and d in NOSTATIC: return 0
            return max(-a.max_shift, min(a.max_shift, std[d] - r['anchor'][d]))
        corrected.append({d: r['current'][d] + shift(d) for d in DIMS})
        raws.append(r['current'])
    avg = {d: round(sum(c[d] for c in corrected) / len(corrected), 1) for d in DIMS}
    total = round(sum(avg.values()), 1)
    raw_avg = {d: round(sum(x[d] for x in raws) / len(raws), 1) for d in DIMS}
    moved = [f'{d} {raw_avg[d]}→{avg[d]}' for d in DIMS if abs(avg[d] - raw_avg[d]) >= 1]
    spread = {d: max(c[d] for c in corrected) - min(c[d] for c in corrected) for d in DIMS}
    print('校正后取平均（这一批写进日志的分）：')
    for d in DIMS:
        warn = '  ← 两位评审差 3 分以上，看一下理由' if spread[d] >= 3 else ''
        print(f'  {d:<6} {avg[d]:>4}{warn}')
    print(f'  总分 {total} / 100；低于 9 的：{[d for d in DIMS if avg[d] < 9] or "无"}')
    print(f'  校正前平均总分 {round(sum(raw_avg.values()),1)}' + ('；校正挪动 1 分以上的：' + '；'.join(moved) + '（检查看定标卷的条件是不是和当初一样）' if moved else ''))
    better = None
    if a.best:
        best = load(a.best)
        bt = round(sum(best[d] for d in DIMS), 1)
        print(f'\n和上一个最好版本比：{bt} → {total}（{total - bt:+.1f}）')
        down = [f'{d} {best[d]}→{avg[d]}' for d in DIMS if avg[d] < best[d]]
        if down: print('  变差的项：' + '；'.join(down))
        better = total > bt
        print('  结论：' + ('比最好版本好，可以当新的最好版本' if better else '没超过最好版本，按 SKILL.md 退回或只保留变好的部分'))
    if a.save and (better or not a.best):
        json.dump(avg, open(a.save, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
        print('已存为新的最好版本：', a.save)
    if awards:
        W = {'设计': .4, '可用性': .3, '创意': .2, '内容': .1}
        aw = {k: round(sum(x[k] for x in awards) / len(awards), 2) for k in W}
        tot = round(sum(aw[k] * W[k] for k in W), 2)
        print(f"\nAwwwards 四项（真实尺度，评审平均）：" + ' · '.join(f'{k}{aw[k]}' for k in W) + f'；加权总分 {tot}（Honorable Mention 6.5+，SOTD 加权常在 7.2–7.7）')
    print('\n日志用：校正后的评审分 ' + ' · '.join(f'{d}{avg[d]}' for d in DIMS) + f'（总分 {total}）')

if __name__ == '__main__':
    main()
