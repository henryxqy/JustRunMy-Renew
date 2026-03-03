#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import time
import subprocess
from seleniumbase import SB

# ============================================================
#  环境变量配置
# ============================================================
LOGIN_URL = os.environ.get("JUSTRUNMY_LOGIN_URL", "https://justrunmy.app/id/Account/Login")
PANEL_URL = os.environ.get("JUSTRUNMY_PANEL_URL", "https://justrunmy.app/panel")
EMAIL     = os.environ.get("JUSTRUNMY_EMAIL")
PASSWORD  = os.environ.get("JUSTRUNMY_PASSWORD")
APP_NAME  = os.environ.get("JUSTRUNMY_APP_NAME",  "JustRunMy DE")
PROXY_STR = os.environ.get("JUSTRUNMY_PROXY",     "http://127.0.0.1:8080")

# ============================================================
#  页面注入脚本
# ============================================================
_EXPAND_JS = """
(function() {
    var ts = document.querySelector('input[name="cf-turnstile-response"]');
    if (!ts) return 'no-turnstile';
    var el = ts;
    for (var i = 0; i < 20; i++) {
        el = el.parentElement;
        if (!el) break;
        var s = window.getComputedStyle(el);
        if (s.overflow === 'hidden' || s.overflowX === 'hidden' || s.overflowY === 'hidden')
            el.style.overflow = 'visible';
        el.style.minWidth = 'max-content';
    }
    document.querySelectorAll('iframe').forEach(function(f){
        if (f.src && f.src.includes('challenges.cloudflare.com')) {
            f.style.width = '300px'; f.style.height = '65px';
            f.style.minWidth = '300px';
            f.style.visibility = 'visible'; f.style.opacity = '1';
        }
    });
    return 'done';
})()
"""

_EXISTS_JS = """
(function(){
    return document.querySelector('input[name="cf-turnstile-response"]') !== null;
})()
"""

_SOLVED_JS = """
(function(){
    var i = document.querySelector('input[name="cf-turnstile-response"]');
    return !!(i && i.value && i.value.length > 20);
})()
"""

_COORDS_JS = """
(function(){
    var iframes = document.querySelectorAll('iframe');
    for (var i = 0; i < iframes.length; i++) {
        var src = iframes[i].src || '';
        if (src.includes('cloudflare') || src.includes('turnstile') || src.includes('challenges')) {
            var r = iframes[i].getBoundingClientRect();
            if (r.width > 0 && r.height > 0)
                return {cx: Math.round(r.x + 30), cy: Math.round(r.y + r.height / 2)};
        }
    }
    var inp = document.querySelector('input[name="cf-turnstile-response"]');
    if (inp) {
        var p = inp.parentElement;
        for (var j = 0; j < 5; j++) {
            if (!p) break;
            var r = p.getBoundingClientRect();
            if (r.width > 100 && r.height > 30)
                return {cx: Math.round(r.x + 30), cy: Math.round(r.y + r.height / 2)};
            p = p.parentElement;
        }
    }
    return null;
})()
"""

_WININFO_JS = """
(function(){
    return {
        sx: window.screenX || 0,
        sy: window.screenY || 0,
        oh: window.outerHeight,
        ih: window.innerHeight
    };
})()
"""

# ============================================================
#  底层输入工具
# ============================================================
def js_fill_input(sb, selector: str, text: str):
    safe_text = text.replace('\\', '\\\\').replace('"', '\\"')
    sb.execute_script(f"""
    (function(){{
        var el = document.querySelector('{selector}');
        if (!el) return;
        var nativeInputValueSetter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value").set;
        if (nativeInputValueSetter) {{
            nativeInputValueSetter.call(el, "{safe_text}");
        }} else {{
            el.value = "{safe_text}";
        }}
        el.dispatchEvent(new Event('input', {{ bubbles: true }}));
        el.dispatchEvent(new Event('change', {{ bubbles: true }}));
    }})()
    """)

