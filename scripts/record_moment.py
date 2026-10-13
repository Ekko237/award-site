#!/usr/bin/env python3
"""录一个招牌时刻：录屏 + 连续截帧 + 量出页面上跑过的动效时长和缓动。给评审打动效、微互动用。

用法：
  python3 record_moment.py <url> --steps steps.json [--width 1440 --height 900] [--out ./moment-out] [--fps 10]

steps.json 是一串操作，按顺序执行，例如：
  [{"wait": 500},
   {"click": "text=开始测试"},
   {"wait": 1500},
   {"hover": "#fix-btn"},
   {"click": "#fix-btn"},
   {"wait": 1200}]
支持的操作：click、hover、fill（{"fill": "选择器", "value": "文字"}）、press（{"press": "Enter"}）、wait（毫秒）、scroll（像素）。

输出：
  video.webm         整段录屏
  frames/0001.png…   每秒 fps 张截图，看动画过程中有没有跳、断、闪
  motion.json        按画面变化估的每一步动效持续多久（JS、WebGL 动画也算得到，粗估，误差约 ±200ms）
  animations.json    每次操作之后页面上出现过的 CSS 动画、过渡和 Web Animations：哪个元素、时长、缓动、延迟
                     （用 requestAnimationFrame 手写的 JS 动画量不到，这类看录屏和截帧）
"""
import argparse, json, os, time
from playwright.sync_api import sync_playwright

COLLECT = r"""
() => document.getAnimations().map(a => {
  const t = a.effect && a.effect.getTiming ? a.effect.getTiming() : {};
  const el = a.effect && a.effect.target;
  const name = el ? (el.tagName.toLowerCase() + (el.id ? '#' + el.id : '') +
    (typeof el.className === 'string' && el.className ? '.' + el.className.trim().split(/\s+/)[0] : '')) : '?';
  return {el: name, type: a.constructor.name, name: a.animationName || a.transitionProperty || '',
          duration: t.duration, delay: t.delay, iterations: t.iterations,
          easing: (a.constructor.name === 'CSSAnimation' && el) ? getComputedStyle(el).animationTimingFunction : t.easing};
})
"""

