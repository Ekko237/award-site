# award-site

一个给 Claude Code / Codex 用的技能：把网页产品做到「获奖网站级」的体验。

功能做全只是及格线；同一份需求，大家做出来的功能差不多，拉开差距靠视觉、交互、动效和流畅度。这个技能把一套从真实项目里磨出来的打磨流程写成了规则：

- **两种模式**：从零做新网站，或者改版已有网站。
- **先看标杆**：真的去 Awwwards / Webby / FWA 看一批同类获奖站，记下可借的手法。
- **按批循环**：评审一次给出完整问题清单，开发一口气改完，再评。全程在本地做，弄好再发布。
- **靠谱的评审**：统一的尺子（10 分 = Awwwards 获奖）、定标卷校正、两个评审取平均、和上一个最好版本并排比。
- **用户把关**：定期把前后对比给人看，防止 AI 评审集体看走眼。
- **刹车写全**：截止时间、卡住、没进展、来回摆各有处理办法。

踩过的坑都记在 `references/lessons.md`。

## 安装

```bash
bash install.sh          # 自动装到 ~/.claude/skills 和/或 ~/.codex/skills
bash install.sh claude   # 只装 Claude Code
bash install.sh codex    # 只装 Codex
```

装好后，说「把这个网站打磨到获奖水平」「改版一下」，或者直接用 `/award-site`。

## 可选搭配

- 一个前端设计规则技能（比如 design-taste-frontend）：装了会按它的设计规则来。
- 一个生图工具：画面优先用生成图片。

MIT License
