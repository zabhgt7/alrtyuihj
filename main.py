#!/usr/bin/env python3

import requests
import json
import time
import os
import logging
from datetime import datetime
from pathlib import Path
import telebot
import threading

WISHLIST_API = "https://www.sheinindia.in/api/wishlist/getwishlist"

TELEGRAM_BOT_TOKEN = "8578329546:AAHLRhR56VcQ1LugAzPGQ4NSLKr19V5-KJ0" # Change with your telegram bot token
TELEGRAM_CHAT_ID = "@abhiwhislistbot" # Change with your telegram chat id

bot = telebot.TeleBot(TELEGRAM_BOT_TOKEN)

CHECK_INTERVAL = 2        # scan gap kam (fast alert)

TOTAL_PAGES = 12         # 100+ products cover

PAGE_SIZE = 20           # double data per request (SABSE IMPORTANT)

REQUEST_TIMEOUT = 7      # zyada wait nahi karega

MAX_RETRIES = 3          # kam retry = fast

MAX_NOTIFICATIONS_PER_PRODUCT = 3


LOG_FILE = "wishlist_monitor.log"

class CustomFormatter(logging.Formatter):
    grey = "\x1b[38;20m"
    green = "\x1b[32;20m"
    yellow = "\x1b[33;20m"
    red = "\x1b[31;20m"
    bold_red = "\x1b[31;1m"
    blue = "\x1b[34;20m"
    reset = "\x1b[0m"
    format_str = "%(asctime)s [%(levelname)s] %(message)s"
    
    FORMATS = {
        logging.DEBUG: grey + format_str + reset,
        logging.INFO: green + format_str + reset,
        logging.WARNING: yellow + format_str + reset,
        logging.ERROR: red + format_str + reset,
        logging.CRITICAL: bold_red + format_str + reset
    }
    
    def format(self, record):
        log_fmt = self.FORMATS.get(record.levelno)
        formatter = logging.Formatter(log_fmt, datefmt="%Y-%m-%d %H:%M:%S")
        return formatter.format(record)

logger = logging.getLogger()
logger.setLevel(logging.INFO)

console_handler = logging.StreamHandler()
console_handler.setFormatter(CustomFormatter())
logger.addHandler(console_handler)

file_handler = logging.FileHandler(LOG_FILE)
file_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S"))
logger.addHandler(file_handler)

NOTIFICATION_COUNT_FILE = "notification_count.json"

def load_notification_counts():
    if os.path.exists(NOTIFICATION_COUNT_FILE):
        try:
            with open(NOTIFICATION_COUNT_FILE, 'r') as f:
                return json.load(f)
        except:
            return {}
    return {}

def save_notification_counts(counts):
    with open(NOTIFICATION_COUNT_FILE, 'w') as f:
        json.dump(counts, f, indent=2)

NOTIFICATION_COUNTS = load_notification_counts()

PREVIOUS_STOCK_STATUS = {}

MONITORING_ACTIVE = False
MONITOR_THREAD = None

def parse_cookie_header(cookie_string):
    cookies = {}
    pairs = cookie_string.strip().split(';')
    for pair in pairs:
        if '=' in pair:
            key, value = pair.strip().split('=', 1)
            cookies[key] = value
    return cookies

def save_cookies(cookies):
    os.makedirs('cookies', exist_ok=True)
    with open('cookies/cookies.json', 'w') as f:
        json.dump(cookies, f, indent=2)
    logger.info(f"✅ Cookies saved ({len(cookies)} items)")

@bot.message_handler(commands=['start'])
def start_command(message):
    cookies_exist = os.path.exists('cookies/cookies.json')
    
    if cookies_exist:
        welcome = (
            "🚀 *SHEIN WISHLIST MONITOR BOT*\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "✅ Cookies found!\n\n"
            "📋 *Available Commands:*\n\n"
            "/startmonitor - Start monitoring\n"
            "/stopmonitor - Stop monitoring\n"
            "/setcookies - Update cookies\n"
            "/status - Check status\n\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            "👤 Created by: Abhiiiiii\n"
        )
    else:
        welcome = (
            "🚀 *SHEIN WISHLIST MONITOR BOT*\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "❌ No cookies found!\n\n"
            "📋 *Use /setcookies to upload your cookies file*\n\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            "👤 Created by: Abhiiiiii\n"
            
        )
    bot.send_message(message.chat.id, welcome, parse_mode='Markdown')

