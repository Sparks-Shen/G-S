#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
G&S足迹回忆 · 商家添加工具
==========================
用法：在 Git Bash 中进入本文件夹，运行  python add_shop.py

按提示依次填写，脚本会自动完成：
  1) 店铺图片复制到 assets/img/
  2) 商家卡片数据写入 foodData.js / funData.js
  3) 填了经纬度的话，地图坐标写入 shopData.js
  4) 生成 places/ 下的商家详情页（含回忆语录）
  5) git pull --rebase → add → commit → push，自动更新到 GitHub

提示：填图片路径时，直接把图片文件从资源管理器拖进窗口即可。
"""

import os
import re
import shutil
import subprocess
import sys

BASE = os.path.dirname(os.path.abspath(__file__))

CATEGORIES = {
    "1": {"name": "美食", "data": "foodData.js", "page": "food.html", "emoji": "🍜"},
    "2": {"name": "娱乐", "data": "funData.js", "page": "fun.html", "emoji": "🎮"},
}

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stdin.reconfigure(encoding="utf-8")
except Exception:
    pass


def ask(prompt, default=""):
    """带默认值的输入；回车=默认值；Ctrl+D / 管道结束会抛 EOFError，由外层处理"""
    tip = f"（回车使用默认：{default}）" if default else ""
    val = input(f"{prompt}{tip}\n> ").strip()
    return val if val else default


def fix_path(p):
    """处理 Git Bash 里拖入的路径：/c/Users/... -> C:/Users/...，并去掉首尾引号"""
    p = p.strip().strip('"').strip("'")
    m = re.match(r"^/([a-zA-Z])/(.*)$", p)
    if m:
        p = f"{m.group(1).upper()}:/{m.group(2)}"
    return p


def sanitize(name):
    """店名 -> 合法文件名（去掉 Windows 非法字符和空格）"""
    s = re.sub(r'[\\/:*?"<>|]', "", name)
    s = s.replace(" ", "")
    return s or "shop"


def js_str(s):
    return s.replace("\\", "\\\\").replace('"', '\\"')


def html_esc(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def append_entry(data_file, entry_line):
    """在数据文件末尾的 ]; 之前插入一行"""
    path = os.path.join(BASE, data_file)
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()
    idx = content.rfind("];")
    if idx == -1:
        print(f"!! 在 {data_file} 里找不到结尾 ]; ，请检查文件格式")
        return False
    content = content[:idx] + entry_line + content[idx:]
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    return True


def run_git(args, ok_warn=""):
    r = subprocess.run(["git", "-C", BASE] + args,
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0:
        msg = (r.stderr or r.stdout).strip().splitlines()
        print("!! git " + " ".join(args) + " 失败：")
        for line in msg[-3:]:
            print("   " + line)
        if ok_warn:
            print("   " + ok_warn)
        return False
    return True


# 详情页模板：__XXX__ 会被替换成真实内容
DETAIL_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__NAME__</title>
<style>
*{margin:0;padding:0;box-sizing:border-box;font-family:Georgia,"Songti SC","SimSun",serif;}
html{height:100%;}
body{background:#f5f8fb;min-height:100%;-webkit-overflow-scrolling:touch;}

.back{
  display:inline-flex;align-items:center;gap:6px;
  margin:22px 0 0 28px;
  padding:8px 16px;
  background:#fff;
  border:1px solid #dbe7f2;
  border-radius:999px;
  font-size:13px;color:#5a7189;
  cursor:pointer;
  transition:all 0.2s ease;
}
.back:hover{border-color:#bcd6ec;color:#22354a;box-shadow:0 4px 10px rgba(60,110,160,0.10);}

.page{max-width:760px;margin:0 auto;padding:0 28px 50px;animation:fadeUp 0.5s ease;}
.hero{
  margin-top:20px;
  border-radius:16px;overflow:hidden;
  border:1px solid #e7eef5;
  box-shadow:0 8px 24px rgba(60,110,160,0.10);
  background:#eef2f6;
}
.hero img{width:100%;display:block;max-height:440px;object-fit:cover;}
.hero-fallback{
  aspect-ratio:16/9;width:100%;
  display:flex;align-items:center;justify-content:center;
  font-size:64px;color:#b6c0cc;
  background:linear-gradient(135deg,#eef4fa,#e2ecf6);
}

h1{margin-top:26px;font-size:26px;color:#1a2533;letter-spacing:1px;}
.addr{margin-top:10px;font-size:14px;color:#8a97a6;}

.memo{
  margin-top:30px;
  background:#fff;
  border:1px dashed #c9dbea;
  border-radius:14px;
  padding:24px;
  color:#5a7189;font-size:14px;line-height:1.8;
}
.memo .memo-title{color:#4a647e;font-weight:bold;margin-bottom:8px;letter-spacing:1px;}

@media(max-width:768px){
  .back{margin-left:16px;}
  .page{padding:0 16px 40px;}
  h1{font-size:22px;}
}

@keyframes fadeUp{
  from{opacity:0;transform:translateY(14px);}
  to{opacity:1;transform:none;}
}
</style>
</head>
<body>
<a class="back" onclick="go('__PAGE__')">← 返回__BACKTEXT__</a>

<div class="page">
  <div class="hero">
    __HERO__
  </div>
  <h1>__NAME__</h1>
  <p class="addr">📍 __ADDR__</p>

  <div class="memo">
    <div class="memo-title">我们的回忆</div>
    __MEMO__
  </div>
</div>

<script>
function go(page){
  if(parent.navigate){ parent.navigate(page); }
  else { location.href = page; }
}
</script>
</body>
</html>
"""


