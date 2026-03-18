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

def js_fill_input(sb, selector, text):
    script = """
    var el = document.querySelector(arguments[0]);
    if (el) {
        el.value = arguments[1];
        el.dispatchEvent(new Event('input', { bubbles: true }));
        el.dispatchEvent(new Event('change', { bubbles: true }));
    }
    """
    sb.execute_script(script, selector, text)

# ============================================================
#  增强版验证处理
# ============================================================
_SOLVED_JS = "return (function(){var i=document.querySelector('input[name=\"cf-turnstile-response\"]');return !!(i&&i.value&&i.value.length>20);})()"
_EXISTS_JS = "return document.querySelector('input[name=\"cf-turnstile-response\"]') !== null"

def handle_turnstile(sb):
    print("🔍 尝试处理 Turnstile 验证...")
    for i in range(15): # 增加尝试次数
        if sb.execute_script(_SOLVED_JS):
            print("✅ Turnstile 验证已通过")
            return True
        # 针对 Cloudflare 验证，有时点击验证框中心有效
        try:
            sb.click_active_element() 
        except: pass
        time.sleep(3)
    print("⚠️ Turnstile 验证超时，尝试强制继续...")
    return False

# ============================================================
#  业务逻辑
# ============================================================
def login(sb):
    print(f"🌐 正在打开登录页面...")
    sb.uc_open_with_reconnect(LOGIN_URL, reconnect_time=5)
    sb.save_screenshot("step1_login_page.png")
    
    try:
        sb.wait_for_element('input[name="Email"]', timeout=20)
        js_fill_input(sb, 'input[name="Email"]', EMAIL)
        js_fill_input(sb, 'input[name="Password"]', PASSWORD)
        print("📧 表单填充完毕")
        
        if sb.execute_script(_EXISTS_JS):
            handle_turnstile(sb)
        
        sb.save_screenshot("step2_before_submit.png")
        sb.click('button[type="submit"]')
        print("🖱️ 点击登录按钮")
        
        # 增加关键等待
        time.sleep(10)
        curr_url = sb.get_current_url()
        print(f"📍 当前 URL: {curr_url}")
        
        if "Login" not in curr_url:
            print("✅ 登录跳转成功！")
            return True
        else:
            print("❌ 登录未跳转，可能验证码拦截或密码错误")
            sb.save_screenshot("error_login_failed.png")
    except Exception as e:
        print(f"❌ 登录出错: {e}")
        sb.save_screenshot("error_login_exception.png")
    return False

def renew(sb):
    global DYNAMIC_APP_NAME
    print("\n🚀 开始执行续期操作...")
    sb.open("https://justrunmy.app/panel")
    time.sleep(8)
    sb.save_screenshot("step3_panel_page.png")

    try:
        # 1. 寻找应用卡片
        card = 'a[href*="/panel/manage/"]'
        sb.wait_for_element(card, timeout=20)
        DYNAMIC_APP_NAME = sb.get_text('h3').split('\n')[0].strip()
        print(f"🎯 发现应用: {DYNAMIC_APP_NAME}")
        
        sb.click(card)
        time.sleep(8)
        sb.save_screenshot("step4_manage_page.png")

        # 2. 点击 Reset 按钮
        print("🖱️ 点击 Reset Timer...")
        sb.click('button:contains("Reset")')
        time.sleep(5)
        sb.save_screenshot("step5_reset_modal.png")

        if sb.execute_script(_EXISTS_JS):
            handle_turnstile(sb)

        # 3. 最终确认
        print("🖱️ 点击 Just Reset...")
        sb.click('button:contains("Just Reset")')
        time.sleep(12) # 提交通常较慢

        # 4. 验证结果
        sb.refresh()
        time.sleep(8)
        timer = sb.get_text('span.font-mono')
        print(f"⏱️ 续期后剩余时间: {timer}")
        
        icon = "✅" if ("2 days" in timer or "3 days" in timer or "2d" in timer) else "⚠️"
        send_tg_message(icon, "自动续期结果", timer)
        sb.save_screenshot("step6_final_result.png")
        return True
    except Exception as e:
        print(f"❌ 续期失败: {e}")
        sb.save_screenshot("error_renew_exception.png")
        send_tg_message("❌", "续期失败(异常)", "Error")
    return False

def main():
    # 注意：Action 运行通常需要 uc 模式
    with SB(uc=True, test=True, headless=False) as sb:
        if login(sb):
            renew(sb)
        else:
            print("❌ 登录失败，流程终止")

if __name__ == "__main__":
    main()