@bot.message_handler(commands=['setcookies'])
def setcookies_command(message):
    msg = bot.send_message(
        message.chat.id,
        "🍪 *UPLOAD COOKIES FILE*\n"
        "━━━━━━━━━━━━━━━━\n\n"
        "� Upload your cookies.txt file\n"
        "Format: `cookie1=value1; cookie2=value2; ...`\n\n"
        "💡 Copy from browser DevTools (Network tab)\n\n"
        "━━━━━━━━━━━━━━━━\n"
        "📢 @Abhiiiiiiiii",
        parse_mode='Markdown'
    )
    bot.register_next_step_handler(msg, process_cookies)

def process_cookies(message):
    try:
        if not message.document:
            bot.send_message(
                message.chat.id,
                "❌ *Please upload a file!*\n"
                "Use /setcookies and upload cookies.txt",
                parse_mode='Markdown'
            )
            return
        
        file_info = bot.get_file(message.document.file_id)
        downloaded_file = bot.download_file(file_info.file_path)
        cookie_string = downloaded_file.decode('utf-8').strip()
        
        cookies = parse_cookie_header(cookie_string)
        
        if len(cookies) < 5:
            bot.send_message(
                message.chat.id,
                "❌ *Invalid cookies!*\n"
                "Please upload valid cookie file.",
                parse_mode='Markdown'
            )
            return
        
        save_cookies(cookies)
        
        bot.send_message(
            message.chat.id,
            f"✅ *Cookies saved!*\n"
            f"━━━━━━━━━━━━━━━━\n"
            f"📦 {len(cookies)} cookies saved\n"
            f"📁 Location: cookies/cookies.json\n\n"
            f"Use /startmonitor to begin\n\n"
            f"━━━━━━━━━━━━━━━━\n"
            f"📢 Abhiiiii",
            parse_mode='Markdown'
        )
        
    except Exception as e:
        bot.send_message(
            message.chat.id,
            f"❌ *Error:* {str(e)}",
            parse_mode='Markdown'
        )

@bot.message_handler(commands=['startmonitor'])
def startmonitor_command(message):
    global MONITORING_ACTIVE, MONITOR_THREAD
    
    if not os.path.exists('cookies/cookies.json'):
        bot.send_message(
            message.chat.id,
            "❌ *No cookies found!*\n"
            "Use /setcookies first",
            parse_mode='Markdown'
        )
        return
    
    if MONITORING_ACTIVE:
        bot.send_message(
            message.chat.id,
            "⚠️ *Monitor already running!*\n"
            "Use /stopmonitor to stop",
            parse_mode='Markdown'
        )
        return
    
    bot.send_message(
        message.chat.id,
        "🚀 *Starting monitor...*",
        parse_mode='Markdown'
    )
    
    MONITORING_ACTIVE = True
    MONITOR_THREAD = threading.Thread(target=monitor_wishlist, daemon=True)
    MONITOR_THREAD.start()

@bot.message_handler(commands=['stopmonitor'])
def stopmonitor_command(message):
    global MONITORING_ACTIVE
    
    if not MONITORING_ACTIVE:
        bot.send_message(
            message.chat.id,
            "⚠️ *Monitor not running!*\n"
            "Use /startmonitor to start",
            parse_mode='Markdown'
        )
        return
    
    MONITORING_ACTIVE = False
    
    bot.send_message(
        message.chat.id,
        "⏹️ *Monitor stopped!*\n\n"
        "━━━━━━━━━━━━━━━━\n"
        "📢 Abhiiii",
        parse_mode='Markdown'
    )

