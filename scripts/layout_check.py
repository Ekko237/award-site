#!/usr/bin/env python3
"""award-site 布局体检：多宽度截图 + 程序检查，输出一份 JSON 报告。

用法：
  python3 layout_check.py <url> [<url> ...] [--widths 375,768,1024,1280,1440] [--out ./check-out]
  python3 layout_check.py http://localhost:5173/ http://localhost:5173/dashboard --widths 1280,1440,1920

查的东西（每个 url × 每档宽度）：
  - 整页截图（用浏览器视口模拟手机宽度，375 也准）；加 --slices N 再按一屏一张截前 N 屏，给评审和定标卷用
  - 横向溢出：页面比视口宽
  - 元素超出视口右边（跑马灯、轮播这类被父容器裁掉的不算）
  - 描边、阴影、outline 被祖先的 overflow 裁掉
  - 可点区域小于 44×44（只在手机宽度查，电脑上用鼠标）
  - 文字被截断（scrollWidth > clientWidth 且 overflow 不可见）
  - 控制台报错、页面报错、加载失败的页面资源（统计和广告请求失败不算）、没加载出来的图片
  - 页面文字里出现了不许出现的字符串（--forbid，比如破折号、占位文字）
只看初始状态。操作后的状态（弹窗、选中、每种业务状态）要先用自己的脚本把页面点到那个状态，
再对那个页面调用 check_page()。
"""
import argparse, json, os, re, sys
from playwright.sync_api import sync_playwright

JS = r"""
() => {
  const vw = document.documentElement.clientWidth;
  const out = {overflowX: document.documentElement.scrollWidth > vw + 1,
               scrollWidth: document.documentElement.scrollWidth, viewport: vw,
               offscreen: [], clipped: [], smallTargets: [], truncated: [], brokenImages: []};
  const label = el => {
    const t = (el.innerText || el.getAttribute('aria-label') || el.alt || '').trim().slice(0, 40);
    return el.tagName.toLowerCase() + (el.id ? '#' + el.id : '') +
      (el.className && typeof el.className === 'string' ? '.' + el.className.trim().split(/\s+/).slice(0,2).join('.') : '') +
      (t ? ' "' + t + '"' : '');
  };
  const visible = el => { const r = el.getBoundingClientRect(); const s = getComputedStyle(el);
    return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none' && +s.opacity > 0; };
  const all = [...document.querySelectorAll('body *')].filter(visible);
  for (const el of all) {
    const r = el.getBoundingClientRect();
    if (r.right > vw + 1 && getComputedStyle(el).position !== 'fixed') {
      // 跑马灯、轮播这类被祖先 overflow 裁掉的内容是有意藏在外面的，不算
      let clippedByAncestor = false, q = el.parentElement;
      while (q && q !== document.body) {
        const qs = getComputedStyle(q);
        if (qs.overflowX !== 'visible' || qs.overflow !== 'visible') { clippedByAncestor = true; break; }
        q = q.parentElement;
      }
      if (!clippedByAncestor) out.offscreen.push({el: label(el), right: Math.round(r.right)});
    }
    const s = getComputedStyle(el);
    // 描边、阴影外框
    let pad = 0;
    const sh = s.boxShadow; if (sh && sh !== 'none') {
      const nums = sh.match(/-?\d+(\.\d+)?px/g) || []; pad = Math.max(pad, nums.reduce((a, n) => a + Math.abs(parseFloat(n)), 0) / 2);
    }
    if (s.outlineStyle !== 'none') pad = Math.max(pad, parseFloat(s.outlineWidth) + parseFloat(s.outlineOffset || 0));
    if (pad > 0 || parseFloat(s.borderTopWidth) > 0) {
      let p = el.parentElement;
      while (p && p !== document.body) {
        const ps = getComputedStyle(p);
        if (ps.overflow !== 'visible' || ps.overflowX !== 'visible' || ps.overflowY !== 'visible') {
          const pr = p.getBoundingClientRect();
          const o = {l: r.left - pad, t: r.top - pad, r: r.right + pad, b: r.bottom + pad};
          if (o.l < pr.left - 0.5 || o.t < pr.top - 0.5 || o.r > pr.right + 0.5 || o.b > pr.bottom + 0.5) {
            // 滚动容器里的内容本来就会超出，只记离边很近、看起来像被切了一刀的
            const inScroller = /auto|scroll/.test(ps.overflow + ps.overflowX + ps.overflowY);
            if (!inScroller || pad > 0) out.clipped.push({el: label(el), by: label(p)});
          }
          break;
        }
        p = p.parentElement;
      }
    }
    const clickable = el.matches('a[href],button,input:not([type=hidden]),select,textarea,[role=button],[onclick],[tabindex]:not([tabindex="-1"])');
    if (vw < 768 && clickable && (r.width < 44 || r.height < 44)) out.smallTargets.push({el: label(el), w: Math.round(r.width), h: Math.round(r.height)});
    if ((s.overflow !== 'visible' || s.textOverflow === 'ellipsis') && el.scrollWidth > el.clientWidth + 1 && el.children.length === 0 && el.innerText)
      out.truncated.push({el: label(el)});
  }
  for (const img of document.images) if (img.complete && img.naturalWidth === 0 && visible(img)) out.brokenImages.push(img.currentSrc || img.src);
  for (const k of ['offscreen','clipped','smallTargets','truncated']) out[k] = out[k].slice(0, 40);
  return out;
}
"""

