#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
G&S足迹回忆 · 商家添加工具
==========================
用法：在 Git Bash 中进入本文件夹，运行  python add_shop.py

按提示依次填写，脚本会自动完成：
  1) 店铺图片复制到 assets/img/
  2) 商家卡片数据写入 foodData.js / funData.js
  3) 填了经纬度的话，自动把高德/百度坐标转换成地图用的标准坐标，写入 shopData.js
  4) 生成 places/ 下的商家详情页（含回忆语录）
  5) git pull --rebase → add → commit → push，自动更新到 GitHub

提示：填图片路径时，直接把图片文件从资源管理器拖进窗口即可。
"""

import hashlib
import math
import os
import re
import shutil
import subprocess
import sys

BASE = os.path.dirname(os.path.abspath(__file__))

# ---------- 坐标转换（高德/百度 → 地图用的 WGS-84 标准坐标） ----------

_PI = math.pi
_A = 6378245.0
_EE = 0.00669342162296594323
_X_PI = _PI * 3000.0 / 180.0


def _out_of_china(lng, lat):
    """国外坐标不参与转换（偏移算法只对中国生效）"""
    return not (72.004 <= lng <= 137.8347 and 0.8293 <= lat <= 55.8271)


def _transform_lat(x, y):
    ret = -100.0 + 2.0*x + 3.0*y + 0.2*y*y + 0.1*x*y + 0.2*math.sqrt(abs(x))
    ret += (20.0*math.sin(6.0*x*_PI) + 20.0*math.sin(2.0*x*_PI)) * 2.0/3.0
    ret += (20.0*math.sin(y*_PI) + 40.0*math.sin(y/3.0*_PI)) * 2.0/3.0
    ret += (160.0*math.sin(y/12.0*_PI) + 320*math.sin(y*_PI/30.0)) * 2.0/3.0
    return ret


def _transform_lng(x, y):
    ret = 300.0 + x + 2.0*y + 0.1*x*x + 0.1*x*y + 0.1*math.sqrt(abs(x))
    ret += (20.0*math.sin(6.0*x*_PI) + 20.0*math.sin(2.0*x*_PI)) * 2.0/3.0
    ret += (20.0*math.sin(x*_PI) + 40.0*math.sin(x/3.0*_PI)) * 2.0/3.0
    ret += (150.0*math.sin(x/12.0*_PI) + 300.0*math.sin(x/30.0*_PI)) * 2.0/3.0
    return ret


def wgs84_to_gcj02(lng, lat):
    if _out_of_china(lng, lat):
        return lng, lat
    dlat = _transform_lat(lng - 105.0, lat - 35.0)
    dlng = _transform_lng(lng - 105.0, lat - 35.0)
    radlat = lat / 180.0 * _PI
    magic = math.sin(radlat)
    magic = 1 - _EE * magic * magic
    sqrtmagic = math.sqrt(magic)
    dlat = (dlat * 180.0) / ((_A * (1 - _EE)) / (magic * sqrtmagic) * _PI)
    dlng = (dlng * 180.0) / (_A / sqrtmagic * math.cos(radlat) * _PI)
    return lng + dlng, lat + dlat


def gcj02_to_wgs84(lng, lat):
    """高德/腾讯（GCJ-02）→ WGS-84，迭代逼近，误差小于 1 米"""
    if _out_of_china(lng, lat):
        return lng, lat
    wgs_lng, wgs_lat = lng, lat
    for _ in range(10):
        glng, glat = wgs84_to_gcj02(wgs_lng, wgs_lat)
        wgs_lng += lng - glng
        wgs_lat += lat - glat
    return wgs_lng, wgs_lat


def bd09_to_wgs84(lng, lat):
    """百度（BD-09）→ WGS-84"""
    x = lng - 0.0065
    y = lat - 0.006
    z = math.sqrt(x*x + y*y) - 0.00002*math.sin(y*_X_PI)
    theta = math.atan2(y, x) - 0.000003*math.cos(x*_X_PI)
    return gcj02_to_wgs84(z*math.cos(theta), z*math.sin(theta))

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


def _sha1(path):
    h = hashlib.sha1()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _smart_square_crop(path, white_th=235):
    """把图片裁成“内容最多、留白最少”的正方形区域。
    普通照片=保持居中不变；一侧有白墙/空白背景的照片会自动把空白侧裁掉。
    用积分图实现，几百 KB 的图片几秒钟内完成。"""
    try:
        from PIL import Image
        img = Image.open(path)
        w, h = img.size
        gray = img.convert("RGB").convert("L")
        g = gray.load()
        side = min(w, h)

        # 白色掩码 + 积分图：white_count(x0,y0,x1,y1) 为区域内近白像素个数
        W1 = w + 1
        integral = [0] * (W1 * (h + 1))
        for y in range(h):
            row = y * w
            iy0, iy1 = y * W1, (y + 1) * W1
            run = 0
            for x in range(w):
                run += 1 if g[x, y] >= white_th else 0
                integral[iy1 + x + 1] = integral[iy0 + x + 1] + run

        def white_count(x0, y0, x1, y1):
            return (integral[y1 * W1 + x1] - integral[y0 * W1 + x1]
                    - integral[y1 * W1 + x0] + integral[y0 * W1 + x0])

        best = None  # (非白占比, 边长, x0, y0)，占比相同取更大的窗口
        s = side
        while s >= max(80, int(side * 0.5)):
            step = max(8, s // 8)
            for y0 in range(0, h - s + 1, step):
                for x0 in range(0, w - s + 1, step):
                    wc = white_count(x0, y0, x0 + s, y0 + s)
                    score = (s * s - wc) / (s * s)
                    if best is None or (score, s) > (best[0], best[1]):
                        best = (score, s, x0, y0)
            s -= max(8, side // 10)

        if best is None:
            return False
        score, s, x0, y0 = best
        if s == side and x0 == 0 and y0 == 0 and score >= 0.999:
            return False  # 没有白边，原样保留
        img.load()
        img.crop((x0, y0, x0 + s, y0 + s)).save(path)
        print(f"  已自动裁出内容最集中的正方形区域：{w}×{h} → {s}×{s}（左上角 {x0},{y0}）")
        return True
    except Exception as e:
        print(f"  !! 自动裁剪失败（不影响使用）：{e}")
        return False


def js_str(s):
    return s.replace("\\", "\\\\").replace('"', '\\"')


def html_esc(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def append_entry(data_file, entry_line):
    """在数据文件末尾的 ]; 之前插入一行；上一条数据结尾缺逗号时自动补上"""
    path = os.path.join(BASE, data_file)
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()
    idx = content.rfind("];")
    if idx == -1:
        print(f"!! 在 {data_file} 里找不到结尾 ]; ，请检查文件格式")
        return False
    before = content[:idx]
    lines = before.splitlines()
    last = lines[-1].strip() if lines else ""
    # 上一条数据如果既不是逗号结尾、也不是注释或开括号，说明缺逗号，补一个
    if last and not last.endswith(",") and not last.startswith("//") \
            and not last.endswith("[") and not last.endswith("{"):
        before = before.rstrip() + ","
    content = before + "\n" + entry_line + content[idx:]
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
    # 反斜杠统一改成斜杠，避免网页显示/转义出问题
    addr = addr.replace("\\", "/")

    # 经纬度可选：填了才会出现在地图上
    # 高德/百度拾取器里复制的就是“经度,纬度”格式，直接整段粘贴即可
    lat_f = lng_f = None
    coords = ask("经纬度（可选，复制拾取器里的“经度,纬度”直接粘贴；填了才会上地图）")
    if coords:
        parts = re.split(r"[,，\s]+", coords)
        try:
            if len(parts) == 1:
                lat_f = float(parts[0])
                lng_f = float(ask("经度"))
            else:
                lng_f, lat_f = float(parts[0]), float(parts[1])
        except ValueError:
            print("!! 经纬度格式不对，本次不加入地图")
            lat_f = lng_f = None
        else:
            print("坐标来源？")
            print(" [1] 高德/腾讯地图（推荐，国内搜店名最准）")
            print(" [2] 百度地图")
            print(" [3] OpenStreetMap / 其他（已是标准坐标）")
            src = ask("请选择", "1")
            if src == "2":
                lng_f, lat_f = bd09_to_wgs84(lng_f, lat_f)
                print("  （已从百度坐标自动转换）")
            elif src == "3":
                print("  （标准坐标，直接使用）")
            else:
                lng_f, lat_f = gcj02_to_wgs84(lng_f, lat_f)
                print("  （已从高德坐标自动转换）")

    quote = ask("回忆语录（可选）")

    # 图片：先记住源路径，等确认通过后再复制，避免取消时留下多余文件
    # 如果图片已经在 assets/img/ 文件夹里，直接用它现有的文件名，不再复制第二份
    img_file = None
    img_src = None
    img_path = ask("店铺图片路径（可选，直接把图片文件拖进来）")
    if img_path:
        img_path = fix_path(img_path)
        if not os.path.isfile(img_path):
            print(f"!! 找不到图片文件：{img_path}（本次不带图片）")
        else:
            img_dir = os.path.normcase(os.path.abspath(os.path.join(BASE, "assets", "img")))
            src_abs = os.path.normcase(os.path.abspath(img_path))
            if src_abs.startswith(img_dir + os.sep):
                img_file = os.path.basename(img_path)
                print(f"  （图片已在 assets/img/ 里，直接使用 {img_file}）")
            else:
                ext = os.path.splitext(img_path)[1].lower() or ".jpg"
                img_file = sanitize(name) + ext
                img_src = img_path

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
        print(f"经纬度：经度 {lng_f:.6f} / 纬度 {lat_f:.6f}（写入地图用的标准坐标）")
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

    # 0) 复制图片并智能裁剪（确认之后才做）
    if img_file and img_src:
        dest = os.path.join(BASE, "assets", "img", img_file)
        if os.path.abspath(img_src) != os.path.abspath(dest):
            if os.path.exists(dest):
                same = (os.path.getsize(dest) == os.path.getsize(img_src)
                        and _sha1(dest) == _sha1(img_src))
                if same:
                    print(f"  assets/img/{img_file} 已存在相同图片，跳过复制")
                elif ask(f"assets/img/{img_file} 已存在且内容不同，覆盖吗？(y/n)", "n").lower() == "y":
                    shutil.copyfile(img_src, dest)
                    print(f"  图片已复制到 assets/img/{img_file}")
                    _smart_square_crop(dest)
            else:
                shutil.copyfile(img_src, dest)
                print(f"  图片已复制到 assets/img/{img_file}")
                _smart_square_crop(dest)
    elif img_file:
        # 图片已经在 assets/img/ 里：原地智能裁剪，去掉一侧的空白
        _smart_square_crop(os.path.join(BASE, "assets", "img", img_file))

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