@bot.message_handler(commands=['status'])
def status_command(message):
    cookies_exist = os.path.exists('cookies/cookies.json')
    
    if MONITORING_ACTIVE:
        status = (
            "✅ *Monitor is RUNNING*\n"
            f"━━━━━━━━━━━━━━━━\n"
            f"📦 Products tracked: {len(PREVIOUS_STOCK_STATUS)}\n"
            f"🔔 Alerts sent: {len(NOTIFICATION_COUNTS)}\n\n"
            f"━━━━━━━━━━━━━━━━\n"
            f"📢 Abhiiii"
        )
    elif cookies_exist:
        status = (
            "⏸️ *Monitor is STOPPED*\n"
            "━━━━━━━━━━━━━━━━\n"
            "✅ Cookies found\n"
            "Use /startmonitor to start\n\n"
            "━━━━━━━━━━━━━━━━\n"
            "📢 Abhiiii"
        )
    else:
        status = (
            "⏸️ *Monitor is STOPPED*\n"
            "━━━━━━━━━━━━━━━━\n"
            "❌ No cookies found\n"
            "Use /setcookies to upload\n\n"
            "━━━━━━━━━━━━━━━━\n"
            "📢 Abhiiii"
        )
    bot.send_message(message.chat.id, status, parse_mode='Markdown')

def load_cookies():
    cookies_file = Path("cookies/cookies.json")
    if cookies_file.exists():
        with open(cookies_file, 'r') as f:
            return json.load(f)
    logger.error("cookies/cookies.json not found!")
    return {}

def send_telegram_message(message):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        data = {
            "chat_id": TELEGRAM_CHAT_ID,
            "text": message,
            "parse_mode": "Markdown"
        }
        response = requests.post(url, json=data, timeout=10)
        return response.status_code == 200
    except Exception as e:
        logger.error(f"Failed to send Telegram message: {e}")
        return False

def fetch_page(cookies, page_num):
    params = {
        'currentPage': page_num,
        'pageSize': PAGE_SIZE,
        'store': 'shein'
    }
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
        'Accept': 'application/json',
        'Referer': 'https://www.sheinindia.in/',
        'Authorization': f'Bearer {cookies.get("A", "")}',
    }
    
    for attempt in range(MAX_RETRIES):
        try:
            response = requests.get(WISHLIST_API, params=params, cookies=cookies, headers=headers, timeout=REQUEST_TIMEOUT)
            
            if response.status_code != 200:
                if attempt < MAX_RETRIES - 1:
                    continue
                return []
            
            data = response.json()
            return data.get('products', [])
            
        except requests.exceptions.Timeout:
            if attempt < MAX_RETRIES - 1:
                continue
            return []
        except Exception:
            if attempt < MAX_RETRIES - 1:
                continue
            return []
    
    return []

def extract_wishlist_products(cookies):
    in_stock_products = []
    total_products = 0
    
    for page_num in range(TOTAL_PAGES + 1):
        params = {
            'currentPage': page_num,
            'pageSize': PAGE_SIZE,
            'store': 'shein'
        }
        
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
                'Accept': 'application/json',
                'Referer': 'https://www.sheinindia.in/',
                'Authorization': f'Bearer {cookies.get("A", "")}',
            }
            
            response = requests.get(WISHLIST_API, params=params, cookies=cookies, headers=headers, timeout=REQUEST_TIMEOUT)
            
            if response.status_code != 200:
                continue
            
            data = response.json()
            
            if 'products' not in data:
                continue
            
            products = data.get('products', [])
            
            if not products:
                break
            
            for product in products:
                total_products += 1
                product_code = product.get('productCode', '')
                product_name = product.get('name', 'Unknown')
                
                if 'variantOptions' in product:
                    for variant in product['variantOptions']:
                        stock = variant.get('stock', {})
                        if stock.get('stockLevelStatus') == 'inStock':
                            variant_code = variant.get('code')
                            size = next((q['value'] for q in variant.get('variantOptionQualifiers', []) 
                                       if q['qualifier'] == 'size'), 'Unknown')
                            
                            in_stock_products.append({
                                'productCode': product_code,
                                'name': product_name,
                                'size': size,
                                'price': product.get('price', {}).get('value', 0),
                                'url': product.get('url', '')
                            })
            
            time.sleep(0.1)
            
        except requests.exceptions.Timeout:
            continue
        except requests.exceptions.RequestException:
            continue
        except json.JSONDecodeError:
            continue
        except Exception:
            continue
    
    return in_stock_products, total_products

