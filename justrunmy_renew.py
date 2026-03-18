#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import time
import subprocess
import requests
from seleniumbase import SB

LOGIN_URL = "https://justrunmy.app/id/Account/Login"
DOMAIN    = "justrunmy.app"

# ============================================================
#  环境变量与全局变量
# ============================================================
EMAIL        = os.environ.get("JUSTRUNMY_EMAIL")
PASSWORD     = os.environ.get("JUSTRUNMY_PASSWORD")
TG_BOT_TOKEN = os.environ.get("TG_BOT_TOKEN")
TG_CHAT_ID   = os.environ.get("TG_CHAT_ID")

if not EMAIL or not PASSWORD:
    print("❌ 致命错误：未找到 JUSTRUNMY_EMAIL 或 JUSTRUNMY_PASSWORD 环境变量！")
    sys.exit(1)

DYNAMIC_APP_NAME = "未知应用"

# ============================================================
#  Telegram 推送模块
# ============================================================
def send_tg_message(status_icon, status_text, time_left):
    if not TG_BOT_TOKEN or not TG_CHAT_ID:
        print("ℹ️ 未配置 TG_BOT_TOKEN 或 TG_CHAT_ID，跳过 Telegram 推送。")
        return

    local_time = time.gmtime(time.time() + 8 * 3600)
    current_time_str = time.strftime("%Y-%m-%d %H:%M:%S", local_time)

    text = (
        f"🖥 {DYNAMIC_APP_NAME}\n"
        f"{status_icon} {status_text}\n"
        f"⏱️ 剩余: {time_left}\n"
        f"时间: {current_time_str}"
    )

    url = f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TG_CHAT_ID, "text": text}
    
    try:
        r = requests.post(url, json=payload, timeout=10)
        if r.status_code == 200:
            print("  📩 Telegram 通知发送成功！")
        else:
            print(f"  ⚠️ Telegram 通知发送失败: {r.text}")
    except Exception as e:
        print(f"  ⚠️ Telegram 通知发送异常: {e}")

# ============================================================
#  页面注入脚本 (Turnstile 处理用)
# ============================================================
_EXPAND_JS = """(function(){var ts=document.querySelector('input[name="cf-turnstile-response"]');if(!ts)return 'no-turnstile';var el=ts;for(var i=0;i<20;i++){el=el.parentElement;if(!el)break;var s=window.getComputedStyle(el);if(s.overflow==='hidden'||s.overflowX==='hidden'||s.overflowY==='hidden')el.style.overflow='visible';el.style.minWidth='max-content';}document.querySelectorAll('iframe').forEach(function(f){if(f.src&&f.src.includes('challenges.cloudflare.com')){f.style.width='300px';f.style.height='65px';f.style.minWidth='300px';f.style.visibility='visible';f.style.opacity='1';}});return 'done';})()"""
_EXISTS_JS = """(function(){return document.querySelector('input[name="cf-turnstile-response"]')!==null;})()"""
_SOLVED_JS = """(function(){var i=document.querySelector('input[name="cf-turnstile-response"]');return !!(i&&i.value&&i.value.length>20);})()"""
_COORDS_JS = """(function(){var iframes=document.querySelectorAll('iframe');for(var i=0;i<iframes.length;i++){var src=iframes[i].src||'';if(src.includes('cloudflare')||src.includes('turnstile')||src.includes('challenges')){var r=iframes[i].getBoundingClientRect();if(r.width>0&&r.height>0)return {cx:Math.round(r.x+30),cy:Math.round(r.y+r.height/2)};}}var inp=document.querySelector('input[name="cf-turnstile-response"]');if(inp){var p=inp.parentElement;for(var j=0;j<5;j++){if(!p)break;var r=p.getBoundingClientRect();if(r.width>100&&r.height>30)return {cx:Math.round(r.x+30),cy:Math.round(r.y+r.height/2)};p=p.parentElement;}}return null;})()"""
_WININFO_JS = """(function(){return {sx:window.screenX||0,sy:window.screenY||0,oh:window.outerHeight,ih:window.innerHeight};})()"""

