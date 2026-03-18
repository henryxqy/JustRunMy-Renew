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
#  针对验证码和遮挡的专项逻辑
# ============================================================
_SOLVED_JS = "return (function(){var i=document.querySelector('input[name=\"cf-turnstile-response\"]');return !!(i&&i.value&&i.value.length>20);})()"

def handle_turnstile(sb):
    print("🤖 正在尝试攻克 Turnstile 人机验证...")
    for i in range(12):
        if sb.execute_script(_SOLVED_JS):
            print("✅ Turnstile 验证通过！")
            return True
        
        # 核心：暴力移除任何可能遮挡点击的层（Cookie/Modal/Overlay）
        sb.execute_script("""
            var selectors = ['.fc-consent-root', '#js-cookie-box', '.cookie-banner', 'div[class*="cookie"]', 'div[class*="modal"]'];
            selectors.forEach(s => {
                var el = document.querySelector(s);
                if (el) el.remove();
            });
        """)
        
        # 物理点击验证框位置
        try:
            # 尝试定位 Cloudflare 的 span 或直接点击活动元素
            if sb.is_element_visible('div[id*="turnstile"]'):
                sb.click('div[id*="turnstile"]')
            else:
                sb.click_active_element()
        except: pass
        
        time.sleep(3)
    return False

# ============================================================
#  业务流程
# ============================================================
def login(sb):
    print(f"🌐 正在打开登录页面...")
    sb.uc_open_with_reconnect(LOGIN_URL, reconnect_time=5)
    time.sleep(5)
    
    # 尝试点掉 Accept All 按钮
    try:
        sb.click('button:contains("Accept All")', timeout=4)
    except: pass

    try:
        sb.wait_for_element('input[name="Email"]', timeout=20)
        
        # 填充数据
        js_fill_input(sb, 'input[name="Email"]', EMAIL)
        js_fill_input(sb, 'input[name="Password"]', PASSWORD)
        print("📧 账号密码已填入")
        
        # 处理验证码
        handle_turnstile(sb)
        sb.save_screenshot("debug_captcha_status.png")
        
        # 点击提交
        print("🖱️ 提交表单...")
        # 截图显示按钮包含 "ID_SignIn"
        sb.click('button:contains("SignIn")') 
        
        time.sleep(12)
        curr_url = sb.get_current_url()
        
        if "Login" not in curr_url:
            print("✅ 登录跳转成功！")
            return True
        else:
            print(f"❌ 登录未成功。当前位置: {curr_url}")
            sb.save_screenshot("error_login_failed.png")
    except Exception as e:
        print(f"❌ 登录异常: {e}")
        sb.save_screenshot("error_login_exception.png")
    return False

def renew(sb):
    global DYNAMIC_APP_NAME
    print("\n🚀 开始执行续期操作...")
    sb.open("https://justrunmy.app/panel")
    time.sleep(8)

    try:
        # 定位并点击管理卡片
        card = 'a[href*="/panel/manage/"]'
        sb.wait_for_element(card, timeout=25)
        DYNAMIC_APP_NAME = sb.get_text('h3').split('\n')[0].strip()
        print(f"🎯 发现应用: {DYNAMIC_APP_NAME}")
        
        sb.click(card)
        time.sleep(8)

        # 点击 Reset 按钮
        print("🖱️ 点击 Reset Timer...")
        sb.click('button:contains("Reset")')
        time.sleep(5)

        # 弹窗内可能还有一次验证
        handle_turnstile(sb)

        # 最终确认
        print("🖱️ 点击 Just Reset...")
        sb.click('button:contains("Just Reset")')
        time.sleep(12)

        # 验证倒计时
        sb.refresh()
        time.sleep(8)
        timer = sb.get_text('span.font-mono')
        print(f"⏱️ 续期后剩余时间: {timer}")
        
        # 只要包含 2 或 3 天，就认为成功
        icon = "✅" if any(x in timer for x in ["2 days", "3 days", "2d", "3d"]) else "⚠️"
        send_tg_message(icon, "自动续期结果", timer)
        sb.save_screenshot("step_final_result.png")
        return True
    except Exception as e:
        print(f"❌ 续期执行失败: {e}")
        sb.save_screenshot("error_renew_exception.png")
        send_tg_message("❌", "续期失败", "Error")
    return False

def main():
    # 强制开启 uc 模式以绕过检测
    with SB(uc=True, test=True, headless=False) as sb:
        if login(sb):
            renew(sb)
        else:
            print("❌ 登录失败，流程终止。")

if __name__ == "__main__":
    main()