def monitor_wishlist():
    global PREVIOUS_STOCK_STATUS, NOTIFICATION_COUNTS
    
    cookies = load_cookies()
    if not cookies:
        logger.error("No cookies found. Cannot monitor.")
        return
    
    banner = """
# ╔══════════════════════════════════════════════════════════════════╗
# ║                                                                  ║
# ║   ███████╗██╗  ██╗███████╗██╗███╗   ██╗                         ║
# ║   ██╔════╝██║  ██║██╔════╝██║████╗  ██║                         ║
# ║   ███████╗███████║█████╗  ██║██╔██╗ ██║                         ║
# ║   ╚════██║██╔══██║██╔══╝  ██║██║╚██╗██║                         ║
# ║   ███████║██║  ██║███████╗██║██║ ╚████║                         ║
# ║   ╚══════╝╚═╝  ╚═╝╚══════╝╚═╝╚═╝  ╚═══╝                         ║
# ║                                                                  ║
# ║         ██╗    ██╗██╗███████╗██╗  ██╗██╗     ██╗███████╗████████╗
# ║         ██║    ██║██║██╔════╝██║  ██║██║     ██║██╔════╝╚══██╔══╝
# ║         ██║ █╗ ██║██║███████╗███████║██║     ██║███████╗   ██║   
# ║         ██║███╗██║██║╚════██║██╔══██║██║     ██║╚════██║   ██║   
# ║         ╚███╔███╔╝██║███████║██║  ██║███████╗██║███████║   ██║   
# ║          ╚══╝╚══╝ ╚═╝╚══════╝╚═╝  ╚═╝╚══════╝╚═╝╚══════╝   ╚═╝   
# ║                                                                  ║
# ║              ███╗   ███╗ ██████╗ ███╗   ██╗██╗████████╗ ██████╗ ██████╗ 
# ║              ████╗ ████║██╔═══██╗████╗  ██║██║╚══██╔══╝██╔═══██╗██╔══██╗
# ║              ██╔████╔██║██║   ██║██╔██╗ ██║██║   ██║   ██║   ██║██████╔╝
# ║              ██║╚██╔╝██║██║   ██║██║╚██╗██║██║   ██║   ██║   ██║██╔══██╗
# ║              ██║ ╚═╝ ██║╚██████╔╝██║ ╚████║██║   ██║   ╚██████╔╝██║  ██║
# ║              ╚═╝     ╚═╝ ╚═════╝ ╚═╝  ╚═══╝╚═╝   ╚═╝    ╚═════╝ ╚═╝  ╚═╝
# ║                                                                  ║
# ║══════════════════════════════════════════════════════════════════║
# ║                                                                  ║
# ║                  🚀 PREMIUM STOCK MONITORING SYSTEM 🚀          ║
# ║                                                                  ║
# ║                                    ║
# ║                                                                  ║
# ╚══════════════════════════════════════════════════════════════════╝
# """
    
    print(banner)
    logger.info("🚀 Starting SHEIN Wishlist Monitor...")
    logger.info(f"⏱️  Check interval: {CHECK_INTERVAL}s")
    logger.info(f"📦 Monitoring {TOTAL_PAGES + 1} pages...")
    logger.info(f"👤 Created by: Abhiiii")
    
    logger.info("🔄 Performing initial scan...")
    initial_products, total_count = extract_wishlist_products(cookies)
    PREVIOUS_STOCK_STATUS = {p['productCode']: True for p in initial_products}
    logger.info(f"📊 Total: {total_count} | In-stock: {len(initial_products)} | Out-of-stock: {total_count - len(initial_products)}")
    
    send_telegram_message(
        f"🚀 *SHEIN WISHLIST MONITOR*\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"📦 Total products: {total_count}\n"
        f"✅ In-stock: {len(initial_products)}\n"
        f"❌ Out-of-stock: {total_count - len(initial_products)}\n"
        f"⏱️ Check interval: {CHECK_INTERVAL}s\n"
        f"🔔 Max alerts per product: {MAX_NOTIFICATIONS_PER_PRODUCT}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"✅ Monitor is running...\n"
        f"💬 You'll get alerts when stock changes!\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"👤 Created by: Abhiiii\n"
    )
    
    scan_count = 0
    
    try:
        while True:
            scan_count += 1
            start_time = time.time()
            
            products, total = extract_wishlist_products(cookies)
            
            notified = 0
            
            for product in products:
                code = product['productCode']
                
                was_in_stock = PREVIOUS_STOCK_STATUS.get(code, False)
                PREVIOUS_STOCK_STATUS[code] = True
                
                if was_in_stock:
                    continue
                
                notify_count = NOTIFICATION_COUNTS.get(code, 0)
                if notify_count >= MAX_NOTIFICATIONS_PER_PRODUCT:
                    continue
                
                notify_count += 1
                NOTIFICATION_COUNTS[code] = notify_count
                save_notification_counts(NOTIFICATION_COUNTS)
                
                raw_url = product.get('url', '')
                if raw_url.startswith('http'):
                    import re
                    product_url = re.sub(r'-[a-z0-9]+\.html$', '.html', raw_url, flags=re.IGNORECASE)
                elif raw_url:
                    import re
                    clean_url = re.sub(r'-[a-z0-9]+\.html$', '.html', raw_url, flags=re.IGNORECASE)
                    product_url = f"https://www.sheinindia.in{clean_url}"
                else:
                    product_url = f"https://www.sheinindia.in/product-{code}.html"
                
                message = (
                    f"🔔 *IN-STOCK ALERT!*\n"
                    f"━━━━━━━━━━━━━━━━\n"
                    f"📦 Product: {product['name']}\n"
                    f"📏 Size: {product['size']}\n"
                    f"💰 Price: Rs.{product['price']}\n"
                    f"🔖 Code: `{code}`\n"
                    f"━━━━━━━━━━━━━━━━\n"
                    f"🛒 [OPEN PRODUCT]({product_url})\n"
                    f"🔔 Alert {notify_count}/{MAX_NOTIFICATIONS_PER_PRODUCT}\n\n"
                    f"━━━━━━━━━━━━━━━━\n"
                    f"📢 Abhiiiii"
                )
                
                if send_telegram_message(message):
                    logger.info(f"📨 Alert sent: {product['name']} ({code})")
                    notified += 1
                else:
                    logger.error(f"❌ Failed to send alert for {code}")
            
            current_codes = {p['productCode'] for p in products}
            for code in list(PREVIOUS_STOCK_STATUS.keys()):
                if code not in current_codes:
                    PREVIOUS_STOCK_STATUS[code] = False
            
            duration = time.time() - start_time
            logger.info(f"Scan #{scan_count}: {duration:.1f}s | Total: {total} | In-stock: {len(products)} | Notified: {notified}")
            
            time.sleep(CHECK_INTERVAL)
            
    except KeyboardInterrupt:
        logger.info("\n⏹️  Monitor stopped by user")
        send_telegram_message(
            "⏹️ *Wishlist Monitor Stopped*\n\n"
            "━━━━━━━━━━━━━━━━\n"
            "📢 Abhiiiii"
        )
    except Exception as e:
        logger.error(f"❌ Monitor error: {e}")
        send_telegram_message(
            f"❌ *Monitor Error*\n{str(e)}\n\n"
            "━━━━━━━━━━━━━━━━\n"
            "📢 Abhiiii"
        )