def _activate_window():
    for cls in ["chrome", "chromium", "Chromium", "Chrome", "google-chrome"]:
        try:
            r = subprocess.run(["xdotool", "search", "--onlyvisible", "--class", cls], capture_output=True, text=True, timeout=3)
            wids = [w for w in r.stdout.strip().split("\n") if w.strip()]
            if wids:
                subprocess.run(["xdotool", "windowactivate", "--sync", wids[0]], timeout=3, stderr=subprocess.DEVNULL)
                time.sleep(0.2)
                return
        except Exception:
            pass
    try:
        subprocess.run(["xdotool", "getactivewindow", "windowactivate"], timeout=3, stderr=subprocess.DEVNULL)
    except Exception:
        pass

def _xdotool_click(x: int, y: int):
    _activate_window()
    try:
        subprocess.run(["xdotool", "mousemove", "--sync", str(x), str(y)], timeout=3, stderr=subprocess.DEVNULL)
        time.sleep(0.15)
        subprocess.run(["xdotool", "click", "1"], timeout=2, stderr=subprocess.DEVNULL)
    except Exception:
        os.system(f"xdotool mousemove {x} {y} click 1 2>/dev/null")

# ============================================================
#  人机验证处理
# ============================================================
def _click_turnstile(sb):
    try:
        coords = sb.execute_script(_COORDS_JS)
    except Exception as e:
        print(f"  ⚠️ 获取 Turnstile 坐标失败: {e}")
        return
    if not coords:
        print("  ⚠️ 无法定位 Turnstile 坐标")
        return
    try:
        wi = sb.execute_script(_WININFO_JS)
    except Exception:
        wi = {"sx": 0, "sy": 0, "oh": 800, "ih": 768}
        
    bar = wi["oh"] - wi["ih"]
    ax  = coords["cx"] + wi["sx"]
    ay  = coords["cy"] + wi["sy"] + bar
    print(f"  🖱️ 物理级点击 Turnstile ({ax}, {ay})")
    _xdotool_click(ax, ay)

def handle_turnstile(sb) -> bool:
    print("🔍 处理 Cloudflare Turnstile 验证...")
    time.sleep(2)
    
    if sb.execute_script(_SOLVED_JS):
        print("  ✅ 已静默通过")
        return True

    for _ in range(3):
        try: sb.execute_script(_EXPAND_JS)
        except Exception: pass
        time.sleep(0.5)

    for attempt in range(6):
        if sb.execute_script(_SOLVED_JS):
            print(f"  ✅ Turnstile 通过（第 {attempt + 1} 次尝试）")
            return True
        try: sb.execute_script(_EXPAND_JS)
        except Exception: pass
        time.sleep(0.3)
        
        _click_turnstile(sb)
        
        for _ in range(8):
            time.sleep(0.5)
            if sb.execute_script(_SOLVED_JS):
                print(f"  ✅ Turnstile 通过（第 {attempt + 1} 次尝试）")
                return True
        print(f"  ⚠️ 第 {attempt + 1} 次未通过，重试...")

    print("  ❌ Turnstile 6 次均失败")
    return False

# ============================================================
#  账户登录模块
# ============================================================
def login(sb) -> bool:
    print(f"🌐 打开登录页面: {LOGIN_URL}")
    sb.uc_open_with_reconnect(LOGIN_URL, reconnect_time=5)
    time.sleep(4)

    try:
        sb.wait_for_element('input[name="Email"]', timeout=15)
    except Exception:
        print("❌ 页面未加载出登录表单")
        sb.save_screenshot("login_load_fail.png")
        return False

    print("🍪 关闭可能的 Cookie 弹窗...")
    try:
        for btn in sb.find_elements("button"):
            if "Accept" in (btn.text or ""):
                btn.click()
                time.sleep(0.5)
                break
    except Exception:
        pass

    print(f"📧 填写邮箱: {EMAIL}")
    js_fill_input(sb, 'input[name="Email"]', EMAIL)
    time.sleep(0.3)
    
    print("🔑 填写密码...")
    js_fill_input(sb, 'input[name="Password"]', PASSWORD)
    time.sleep(1)

    if sb.execute_script(_EXISTS_JS):
        if not handle_turnstile(sb):
            print("❌ 登录界面的 Turnstile 验证失败")
            sb.save_screenshot("login_turnstile_fail.png")
            return False
    else:
        print("ℹ️ 未检测到 Turnstile")

    print("🖱️ 敲击回车提交表单...")
    sb.press_keys('input[name="Password"]', '\n')

    print("⏳ 等待登录跳转...")
    for _ in range(12):
        time.sleep(1)
        if sb.get_current_url().split('?')[0].lower() != LOGIN_URL.lower():
            break

    if sb.get_current_url().split('?')[0].lower() != LOGIN_URL.lower():
        print("✅ 登录成功！")
        return True
        
    print("❌ 登录失败，页面没有跳转。")
    sb.save_screenshot("login_failed.png")
    return False

