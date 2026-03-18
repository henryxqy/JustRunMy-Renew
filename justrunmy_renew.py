#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import time
import subprocess
import requests
from seleniumbase import SB

# ============================================================
#  配置与环境变量
# ============================================================
LOGIN_URL = "https://justrunmy.app/id/Account/Login"
EMAIL        = os.environ.get("JUSTRUNMY_EMAIL")
PASSWORD     = os.environ.get("JUSTRUNMY_PASSWORD")
TG_BOT_TOKEN = os.environ.get("TG_BOT_TOKEN")
TG_CHAT_ID   = os.environ.get("TG_CHAT_ID")

if not EMAIL or not PASSWORD:
    print("❌ 致命错误：未找到账号密码环境变量！")
    sys.exit(1)

DYNAMIC_APP_NAME = "未知应用"

def send_tg_message(status_icon, status_text, time_left):
    if not TG_BOT_TOKEN or not TG_CHAT_ID: return
    local_time = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(time.time() + 8*3600))
    text = f"🖥 {DYNAMIC_APP_NAME}\n{status_icon} {status_text}\n⏱️ 剩余: {time_left}\n时间: {local_time}"
    try:
        requests.post(f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendMessage", 
                      json={"chat_id": TG_CHAT_ID, "text": text}, timeout=10)
    except: pass

# ============================================================
#  底层工具：解决 JS 报错的关键
# ============================================================
def js_fill_input(sb, selector, text):
    """安全地填充输入框，避免 JS 语法错误"""
    script = """
    var el = document.querySelector(arguments[0]);
    if (el) {
        el.value = arguments[1];
        el.dispatchEvent(new Event('input', { bubbles: true }));
        el.dispatchEvent(new Event('change', { bubbles: true }));
    }
    """
    sb.execute_script(script, selector, text)

def _xdotool_click(x, y):
    try: subprocess.run(["xdotool", "mousemove", str(x), str(y), "click", "1"], timeout=2)
    except: pass

# Turnstile 相关脚本保持原样，但采用更安全的调用方式
_SOLVED_JS = "return (function(){var i=document.querySelector('input[name=\"cf-turnstile-response\"]');return !!(i&&i.value&&i.value.length>20);})()"
_EXISTS_JS = "return document.querySelector('input[name=\"cf-turnstile-response\"]') !== null"

def handle_turnstile(sb):
    print("🔍 尝试处理 Turnstile 验证...")
    for _ in range(10):
        if sb.execute_script(_SOLVED_JS): return True
        # 尝试物理点击中心位置（针对headless环境优化）
        sb.click_active_element() 
        time.sleep(2)
    return False

# ============================================================
#  业务逻辑
# ============================================================
def login(sb):
    print(f"🌐 打开登录页面...")
    sb.uc_open_with_reconnect(LOGIN_URL, reconnect_time=5)
    time.sleep(5)
    
    try:
        sb.wait_for_element('input[name="Email"]', timeout=20)
        js_fill_input(sb, 'input[name="Email"]', EMAIL)
        js_fill_input(sb, 'input[name="Password"]', PASSWORD)
        
        if sb.execute_script(_EXISTS_JS): handle_turnstile(sb)
        
        sb.click('button[type="submit"]') # 改用点击提交按钮
        time.sleep(10)
        
        if "Login" not in sb.get_current_url():
            print("✅ 登录成功！")
            return True
    except Exception as e:
        print(f"❌ 登录过程出错: {e}")
    return False

def renew(sb):
    global DYNAMIC_APP_NAME
    print("\n🚀 开始续期流程")
    sb.open("https://justrunmy.app/panel")
    time.sleep(5)

    try:
        # 定位应用卡片
        card = 'a[href*="/panel/manage/"]'
        sb.wait_for_element(card, timeout=20)
        DYNAMIC_APP_NAME = sb.get_text('h3').split('\n')[0].strip()
        print(f"🎯 发现应用: {DYNAMIC_APP_NAME}")
        sb.click(card)
        time.sleep(5)

        # 点击 Reset 按钮
        sb.click('button:contains("Reset")')
        time.sleep(3)

        if sb.execute_script(_EXISTS_JS): handle_turnstile(sb)

        sb.click('button:contains("Just Reset")')
        print("⏳ 提交中...")
        time.sleep(10)

        sb.refresh()
        time.sleep(5)
        timer = sb.get_text('span.font-mono')
        print(f"⏱️ 剩余时间: {timer}")
        
        icon = "✅" if ("2 days" in timer or "3 days" in timer) else "⚠️"
        send_tg_message(icon, "续期结果", timer)
        return True
    except Exception as e:
        print(f"❌ 续期失败: {e}")
        send_tg_message("❌", "续期失败", "Error")
    return False

def main():
    # GitHub Action 环境必须确保参数正确
    with SB(uc=True, test=True, headless=False) as sb:
        if login(sb):
            renew(sb)

if __name__ == "__main__":
    main()
