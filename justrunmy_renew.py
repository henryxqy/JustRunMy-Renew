#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import time
import subprocess
import requests
import hashlib
import base64
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
        if r.status_code != 200:
            print(f"  ⚠️ Telegram 通知发送失败: {r.text}")
    except Exception as e:
        print(f"  ⚠️ Telegram 通知发送异常: {e}")

# ============================================================
#  页面注入脚本 (JS)
# ============================================================
_EXPAND_JS = """(function(){var ts=document.querySelector('input[name="cf-turnstile-response"]');if(!ts)return 'no-turnstile';var el=ts;for(var i=0;i<20;i++){el=el.parentElement;if(!el)break;var s=window.getComputedStyle(el);if(s.overflow==='hidden'||s.overflowX==='hidden'||s.overflowY==='hidden')el.style.overflow='visible';el.style.minWidth='max-content';}return 'done';})()"""
_EXISTS_JS = """(function(){return document.querySelector('input[name="cf-turnstile-response"]') !== null;})()"""
_SOLVED_JS = """(function(){var i=document.querySelector('input[name="cf-turnstile-response"]');return !!(i&&i.value&&i.value.length>20);})()"""
_COORDS_JS = """(function(){var iframes=document.querySelectorAll('iframe');for(var i=0;i<iframes.length;i++){var src=iframes[i].src||'';if(src.includes('cloudflare')||src.includes('turnstile')){var r=iframes[i].getBoundingClientRect();if(r.width>0&&r.height>0)return {cx:Math.round(r.x+30),cy:Math.round(r.y+r.height/2)};}}return null;})()"""
_WININFO_JS = """(function(){return {sx:window.screenX||0,sy:window.screenY||0,oh:window.outerHeight,ih:window.innerHeight};})()"""

# ============================================================
#  底层输入工具
# ============================================================
def js_fill_input(sb, selector: str, text: str):
    script = "var el = document.querySelector(arguments[0]); if(el) { el.value = arguments[1]; el.dispatchEvent(new Event('input', {bubbles:true})); el.dispatchEvent(new Event('change', {bubbles:true})); }"
    sb.execute_script(script, selector, text)

def _xdotool_click(x: int, y: int):
    try:
        subprocess.run(["xdotool", "mousemove", "--sync", str(x), str(y), "click", "1"], timeout=3, stderr=subprocess.DEVNULL)
    except:
        pass

# ============================================================
#  人机验证处理 (核心修复点)
# ============================================================
def handle_turnstile(sb) -> bool:
    print("🔍 正在处理 Cloudflare Turnstile 验证...")
    time.sleep(2)
    
    # 【修复】暴力移除可能遮挡验证框的 Cookie 弹窗
    sb.execute_script("""
        var selectors = ['.fc-consent-root', '#js-cookie-box', 'div[class*="cookie"]', 'button:contains("Accept")'];
        selectors.forEach(s => { try { var el = document.querySelector(s); if(el) el.remove(); } catch(e){} });
    """)

    if sb.execute_script(_SOLVED_JS):
        print("  ✅ 已自动通过")
        return True

    for attempt in range(6):
        # 【修复】使用官方原生的 GUI 绕过方法
        try:
            sb.uc_gui_handle_captcha()
            time.sleep(2)
        except:
            pass

        if sb.execute_script(_SOLVED_JS):
            print(f"  ✅ Turnstile 验证通过")
            return True

        try:
            coords = sb.execute_script(_COORDS_JS)
            if coords:
                wi = sb.execute_script(_WININFO_JS)
                ax = coords["cx"] + wi["sx"]
                ay = coords["cy"] + wi["sy"] + (wi["oh"] - wi["ih"])
                _xdotool_click(ax, ay)
        except:
            pass
        
        time.sleep(3)
        if sb.execute_script(_SOLVED_JS): return True

    return False

# ============================================================
#  账户登录模块 (修复按钮点击)
# ============================================================
def login(sb) -> bool:
    print(f"🌐 正在打开登录页面...")
    sb.uc_open_with_reconnect(LOGIN_URL, reconnect_time=5)
    time.sleep(5)

    # 尝试点掉 Cookie 按钮
    try:
        sb.click('button:contains("Accept All")', timeout=3)
    except:
        pass

    try:
        sb.wait_for_element('input[name="Email"]', timeout=15)
        print("📧 正在填写表单...")
        js_fill_input(sb, 'input[name="Email"]', EMAIL)
        js_fill_input(sb, 'input[name="Password"]', PASSWORD)
        
        if sb.execute_script(_EXISTS_JS):
            handle_turnstile(sb)
        
        sb.save_screenshot("debug_before_login.png")
        
        # 【修复】改用精准点击 ID_SignIn 按钮
        print("🖱️ 点击登录按钮...")
        try:
            sb.click('button:contains("SignIn")')
        except:
            sb.press_keys('input[name="Password"]', '\n')

        print("⏳ 等待页面跳转...")
        for _ in range(12):
            time.sleep(1)
            if "login" not in sb.get_current_url().lower():
                print("✅ 登录成功！")
                return True
    except Exception as e:
        print(f"❌ 登录出错: {e}")
        sb.save_screenshot("login_error.png")
    
    return False

# ============================================================
#  自动续期模块 (修复卡片定位)
# ============================================================
def renew(sb) -> bool:
    global DYNAMIC_APP_NAME
    print("\n🚀 开始自动续期流程")
    sb.open("https://justrunmy.app/panel")
    time.sleep(8)

    print("🖱️ 正在寻找应用卡片...")
    try:
        # 【修复】使用更稳健的管理页面链接定位卡片
        selector_card = 'a[href*="/panel/manage/"]'
        sb.wait_for_element(selector_card, timeout=20)
        
        DYNAMIC_APP_NAME = sb.get_text('h3').split('\n')[0].strip()
        print(f"🎯 发现应用: {DYNAMIC_APP_NAME}")
        
        sb.click(selector_card)
        time.sleep(5)
        
        print("🖱️ 点击 Reset Timer 按钮...")
        sb.click('button:contains("Reset")')
        time.sleep(3)

        if sb.execute_script(_EXISTS_JS):
            handle_turnstile(sb)

        print("🖱️ 点击 Just Reset 确认续期...")
        sb.click('button:contains("Just Reset")')
        time.sleep(10)

        sb.refresh()
        time.sleep(5)
        timer_text = sb.get_text('span.font-mono')
        print(f"⏱️ 剩余时间: {timer_text}")
        
        icon = "✅" if any(x in timer_text for x in ["2 days", "3 days", "2d", "3d"]) else "⚠️"
        send_tg_message(icon, "续期完成", timer_text)
        return True
    except Exception as e:
        print(f"❌ 续期失败: {e}")
        sb.save_screenshot("renew_failed.png")
        send_tg_message("❌", "续期失败", "未知")
        return False

# ============================================================
#  执行入口
# ============================================================
def main():
    print("=" * 50)
    print("   JustRunMy.app 增强修复版脚本")
    print("=" * 50)
    
    # GitHub Action 环境必须确保 uc=True
    with SB(uc=True, test=True, headless=False) as sb:
        if login(sb):
            renew(sb)
        else:
            print("❌ 登录失败，终止流程。")

if __name__ == "__main__":
    main()