if __name__ == "__main__":
    print("""
╔══════════════════════════════════════════════════════════════════╗
║                                                                  ║
║   ███████╗██╗  ██╗███████╗██╗███╗   ██╗                         ║
║   ██╔════╝██║  ██║██╔════╝██║████╗  ██║                         ║
║   ███████╗███████║█████╗  ██║██╔██╗ ██║                         ║
║   ╚════██║██╔══██║██╔══╝  ██║██║╚██╗██║                         ║
║   ███████║██║  ██║███████╗██║██║ ╚████║                         ║
║   ╚══════╝╚═╝  ╚═╝╚══════╝╚═╝╚═╝  ╚═══╝                         ║
║                                                                  ║
║              🤖 TELEGRAM BOT MODE 🤖                            ║
║                                                                  ║
║                                                                  ║
║                                                                  ║
╚══════════════════════════════════════════════════════════════════╝
""")
    
    logger.info("🤖 Starting Telegram Bot...")
    logger.info("📱 Send /start to the bot to begin")
    logger.info("🍪 Use /setcookies to set your cookies and start monitoring")
    logger.info("👤 Created by: Abhiiii")
    
    try:
        logger.info("✅ Bot is running... Press Ctrl+C to stop")
        bot.infinity_polling()
    except KeyboardInterrupt:
        logger.info("\n⏹️  Bot stopped by user")