# ============================================================
#  自动续期模块
# ============================================================
def renew(sb) -> bool:
    print("\n" + "="*50)
    print("   🚀 开始自动续期流程")
    print("="*50)
    
    print(f"🌐 进入控制面板: {PANEL_URL}")
    sb.open(PANEL_URL)
    time.sleep(3)

    print(f"🖱️ 查找应用: {APP_NAME}")
    try:
        # 使用动态传入的应用名称来定位卡片
        sb.wait_for_element(f'h3[title="{APP_NAME}"]', timeout=10)
        sb.click(f'h3[title="{APP_NAME}"]')
        time.sleep(3)
        print(f"📍 成功进入应用详情页: {sb.get_current_url()}")
    except Exception as e:
        print(f"❌ 找不到应用卡片 ({APP_NAME}): {e}")
        sb.save_screenshot("renew_app_not_found.png")
        return False

    print("🖱️ 点击 Reset Timer 按钮...")
    try:
        sb.click('button:contains("Reset Timer")')
        time.sleep(3)
    except Exception as e:
        print(f"❌ 找不到 Reset Timer 按钮: {e}")
        sb.save_screenshot("renew_reset_btn_not_found.png")
        return False

    print("🛡️ 检查续期弹窗内是否需要 CF 验证...")
    if sb.execute_script(_EXISTS_JS):
        if not handle_turnstile(sb):
            print("❌ 弹窗内的 Turnstile 验证失败")
            sb.save_screenshot("renew_turnstile_fail.png")
            return False
    else:
        print("ℹ️ 弹窗内未检测到 Turnstile")

    print("🖱️ 点击 Just Reset 确认续期...")
    try:
        sb.click('button:contains("Just Reset")')
        print("⏳ 提交续期请求，等待服务器处理...")
        time.sleep(5) 
    except Exception as e:
        print(f"❌ 找不到 Just Reset 按钮: {e}")
        sb.save_screenshot("renew_just_reset_not_found.png")
        return False

    print("🔍 验证最终倒计时状态...")
    try:
        sb.refresh()
        time.sleep(4)
        timer_text = sb.get_text('span.font-mono.text-xl')
        print(f"⏱️ 当前应用剩余时间: {timer_text}")
        
        if "2 days 23" in timer_text or "3 days" in timer_text:
            print("✅ 完美！续期任务圆满完成！")
            sb.save_screenshot("renew_success.png")
            return True
        else:
            print("⚠️ 倒计时似乎没有重置到最高值，请人工检查截图确认。")
            sb.save_screenshot("renew_warning.png")
            return True 
    except Exception as e:
        print(f"⚠️ 读取倒计时失败，但流程已执行完毕: {e}")
        sb.save_screenshot("renew_timer_read_fail.png")
        return False

# ============================================================
#  脚本执行入口
# ============================================================
def main():
    print("=" * 50)
    print("   JustRunMy.app 自动登录与续期脚本")
    print("=" * 50)

    # 运行前进行基础的参数校验
    if not EMAIL or not PASSWORD:
        print("❌ 错误：未配置 JUSTRUNMY_EMAIL 或 JUSTRUNMY_PASSWORD 环境变量！")
        sys.exit(1)
    
    print(f"🔗 挂载代理: {PROXY_STR if PROXY_STR else '无'}")
    
    # proxy 参数支持传 None（如果用户把代理变量设为空的话）
    proxy_arg = PROXY_STR if PROXY_STR else None

    with SB(uc=True, test=True, headless=False, proxy=proxy_arg) as sb:
        print("✅ 浏览器已启动")
        if proxy_arg:
            try:
                sb.open("https://api.ipify.org/?format=json")
                print(f"🌐 代理出口真实 IP: {sb.get_text('body')}")
            except Exception:
                pass

        if login(sb):
            renew(sb)
        else:
            print("\n❌ 登录环节失败，终止后续续期操作。")

if __name__ == "__main__":
    main()