ANALYTICS = re.compile(r'google-analytics|googletagmanager|/g/collect|/ga/|doubleclick|segment\.io|hotjar|plausible|clarity\.ms|facebook\.net', re.I)

def check_page(page):
    return page.evaluate(JS)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('urls', nargs='+')
    ap.add_argument('--widths', default='375,768,1024,1280,1440')
    ap.add_argument('--height', type=int, default=900)
    ap.add_argument('--out', default='check-out')
    ap.add_argument('--slices', type=int, default=0, help='另外按一屏一张截前 N 屏（给评审看；整页长图交给评审会被缩得看不清）')
    ap.add_argument('--forbid', default='', help='页面文字里不许出现的字符串，逗号分隔，比如 "—,Lorem,TODO"')
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    report = []
    with sync_playwright() as p:
        b = p.chromium.launch()
        for w in [int(x) for x in a.widths.split(',')]:
            mobile = w < 768
            ctx = b.new_context(viewport={'width': w, 'height': a.height}, device_scale_factor=2 if mobile else 1,
                                is_mobile=mobile, has_touch=mobile)
            page = ctx.new_page()
            errors, failed = [], []
            page.on('console', lambda m: errors.append(m.text) if m.type == 'error' else None)
            page.on('pageerror', lambda e: errors.append(str(e)))
            def on_failed(r):
                if r.resource_type in ('document', 'script', 'stylesheet', 'image', 'font', 'media') and not ANALYTICS.search(r.url):
                    failed.append(r.url)
            page.on('requestfailed', on_failed)
            for url in a.urls:
                errors.clear(); failed.clear()
                page.goto(url, wait_until='networkidle')
                page.wait_for_timeout(300)
                slug = re.sub(r'[^a-zA-Z0-9]+', '-', url.split('://')[-1]).strip('-')[:60] or 'page'
                shot = os.path.join(a.out, f'{slug}-{w}.png')
                page.screenshot(path=shot, full_page=True)
                if a.slices:
                    total_h = page.evaluate('document.documentElement.scrollHeight')
                    for i in range(min(a.slices, -(-total_h // a.height))):
                        page.evaluate(f'window.scrollTo(0, {i * a.height})')
                        page.wait_for_timeout(250)
                        page.screenshot(path=os.path.join(a.out, f'{slug}-{w}-screen{i+1:02d}.png'))
                    page.evaluate('window.scrollTo(0, 0)')
                r = check_page(page)
                text = page.inner_text('body')
                r['forbidden'] = [x for x in a.forbid.split(',') if x and x in text]
                r.update(url=url, width=w, screenshot=shot, consoleErrors=errors[:20], failedRequests=failed[:20])
                r['pass'] = not (r['overflowX'] or r['offscreen'] or r['clipped'] or r['truncated'] or r['brokenImages'] or r['forbidden'] or errors or failed)
                report.append(r)
            ctx.close()
        b.close()
    path = os.path.join(a.out, 'report.json')
    json.dump(report, open(path, 'w'), ensure_ascii=False, indent=1)
    for r in report:
        flags = [k for k in ('overflowX','offscreen','clipped','smallTargets','truncated','brokenImages','forbidden','consoleErrors','failedRequests') if r.get(k)]
        print(f"{'PASS' if r['pass'] else 'FAIL'}  {r['width']:>5}  {r['url']}  {' '.join(flags)}")
    print('report:', path)

if __name__ == '__main__':
    main()