def add_shop(cat):
    c = CATEGORIES[cat]
    print(f"\n===== 添加{c['name']}商家 =====")

    # 先把远端的更新拉下来（比如你在网页上改过东西），避免后面冲突。
    # 必须放在写文件之前，否则 pull 会被未提交的改动挡住。
    run_git(["pull", "--rebase", "origin", "master"],
            ok_warn="（网络不通或远端没有新提交时会这样，不影响继续）")

    name = ask("店名（必填）")
    if not name:
        print("店名不能为空，本次取消")
        return
    addr = ask("地址（必填）")
    if not addr:
        print("地址不能为空，本次取消")
        return

    # 经纬度可选：填了才会出现在地图上
    lat_f = lng_f = None
    lat = ask("纬度（可选，填了才会上地图）")
    if lat:
        try:
            lat_f = float(lat)
            lng_f = float(ask("经度"))
        except ValueError:
            print("!! 经纬度必须是数字，本次不加入地图")

    quote = ask("回忆语录（可选）")

    # 图片：拖入窗口或手输路径
    img_file = None
    img_path = ask("店铺图片路径（可选，直接把图片文件拖进来）")
    if img_path:
        img_path = fix_path(img_path)
        if not os.path.isfile(img_path):
            print(f"!! 找不到图片文件：{img_path}（本次不带图片）")
        else:
            ext = os.path.splitext(img_path)[1].lower() or ".jpg"
            img_file = sanitize(name) + ext
            dest = os.path.join(BASE, "assets", "img", img_file)
            if os.path.abspath(img_path) != os.path.abspath(dest):
                overwrite = True
                if os.path.exists(dest):
                    overwrite = ask(f"assets/img/{img_file} 已存在，覆盖吗？(y/n)", "n").lower() == "y"
                if overwrite:
                    shutil.copyfile(img_path, dest)
                    print(f"  图片已复制到 assets/img/{img_file}")

    emoji = ask("卡片占位表情（可选）", c["emoji"])

    # 详情页重名检查
    slug = sanitize(name)
    detail_path = os.path.join(BASE, "places", slug + ".html")
    if os.path.exists(detail_path):
        if ask(f"places/{slug}.html 已存在，覆盖吗？(y/n)", "n").lower() != "y":
            print("已取消")
            return

    # 确认信息
    print("\n====== 确认信息 ======")
    print(f"分类：{c['name']}")
    print(f"店名：{name}")
    print(f"地址：{addr}")
    if lat_f is not None:
        print(f"经纬度：{lat_f}, {lng_f}")
    if quote:
        print(f"回忆语录：{quote}")
    if img_file:
        print(f"图片：assets/img/{img_file}")
    else:
        print(f"图片：无（卡片用 {emoji} 占位）")
    print("======================")
    if ask("确认写入并上传 GitHub？(y/n)", "y").lower() != "y":
        print("已取消")
        return

    # 1) 写入卡片数据（foodData.js / funData.js）
    img_field = f', img:"assets/img/{img_file}"' if img_file else ""
    entry = (f'  {{ name:"{js_str(name)}", address:"{js_str(addr)}"{img_field}, '
             f'emoji:"{js_str(emoji)}", link:"places/{slug}.html" }},\n')
    append_entry(c["data"], entry)

    # 2) 写入地图坐标（shopData.js，仅填了经纬度时）
    if lat_f is not None:
        mimg = f'assets/img/{img_file}' if img_file else ""
        mentry = (f'  {{ lng: {lng_f}, lat: {lat_f}, name:"{js_str(name)}", '
                  f'img:"{mimg}", link:"places/{slug}.html" }},\n')
        append_entry("shopData.js", mentry)

    # 3) 生成详情页
    hero = (f'<img src="../assets/img/{img_file}" alt="{html_esc(name)}">' if img_file
            else f'<div class="hero-fallback">{html_esc(emoji)}</div>')
    memo = html_esc(quote) if quote else "（在这里写下你们在这家店的回忆，还可以继续放照片……）"
    html = (DETAIL_TEMPLATE
            .replace("__NAME__", html_esc(name))
            .replace("__ADDR__", html_esc(addr))
            .replace("__PAGE__", c["page"])
            .replace("__BACKTEXT__", c["name"] + "信息")
            .replace("__HERO__", hero)
            .replace("__MEMO__", memo))
    with open(detail_path, "w", encoding="utf-8") as f:
        f.write(html)
    print("  详情页已生成 places/" + slug + ".html")

    # 4) 同步 GitHub
    print("\n同步 GitHub ...")
    run_git(["add", "-A"])
    r = subprocess.run(["git", "-C", BASE, "status", "--porcelain"],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.stdout.strip():
        run_git(["commit", "-m", f"add: 新增{c['name']}商家「{name}」"])
    if run_git(["push"]):
        print("✅ 已上传 GitHub！等 1~2 分钟刷新网站即可看到。")
    else:
        print("!! push 失败。可能是网络问题，稍后在文件夹里手动运行：git push")


def main():
    print("====================================")
    print("  G&S足迹回忆 · 商家添加工具")
    print("====================================")
    while True:
        try:
            print("\n [1] 添加美食商家")
            print(" [2] 添加娱乐商家")
            print(" [0] 退出")
            choice = input("请选择：").strip()
            if choice == "0":
                print("再见～")
                break
            if choice in CATEGORIES:
                add_shop(choice)
            else:
                print("请输入 1 / 2 / 0")
        except EOFError:
            print("\n再见～")
            break


if __name__ == "__main__":
    main()