# ============================================================
#  底层输入与点击工具
# ============================================================
def js_fill_input(sb, selector: str, text: str):
    safe_text = text.replace('\\', '\\\\').replace('"', '\\"')
    sb.execute_script(f'document.querySelector("{selector}").value = "{safe_text}";')
    sb.execute_script(f'document.querySelector("{selector}").dispatchEvent(new Event("input", {{bubbles:true}}));')

def _xdotool_click(x: int, y: int):
    try:
        subprocess.run(["xdotool", "mousemove", "--sync", str(x), str(y), "click", "1"], timeout=3)
    except:
        pass

def handle_turnstile(sb) -> bool:
    print("🔍 处理 Cloudflare Turnstile 验证...")
    time.sleep(2)
    if sb.execute_script(_SOLVED_JS): return True

    for attempt in range(6):
        try: sb.execute_script(_EXPAND_JS)
        except: pass
        coords = sb.execute_script(_COORDS_JS)
        if coords:
            wi = sb.execute_script(_WININFO_JS)
            ax = coords["cx"] + wi["sx"]
            ay = coords["cy"] + wi["sy"] + (wi["oh"] - wi["ih"])
            _xdotool_click(ax, ay)
        
        for _ in range(8):
            time.sleep(1)
            if sb.execute_script(_SOLVED_JS):
                print(f"  ✅ Turnstile 通过")
                return True
    return False

# ============================================================
#  核心逻辑：登录与续期
# ============================================================
def login(sb) -> bool:
    print(f"🌐 打开登录页面: {LOGIN_URL}")
    sb.uc_open_with_reconnect(LOGIN_URL, reconnect_time=5)
    time.sleep(5)
    
    try:
        sb.wait_for_element('input[name="Email"]', timeout=15)
        js_fill_input(sb, 'input[name="Email"]', EMAIL)
        js_fill_input(sb, 'input[name="Password"]', PASSWORD)
        
        if sb.execute_script(_EXISTS_JS):
            handle_turnstile(sb)
        
        sb.press_keys('input[name="Password"]', '\n')
        time.sleep(10)
        
        if sb.get_current_url().lower() != LOGIN_URL.lower():
            print("✅ 登录成功！")
            return True
    except Exception as e:
        print(f"❌ 登录过程出错: {e}")
    return False

def renew(sb) -> bool:
    global DYNAMIC_APP_NAME
    print("\n🚀 开始自动续期流程")
    sb.open("https://justrunmy.app/panel")
    time.sleep(5)

    try:
        # 寻找应用卡片链接
        selector_card = 'a[href*="/panel/manage/"]'
        sb.wait_for_element(selector_card, timeout=20)
        
        # 抓取名称并进入
        DYNAMIC_APP_NAME = sb.get_text('h3').split('\n')[0].strip()
        print(f"🎯 发现应用: {DYNAMIC_APP_NAME}")
        sb.click(selector_card)
        time.sleep(5)

        # 点击 Reset Timer
        sb.click('button:contains("Reset")')
        time.sleep(3)

        # 处理弹窗内的 CF
        if sb.execute_script(_EXISTS_JS):
            handle_turnstile(sb)

        # 最终确认
        sb.click('button:contains("Just Reset")')
        print("⏳ 提交续期中...")
        time.sleep(8)

        # 验证结果
        sb.refresh()
        time.sleep(5)
        timer_text = sb.get_text('span.font-mono')
        print(f"⏱️ 剩余时间: {timer_text}")
        
        if "2 days" in timer_text or "3 days" in timer_text or "2d" in timer_text:
            print("✅ 续期圆满完成！")
            send_tg_message("✅", "续期完成", timer_text)
            return True
        else:
            send_tg_message("⚠️", "续期异常(请检查)", timer_text)
    except Exception as e:
        print(f"❌ 续期失败: {e}")
        send_tg_message("❌", "续期失败", "错误")
    return False

def main():
    sb_kwargs = {"uc": True, "test": True, "headless": False} # Action环境建议headless=True
    with SB(**sb_kwargs) as sb:
        if login(sb):
            renew(sb)

if __name__ == "__main__":
    main()