def estimate_motion(timeline, min_frac=0.0005):
    """相邻两帧缩小后数一数有多少像素变了（灰度差 > 6），变化的像素超过万分之五算「还在动」。每一步操作后画面持续变化多久，就是估出来的动效时长。
    精度受截图速度限制，实测约 ±200ms（已知 180ms 的悬停估成 350ms，700ms 的弹出估成 550ms）。用来发现超过 1 秒、拖沓挡路的动效，不用来抠一两百毫秒；精确时长看 animations.json。"""
    try:
        from PIL import Image, ImageChops, ImageStat
    except ImportError:
        return []
    out, prev = {}, None
    for t, step, fp in timeline:
        im = Image.open(fp).convert('L').resize((400, 250))
        if prev is not None and step > 0:
            d = ImageChops.difference(im, prev[1]).point(lambda v: 255 if v > 6 else 0)
            frac = ImageStat.Stat(d).mean[0] / 255
            rec = out.setdefault(step, {'start': prev[0], 'last_moving': None})
            if frac > min_frac: rec['last_moving'] = t
        prev = (t, im)
    res = []
    for step, rec in sorted(out.items()):
        ms = 0 if rec['last_moving'] is None else round((rec['last_moving'] - rec['start']) * 1000)
        res.append({'step': step, 'moving_ms': ms})
    return res

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('url')
    ap.add_argument('--steps', required=True)
    ap.add_argument('--width', type=int, default=1440)
    ap.add_argument('--height', type=int, default=900)
    ap.add_argument('--out', default='moment-out')
    ap.add_argument('--fps', type=int, default=10)
    a = ap.parse_args()
    steps = json.load(open(a.steps, encoding='utf-8'))
    os.makedirs(os.path.join(a.out, 'frames'), exist_ok=True)
    seen, frame, skipped = [], [0], [0]
    timeline, cur_step, t0 = [], [0], time.time()  # (秒, 第几步, 帧文件)
    with sync_playwright() as p:
        b = p.chromium.launch()
        ctx = b.new_context(viewport={'width': a.width, 'height': a.height},
                            record_video_dir=a.out, record_video_size={'width': a.width, 'height': a.height})
        page = ctx.new_page()
        try:
            page.goto(a.url, wait_until='networkidle', timeout=20000)
        except Exception:
            page.wait_for_timeout(1500)  # 有些站一直有请求，等不到空闲，就按已加载的继续

        def snap_for(ms):
            end = time.time() + ms / 1000
            while True:
                try:
                    fp = os.path.join(a.out, 'frames', f'{frame[0] + 1:04d}.png')
                    page.screenshot(path=fp, timeout=4000)
                    frame[0] += 1
                    timeline.append((time.time() - t0, cur_step[0], fp))
                except Exception:
                    skipped[0] += 1  # 很重的 WebGL 页面截图可能超时，跳过这一帧
                try:
                    for x in page.evaluate(COLLECT):
                        if x not in seen: seen.append(x)
                except Exception:
                    pass
                if time.time() >= end: break
                time.sleep(max(0, 1 / a.fps - 0.02))

        failed_steps = []
        try:
            snap_for(300)
            page.mouse.move(a.width / 2, a.height / 2)
            for i, st in enumerate(steps, 1):
                cur_step[0] = i
                try:
                    if 'click' in st: page.locator(st['click']).locator('visible=true').first.click(timeout=5000)
                    elif 'hover' in st: page.locator(st['hover']).locator('visible=true').first.hover(timeout=5000)
                    elif 'fill' in st: page.locator(st['fill']).first.fill(st.get('value', ''), timeout=5000)
                    elif 'press' in st: page.keyboard.press(st['press'])
                    elif 'scroll' in st: page.mouse.wheel(0, st['scroll'])
                except Exception as e:
                    # 一步失败不要毁掉整段录制：记下来，接着录
                    failed_steps.append({'step': i, 'action': st, 'error': str(e).splitlines()[0]})
                snap_for(st.get('wait', 600))
        finally:
            video = page.video.path()
            ctx.close(); b.close()
    final = os.path.join(a.out, 'video.webm')
    if os.path.exists(video): os.replace(video, final)
    json.dump(seen, open(os.path.join(a.out, 'animations.json'), 'w'), ensure_ascii=False, indent=1)
    if failed_steps:
        print('没执行成功的步骤（换个选择器再录）：')
        for f in failed_steps: print('  ', f)
    long_ = [x for x in seen if isinstance(x.get('duration'), (int, float)) and x['duration'] > 500 and x.get('iterations') != float('inf')]
    motion = estimate_motion(timeline)
    for m in motion: m['action'] = steps[m['step'] - 1] if m['step'] <= len(steps) else {}
    json.dump(motion, open(os.path.join(a.out, 'motion.json'), 'w'), ensure_ascii=False, indent=1)
    print('按画面变化估的动效时长（JS、WebGL 动画也算得到）：')
    for m in motion:
        w = m['action'].get('wait', 600) if isinstance(m['action'], dict) else 600
        note = '（整段都在变：多半是循环动画、视频或滚动驱动的画面，不是一次性的过渡，看录屏判断）' if m['moving_ms'] >= w - 250 else ''
        print(f"  第 {m['step']} 步 {m['action']}：画面变化持续约 {m['moving_ms']} ms{note}")
    print(f'frames: {frame[0]}（超时跳过 {skipped[0]}）  animations: {len(seen)}  longer than 500ms: {len(long_)}')
    for x in long_[:10]: print('  ', x)
    print('video:', final)

if __name__ == '__main__':
    main()
