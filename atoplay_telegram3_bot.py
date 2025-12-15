import sqlite3
import uuid
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters
import os
import warnings
import logging

# Enable logging for debugging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Suppress ALL warnings
warnings.filterwarnings("ignore")

TOKEN = os.environ.get('BOT_TOKEN', '8505602493:AAF8fznj0OA3OqVstBDt-Zn9MkQ8DjPh5vw')
SUPER_ADMIN_ID = 5911406948  # Super Admin ID
ADMIN_IDS = [5911406948, 5510368247]  # Initial admins

# Exchange rates for different payment methods
EXCHANGE_RATES = {
    'easypaisa': {
        'rate': 1.0,
        'message': "⚠️ **Exchange Rate Notice:**\nFor Easypaisa payments, please convert INR to PKR at current exchange rate.\n\n📊 **Example:** ₹280 ≈ ₨280\n\n💡 **Tip:** Check current INR to PKR rate before sending payment."
    },
    'jazzcash': {
        'rate': 1.0,
        'message': "⚠️ **Exchange Rate Notice:**\nFor JazzCash payments, please convert INR to PKR at current exchange rate.\n\n📊 **Example:** ₹280 ≈ ₨280\n\n💡 **Tip:** Check current INR to PKR rate before sending payment."
    },
    'binance': {
        'rate': 0.012,
        'message': "⚠️ **Exchange Rate Notice:**\nFor Binance payments, please convert INR to USDT at current exchange rate.\n\n📊 **Example:** ₹280 ≈ 3.36 USDT\n\n💡 **Tip:** Check current INR to USDT rate before sending payment."
    },
    'upi': {
        'rate': 1.0,
        'message': "✅ **UPI Payment:**\nDirect INR payment - no conversion needed."
    }
}

# Make prices editable
PRODUCT_PRICES = {
    '3d': 280,
    '10d': 560,
    '30d': 1250
}

PAYMENT_METHODS = {
    'easypaisa': {'name': 'Easypaisa', 'number': '03431178575', 'account_name': ''},
    'jazzcash': {'name': 'JazzCash', 'number': '', 'account_name': ''},
    'binance': {'name': 'Binance', 'pay_id': '335277914', 'qr_code': None},
    'upi': {'name': 'UPI', 'number': 'trustedprem9719472@ybl', 'account_name': '', 'qr_code': None}
}

# Admin permission levels
ADMIN_PERMISSIONS = {
    'approve_payments': False,
    'add_keys': False,
    'delete_keys': False,
    'view_stock': False,
    'change_prices': False,
    'view_users': False,
    'block_users': False,
    'unblock_users': False,
    'view_user_info': False,
    'adjust_balance': False,
    'view_payments': False,
    'change_payments': False,
    'view_stats': False,
    'manage_admins': False
}

def get_products():
    """Get products with current prices"""
    return {
        'product_3d': {'name': '3-Day Key', 'price': PRODUCT_PRICES['3d'], 'days': 3},
        'product_10d': {'name': '10-Day Key', 'price': PRODUCT_PRICES['10d'], 'days': 10},
        'product_30d': {'name': '30-Day Key', 'price': PRODUCT_PRICES['30d'], 'days': 30}
    }

def init_db():
    # Delete old database if exists
    if os.path.exists('atoplay_bot.db'):
        os.remove('atoplay_bot.db')
        print("🗑️ Old database deleted!")
    
    conn = sqlite3.connect('atoplay_bot.db')
    cursor = conn.cursor()
    
    # USERS table with ALL columns
    cursor.execute('''CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        telegram_id INTEGER UNIQUE,
        username TEXT,
        balance REAL DEFAULT 0,
        unique_id TEXT UNIQUE,
        is_blocked INTEGER DEFAULT 0,
        blocked_reason TEXT,
        blocked_at TIMESTAMP,
        is_admin INTEGER DEFAULT 0,
        added_by INTEGER,
        permissions TEXT DEFAULT '{}'
    )''')
    
    cursor.execute('''CREATE TABLE IF NOT EXISTS transactions (
        transaction_id INTEGER PRIMARY KEY,
        user_id INTEGER,
        amount REAL,
        payment_method TEXT,
        screenshot TEXT,
        status TEXT DEFAULT 'pending',
        admin_id INTEGER,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')
    
    cursor.execute('''CREATE TABLE IF NOT EXISTS keys_stock (
        key_id INTEGER PRIMARY KEY,
        key_value TEXT UNIQUE,
        key_type TEXT,  -- '3d', '10d', '30d'
        status TEXT DEFAULT 'available',  -- 'available', 'used'
        used_by INTEGER,
        used_at TIMESTAMP,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')
    
    cursor.execute('''CREATE TABLE IF NOT EXISTS user_keys (
        user_key_id INTEGER PRIMARY KEY,
        user_id INTEGER,
        key_value TEXT,
        key_type TEXT,
        purchased_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        status TEXT DEFAULT 'active'  -- 'active', 'expired'
    )''')
    
    cursor.execute('''CREATE TABLE IF NOT EXISTS admin_logs (
        log_id INTEGER PRIMARY KEY,
        admin_id INTEGER,
        action TEXT,
        target_user_id INTEGER,
        details TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')
    
    cursor.execute('''CREATE TABLE IF NOT EXISTS settings (
        setting_id INTEGER PRIMARY KEY,
        setting_key TEXT UNIQUE,
        setting_value TEXT,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')
    
    cursor.execute('''CREATE TABLE IF NOT EXISTS payment_methods (
        method_id INTEGER PRIMARY KEY,
        method_key TEXT UNIQUE,
        method_name TEXT,
        number TEXT,
        pay_id TEXT,
        account_name TEXT,
        qr_code TEXT,
        is_active INTEGER DEFAULT 1,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')
    
    # Add initial super admin (5911406948) with all permissions
    super_admin_permissions = {
        'approve_payments': True,
        'add_keys': True,
        'delete_keys': True,
        'view_stock': True,
        'change_prices': True,
        'view_users': True,
        'block_users': True,
        'unblock_users': True,
        'view_user_info': True,
        'adjust_balance': True,
        'view_payments': True,
        'change_payments': True,
        'view_stats': True,
        'manage_admins': True
    }
    
    cursor.execute('''INSERT OR IGNORE INTO users 
                      (telegram_id, username, is_admin, permissions) 
                      VALUES (?, 'Super Admin', 1, ?)''', 
                   (SUPER_ADMIN_ID, str(super_admin_permissions)))
    
    # Add other initial admin with basic permissions
    initial_admin_permissions = {
        'approve_payments': True,
        'add_keys': True,
        'view_stock': True,
        'view_users': True,
        'view_user_info': True,
        'adjust_balance': True,
        'view_payments': True,
        'view_stats': True
    }
    
    cursor.execute('''INSERT OR IGNORE INTO users 
                      (telegram_id, username, is_admin, permissions) 
                      VALUES (?, 'Admin', 1, ?)''', 
                   (5510368247, str(initial_admin_permissions)))
    
    # Initialize payment methods in database
    for method_key, method_data in PAYMENT_METHODS.items():
        cursor.execute('''INSERT OR IGNORE INTO payment_methods 
                          (method_key, method_name, number, pay_id, account_name, qr_code) 
                          VALUES (?, ?, ?, ?, ?, ?)''',
                       (method_key, 
                        method_data['name'],
                        method_data.get('number', ''),
                        method_data.get('pay_id', ''),
                        method_data.get('account_name', ''),
                        method_data.get('qr_code', '')))
    
    conn.commit()
    conn.close()
    print("✅ Database tables created successfully!")
    print("✅ Super Admin (5911406948) added with ALL permissions!")
    print("✅ Admin (5510368247) added with basic permissions!")
    print("✅ Payment methods initialized!")

def load_payment_methods():
    """Load payment methods from database"""
    conn = sqlite3.connect('atoplay_bot.db')
    cursor = conn.cursor()
    
    cursor.execute('''SELECT method_key, method_name, number, pay_id, account_name, qr_code 
                      FROM payment_methods WHERE is_active = 1''')
    
    methods_data = cursor.fetchall()
    conn.close()
    
    methods = {}
    for method_key, method_name, number, pay_id, account_name, qr_code in methods_data:
        methods[method_key] = {
            'name': method_name,
            'number': number if number else '',
            'pay_id': pay_id if pay_id else '',
            'account_name': account_name if account_name else '',
            'qr_code': qr_code if qr_code else None
        }
    
    return methods

def update_payment_methods_global():
    """Update the global PAYMENT_METHODS variable from database"""
    global PAYMENT_METHODS
    new_methods = load_payment_methods()
    PAYMENT_METHODS.clear()
    PAYMENT_METHODS.update(new_methods)

def update_payment_method(method_key, updates):
    """Update a payment method in database"""
    conn = sqlite3.connect('atoplay_bot.db')
    cursor = conn.cursor()
    
    set_clauses = []
    values = []
    
    for key, value in updates.items():
        set_clauses.append(f"{key} = ?")
        values.append(value)
    
    values.append(method_key)
    
    query = f'''UPDATE payment_methods 
                SET {', '.join(set_clauses)}, updated_at = CURRENT_TIMESTAMP
                WHERE method_key = ?'''
    
    cursor.execute(query, values)
    conn.commit()
    conn.close()
    
    # Update global variable
    update_payment_methods_global()

def add_sample_keys():
    """Add real keys provided by user - ONLY REAL KEYS"""
    conn = sqlite3.connect('atoplay_bot.db')
    cursor = conn.cursor()
    
    # ONLY REAL KEYS FROM USER'S MESSAGES
    real_keys = {
        '3d': [
            'EZwXVP',  # 3-day key
            'ZyQiee',  # 3-day key
            'KuU4fy',  # 3-day key
            'ZKyyPO'   # 3-day key
        ],
        '10d': [
            'UbhtLb',  # 10-day key
            'FIrCnj',  # 10-day key  
            'PsXM5W'   # 10-day key
        ],
        '30d': [
            # 30-day keys (none provided by user)
        ]
    }
    
    for key_type, keys in real_keys.items():
        for key_value in keys:
            cursor.execute('''INSERT OR IGNORE INTO keys_stock (key_value, key_type) 
                              VALUES (?, ?)''', (key_value, key_type))
    
    conn.commit()
    conn.close()
    print("✅ ONLY REAL KEYS ADDED (EXACTLY AS PROVIDED)!")

def get_stock_info():
    """Get current stock information"""
    conn = sqlite3.connect('atoplay_bot.db')
    cursor = conn.cursor()
    
    cursor.execute('''SELECT key_type, 
                             SUM(CASE WHEN status = 'available' THEN 1 ELSE 0 END) as available
                      FROM keys_stock 
                      GROUP BY key_type''')
    
    stock_data = cursor.fetchall()
    conn.close()
    
    stock_info = {}
    for key_type, available in stock_data:
        stock_info[key_type] = available
    
    return stock_info

def is_admin(user_id):
    """Check if user is admin"""
    conn = sqlite3.connect('atoplay_bot.db')
    cursor = conn.cursor()
    
    cursor.execute('SELECT is_admin FROM users WHERE telegram_id = ?', (user_id,))
    result = cursor.fetchone()
    conn.close()
    
    return result and result[0] == 1

def is_super_admin(user_id):
    """Check if user is super admin"""
    return user_id == SUPER_ADMIN_ID

def get_admin_permissions(user_id):
    """Get admin permissions from database"""
    conn = sqlite3.connect('atoplay_bot.db')
    cursor = conn.cursor()
    
    cursor.execute('SELECT permissions FROM users WHERE telegram_id = ?', (user_id,))
    result = cursor.fetchone()
    conn.close()
    
    if result and result[0]:
        import ast
        try:
            return ast.literal_eval(result[0])
        except:
            return ADMIN_PERMISSIONS.copy()
    return ADMIN_PERMISSIONS.copy()

def has_permission(user_id, permission):
    """Check if admin has specific permission"""
    if is_super_admin(user_id):
        return True
    
    permissions = get_admin_permissions(user_id)
    return permissions.get(permission, False)

def update_admin_permissions(user_id, permissions):
    """Update admin permissions in database"""
    conn = sqlite3.connect('atoplay_bot.db')
    cursor = conn.cursor()
    
    cursor.execute('UPDATE users SET permissions = ? WHERE telegram_id = ?',
                   (str(permissions), user_id))
    
    conn.commit()
    conn.close()

def get_all_admins():
    """Get all admin users"""
    conn = sqlite3.connect('atoplay_bot.db')
    cursor = conn.cursor()
    
    cursor.execute('''SELECT telegram_id, username, is_admin 
                      FROM users WHERE is_admin = 1''')
    admins = cursor.fetchall()
    conn.close()
    
    return admins

def get_admin_permissions_list(admin_id):
    """Get admin permissions as formatted list"""
    permissions = get_admin_permissions(admin_id)
    
    permission_names = {
        'approve_payments': '✅ Approve Payments',
        'add_keys': '✅ Add Keys',
        'delete_keys': '✅ Delete Keys',
        'view_stock': '✅ View Stock',
        'change_prices': '✅ Change Prices',
        'view_users': '✅ View Users',
        'block_users': '✅ Block Users',
        'unblock_users': '✅ Unblock Users',
        'view_user_info': '✅ View User Info',
        'adjust_balance': '✅ Adjust Balance',
        'view_payments': '✅ View Payments',
        'change_payments': '✅ Change Payments',
        'view_stats': '✅ View Stats',
        'manage_admins': '✅ Manage Admins'
    }
    
    enabled = []
    disabled = []
    
    for perm, name in permission_names.items():
        if permissions.get(perm, False):
            enabled.append(name)
        else:
            disabled.append(name.replace('✅', '❌'))
    
    return enabled, disabled

def log_admin_action(admin_id, action, target_user_id, details=""):
    """Log admin actions"""
    conn = sqlite3.connect('atoplay_bot.db')
    cursor = conn.cursor()
    
    cursor.execute('''INSERT INTO admin_logs (admin_id, action, target_user_id, details) 
                      VALUES (?, ?, ?, ?)''',
                   (admin_id, action, target_user_id, details))
    
    conn.commit()
    conn.close()

# ========== KEYBOARDS ==========
def get_user_main_menu(is_admin=False):
    if is_admin:
        keyboard = [
            [KeyboardButton("🛒 Buy Keys"), KeyboardButton("🔧 Admin Panel")],
            [KeyboardButton("💳 Balance"), KeyboardButton("🔑 My Keys")],
            [KeyboardButton("📞 Contact"), KeyboardButton("📢 Channel")]
        ]
    else:
        keyboard = [
            [KeyboardButton("🛒 Buy Keys")],
            [KeyboardButton("💳 Balance"), KeyboardButton("🔑 My Keys")],
            [KeyboardButton("📞 Contact"), KeyboardButton("📢 Channel")]
        ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=False)

def get_admin_main_menu(user_id):
    """Beautiful admin panel with inline buttons based on permissions"""
    keyboard = []
    
    if has_permission(user_id, 'view_stock'):
        keyboard.append([InlineKeyboardButton("📦 Stock Management", callback_data='admin_stock')])
    
    if has_permission(user_id, 'change_prices'):
        keyboard.append([InlineKeyboardButton("💰 Price Management", callback_data='admin_prices')])
    
    if has_permission(user_id, 'view_users'):
        keyboard.append([InlineKeyboardButton("👤 User Management", callback_data='admin_users')])
    
    if has_permission(user_id, 'view_payments'):
        keyboard.append([InlineKeyboardButton("💳 Payment Methods", callback_data='admin_payments')])
    
    if has_permission(user_id, 'view_stats'):
        keyboard.append([InlineKeyboardButton("📊 View Statistics", callback_data='admin_stats')])
    
    if is_super_admin(user_id) or has_permission(user_id, 'manage_admins'):
        keyboard.append([InlineKeyboardButton("⚙️ Admin Settings", callback_data='admin_settings')])
    
    keyboard.append([InlineKeyboardButton("🏠 Back to Main Menu", callback_data='admin_back_home')])
    
    return InlineKeyboardMarkup(keyboard)

def get_admin_stock_menu(user_id):
    """Stock management sub-menu based on permissions"""
    keyboard = []
    
    if has_permission(user_id, 'add_keys'):
        keyboard.append([InlineKeyboardButton("➕ Add 3-Day Key", callback_data='addkey_3d_menu')])
        keyboard.append([InlineKeyboardButton("➕ Add 10-Day Key", callback_data='addkey_10d_menu')])
        keyboard.append([InlineKeyboardButton("➕ Add 30-Day Key", callback_data='addkey_30d_menu')])
    
    if has_permission(user_id, 'delete_keys'):
        keyboard.append([InlineKeyboardButton("🗑️ Delete Key", callback_data='delkey_menu')])
    
    if has_permission(user_id, 'view_stock'):
        keyboard.append([InlineKeyboardButton("📋 View All Keys", callback_data='view_stock')])
    
    keyboard.append([InlineKeyboardButton("🔙 Back", callback_data='admin_back')])
    
    return InlineKeyboardMarkup(keyboard)

def get_admin_payments_menu(user_id):
    """Payment methods management sub-menu based on permissions"""
    keyboard = []
    
    if has_permission(user_id, 'change_payments'):
        keyboard.append([InlineKeyboardButton("📱 Easypaisa", callback_data='set_easypaisa_menu')])
        keyboard.append([InlineKeyboardButton("📱 JazzCash", callback_data='set_jazzcash_menu')])
        keyboard.append([InlineKeyboardButton("💰 Binance", callback_data='set_binance_menu')])
        keyboard.append([InlineKeyboardButton("💎 UPI Details", callback_data='set_upi_menu')])
        keyboard.append([InlineKeyboardButton("📸 UPI QR Code", callback_data='set_upi_qr_menu')])
        keyboard.append([InlineKeyboardButton("📸 Binance QR Code", callback_data='set_binance_qr_menu')])
    
    if has_permission(user_id, 'view_payments'):
        keyboard.append([InlineKeyboardButton("👀 View Methods", callback_data='view_payments')])
    
    keyboard.append([InlineKeyboardButton("🔙 Back", callback_data='admin_back')])
    
    return InlineKeyboardMarkup(keyboard)

def get_admin_prices_menu(user_id):
    """Price management sub-menu based on permissions"""
    keyboard = []
    
    if has_permission(user_id, 'change_prices'):
        keyboard.append([InlineKeyboardButton("💰 3-Day Price", callback_data='price_3d_menu')])
        keyboard.append([InlineKeyboardButton("💰 10-Day Price", callback_data='price_10d_menu')])
        keyboard.append([InlineKeyboardButton("💰 30-Day Price", callback_data='price_30d_menu')])
    
    if has_permission(user_id, 'view_payments'):
        keyboard.append([InlineKeyboardButton("📊 View All Prices", callback_data='view_prices')])
    
    keyboard.append([InlineKeyboardButton("🔙 Back", callback_data='admin_back')])
    
    return InlineKeyboardMarkup(keyboard)

def get_admin_users_menu(user_id):
    """User management sub-menu based on permissions"""
    keyboard = []
    
    if has_permission(user_id, 'block_users'):
        keyboard.append([InlineKeyboardButton("🚫 Block User", callback_data='block_user_menu')])
    
    if has_permission(user_id, 'unblock_users'):
        keyboard.append([InlineKeyboardButton("✅ Unblock User", callback_data='unblock_user_menu')])
    
    if has_permission(user_id, 'view_user_info'):
        keyboard.append([InlineKeyboardButton("👤 User Info", callback_data='userinfo_menu')])
    
    if has_permission(user_id, 'view_users'):
        keyboard.append([InlineKeyboardButton("📊 All Users", callback_data='view_users')])
    
    if has_permission(user_id, 'adjust_balance'):
        keyboard.append([InlineKeyboardButton("💰 Manage Balance", callback_data='manage_user_balance_menu')])
    
    keyboard.append([InlineKeyboardButton("🔙 Back", callback_data='admin_back')])
    
    return InlineKeyboardMarkup(keyboard)

def get_admin_settings_menu(user_id):
    """Admin settings sub-menu (for super admin only)"""
    if not is_super_admin(user_id):
        return None
    
    keyboard = [
        [InlineKeyboardButton("➕ Add Admin", callback_data='addadmin_menu')],
        [InlineKeyboardButton("➖ Remove Admin", callback_data='removeadmin_menu')],
        [InlineKeyboardButton("👑 List Admins", callback_data='listadmins')],
        [InlineKeyboardButton("⚙️ Set Permissions", callback_data='set_permissions_menu')],
        [InlineKeyboardButton("📋 View Permissions", callback_data='view_permissions')],
        [InlineKeyboardButton("🔙 Back", callback_data='admin_back')]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_buy_menu():
    keyboard = [
        [
            InlineKeyboardButton("3-Day Key", callback_data='product_3d'),
            InlineKeyboardButton("10-Day Key", callback_data='product_10d')
        ],
        [
            InlineKeyboardButton("30-Day Key", callback_data='product_30d'),
            InlineKeyboardButton("💳 Add Balance", callback_data='add_balance')
        ],
        [InlineKeyboardButton("❌ Cancel", callback_data='cancel')]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_permissions_menu(target_admin_id):
    """Permissions selection menu"""
    permissions_list = [
        ('approve_payments', '✅ Approve Payments'),
        ('add_keys', '✅ Add Keys'),
        ('delete_keys', '✅ Delete Keys'),
        ('view_stock', '✅ View Stock'),
        ('change_prices', '✅ Change Prices'),
        ('view_users', '✅ View Users'),
        ('block_users', '✅ Block Users'),
        ('unblock_users', '✅ Unblock Users'),
        ('view_user_info', '✅ View User Info'),
        ('adjust_balance', '✅ Adjust Balance'),
        ('view_payments', '✅ View Payments'),
        ('change_payments', '✅ Change Payments'),
        ('view_stats', '✅ View Stats')
    ]
    
    keyboard = []
    for perm_key, perm_name in permissions_list:
        callback_data = f'toggle_{target_admin_id}_{perm_key}'
        keyboard.append([InlineKeyboardButton(perm_name, callback_data=callback_data)])
    
    keyboard.append([InlineKeyboardButton("💾 Save Permissions", callback_data=f'save_permissions_{target_admin_id}')])
    keyboard.append([InlineKeyboardButton("🔙 Back", callback_data='admin_settings')])
    
    return InlineKeyboardMarkup(keyboard)

def get_payment_methods_menu():
    """Payment methods menu for customers"""
    keyboard = [
        [
            InlineKeyboardButton("📱 Easypaisa", callback_data='payment_easypaisa'),
            InlineKeyboardButton("📱 JazzCash", callback_data='payment_jazzcash')
        ],
        [
            InlineKeyboardButton("💰 Binance", callback_data='payment_binance'),
            InlineKeyboardButton("💎 UPI", callback_data='payment_upi')
        ],
        [InlineKeyboardButton("❌ Cancel", callback_data='cancel')]
    ]
    return InlineKeyboardMarkup(keyboard)

# ========== NEW FUNCTION: NOTIFY ADMINS ABOUT KEY SALE ==========
async def notify_admins_about_key_sale(context, user_id, username, product_name, key_value, key_type, amount, payment_method="balance"):
    """Notify all admins when a key is sold"""
    try:
        admins = get_all_admins()
        
        # Get user details
        conn = sqlite3.connect('atoplay_bot.db')
        cursor = conn.cursor()
        cursor.execute('SELECT unique_id FROM users WHERE telegram_id = ?', (user_id,))
        user_data = cursor.fetchone()
        unique_id = user_data[0] if user_data else "N/A"
        conn.close()
        
        # Get current stock after sale
        stock_info = get_stock_info()
        
        # Create notification message
        notification_text = f"""🔔 **NEW KEY SOLD!**

✅ **Sale Details:**
• **Customer:** @{username} (ID: {user_id})
• **Unique ID:** {unique_id}
• **Product:** {product_name}
• **Key:** `{key_value}`
• **Key Type:** {key_type.upper()}-Day
• **Price:** ₹{amount}
• **Payment Method:** {payment_method.title()}
• **Time:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

📊 **Updated Stock:**
• 3-Day Keys: {stock_info.get('3d', 0)} available
• 10-Day Keys: {stock_info.get('10d', 0)} available
• 30-Day Keys: {stock_info.get('30d', 0)} available

⚠️ **Key has been automatically removed from stock.**"""
        
        # Send to all admins
        for admin_id, admin_name, _ in admins:
            try:
                await context.bot.send_message(
                    chat_id=admin_id,
                    text=notification_text,
                    parse_mode='Markdown'
                )
                logger.info(f"Key sale notification sent to admin: {admin_id}")
            except Exception as e:
                logger.error(f"Failed to send notification to admin {admin_id}: {e}")
        
    except Exception as e:
        logger.error(f"Error in notify_admins_about_key_sale: {e}")

# ========== HANDLERS ==========
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info(f"Start command received from user: {update.effective_user.id}")
    
    try:
        user = update.effective_user
        user_id = user.id
        
        conn = sqlite3.connect('atoplay_bot.db')
        cursor = conn.cursor()
        
        cursor.execute('SELECT balance, unique_id, is_blocked, is_admin FROM users WHERE telegram_id = ?', (user_id,))
        user_data = cursor.fetchone()
        
        # Check if user is blocked
        if user_data and user_data[2] == 1:
            await update.message.reply_text("❌ You are blocked from using this bot!")
            conn.close()
            return
        
        if not user_data:
            unique_id = str(uuid.uuid4())[:8].upper()
            is_admin_user = 1 if user_id in ADMIN_IDS else 0
            cursor.execute('INSERT INTO users (telegram_id, username, unique_id, balance, is_blocked, is_admin) VALUES (?, ?, ?, ?, 0, ?)', 
                          (user_id, user.username, unique_id, 0, is_admin_user))
            conn.commit()
            
            welcome_text = f"""🎉 **Welcome to Atoplay Shop!**

🆔 **Your Unique ID:** `{unique_id}`
💰 **Balance:** ₹0

📱 **Available Commands:**
• /buy - Purchase Atoplay keys
• /balance - Check your balance
• /mykeys - View your purchased keys

📞 **Contact:** @Aarifseller
📢 **Channel:** @SnakeEngine105

👉 **Use the buttons below to navigate!**"""
        else:
            balance, unique_id, is_blocked, is_admin_user = user_data
            
            welcome_text = f"""🎉 **Welcome back {user.first_name}!**

🆔 **Your Unique ID:** `{unique_id}`
💰 **Balance:** ₹{balance}

📱 **Available Commands:**
• /buy - Purchase Atoplay keys
• /balance - Check your balance
• /mykeys - View your purchased keys

📞 **Contact:** @Aarifseller
📢 **Channel:** @SnakeEngine105

👉 **Use the buttons below to navigate!**"""
        
        conn.close()
        
        reply_markup = get_user_main_menu(is_admin(user_id))
        
        await update.message.reply_text(welcome_text, reply_markup=reply_markup, parse_mode='Markdown')
        logger.info(f"Welcome message sent to user: {user_id}")
        
    except Exception as e:
        logger.error(f"Error in start command: {e}")
        await update.message.reply_text("⚠️ An error occurred. Please try again.")

async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show beautiful admin panel"""
    admin_id = update.effective_user.id
    
    if not is_admin(admin_id):
        await update.message.reply_text("❌ Unauthorized!")
        return
    
    # Update payment methods from database
    update_payment_methods_global()
    
    stock_info = get_stock_info()
    
    text = f"""🔧 **ADMIN PANEL** - **Control Center**

📊 **Quick Stats:**
• 3-Day Keys: {stock_info.get('3d', 0)} available
• 10-Day Keys: {stock_info.get('10d', 0)} available
• 30-Day Keys: {stock_info.get('30d', 0)} available

🎛️ **Management Sections:**

📦 **Stock Management** - Add/Delete/View keys
💰 **Price Management** - Change product prices
👤 **User Management** - Block/Unblock/View users
💳 **Payment Methods** - Update payment details
📊 **Statistics** - View bot analytics
🔑 **Admin Settings** - Manage admins (Super Admin only)

👇 **Select a section to manage:**"""
    
    reply_markup = get_admin_main_menu(admin_id)
    
    if update.message:
        await update.message.reply_text(text, reply_markup=reply_markup, parse_mode='Markdown')
    elif update.callback_query:
        await update.callback_query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')

async def buy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info(f"Buy command received from user: {update.effective_user.id}")
    
    try:
        user = update.effective_user
        user_id = user.id
        
        # Check if user is blocked
        conn = sqlite3.connect('atoplay_bot.db')
        cursor = conn.cursor()
        cursor.execute('SELECT is_blocked FROM users WHERE telegram_id = ?', (user_id,))
        user_data = cursor.fetchone()
        conn.close()
        
        if user_data and user_data[0] == 1:
            await update.message.reply_text("❌ You are blocked from using this bot!")
            return
        
        # Get stock information
        stock_info = get_stock_info()
        
        reply_markup = get_buy_menu()
        
        # Load current payment methods
        update_payment_methods_global()
        
        text = f"""🛒 **Select Product:**

1️⃣ **3-Day Atoplay Key** - ₹{PRODUCT_PRICES['3d']}
2️⃣ **10-Day Atoplay Key** - ₹{PRODUCT_PRICES['10d']}
3️⃣ **30-Day Atoplay Key** - ₹{PRODUCT_PRICES['30d']}

📦 **Current Stock:**
• 3-Day Keys: {stock_info.get('3d', 0)} available
• 10-Day Keys: {stock_info.get('10d', 0)} available
• 30-Day Keys: {stock_info.get('30d', 0)} available

👇 **Select a product or add balance:**"""
        
        if update.callback_query:
            await update.callback_query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')
        else:
            await update.message.reply_text(text, reply_markup=reply_markup, parse_mode='Markdown')
        
        logger.info(f"Buy menu shown to user: {user_id}")
        
    except Exception as e:
        logger.error(f"Error in buy command: {e}")
        await update.message.reply_text("⚠️ An error occurred. Please try again.")

async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    data = query.data
    
    await query.answer()
    
    logger.info(f"Callback from user: {user_id}, data: {data}")
    
    try:
        # Handle cancel
        if data == 'cancel':
            try:
                await query.edit_message_text("❌ Cancelled!")
            except Exception as e:
                logger.error(f"Error editing message: {e}")
            return
        
        # Handle admin panel navigation
        if data == 'admin_back':
            await admin_panel_callback(update, context)
            return
        
        if data == 'admin_back_home':
            await start_callback(update, context)
            return
        
        # Handle permission toggling
        if data.startswith('toggle_'):
            await toggle_permission(update, context)
            return
        
        if data.startswith('save_permissions_'):
            await save_permissions(update, context)
            return
        
        # Handle select_admin callback
        if data.startswith('select_admin_'):
            await select_admin_for_permissions(update, context)
            return
        
        # Admin panel sections
        if data == 'admin_stock':
            if has_permission(user_id, 'view_stock'):
                await admin_stock_menu(update, context)
            else:
                await query.edit_message_text("❌ You don't have permission to access Stock Management!")
            return
        
        if data == 'admin_prices':
            if has_permission(user_id, 'change_prices') or has_permission(user_id, 'view_payments'):
                await admin_prices_menu(update, context)
            else:
                await query.edit_message_text("❌ You don't have permission to access Price Management!")
            return
        
        if data == 'admin_users':
            if has_permission(user_id, 'view_users'):
                await admin_users_menu(update, context)
            else:
                await query.edit_message_text("❌ You don't have permission to access User Management!")
            return
        
        if data == 'admin_payments':
            if has_permission(user_id, 'view_payments'):
                await admin_payments_menu(update, context)
            else:
                await query.edit_message_text("❌ You don't have permission to access Payment Methods!")
            return
        
        if data == 'admin_stats':
            if has_permission(user_id, 'view_stats'):
                await show_stats(update, context)
            else:
                await query.edit_message_text("❌ You don't have permission to view Statistics!")
            return
        
        if data == 'admin_settings':
            if is_super_admin(user_id) or has_permission(user_id, 'manage_admins'):
                await admin_settings_menu(update, context)
            else:
                await query.edit_message_text("❌ Only Super Admin can access this section!")
            return
        
        if data == 'set_permissions_menu':
            if is_super_admin(user_id):
                await set_permissions_menu(update, context)
            else:
                await query.edit_message_text("❌ Only Super Admin can set permissions!")
            return
        
        if data == 'view_permissions':
            if is_super_admin(user_id):
                await view_all_permissions(update, context)
            else:
                await query.edit_message_text("❌ Only Super Admin can view permissions!")
            return
        
        # Stock management sub-menus
        if data == 'addkey_3d_menu':
            if has_permission(user_id, 'add_keys'):
                await query.edit_message_text(
                    "📝 **Add 3-Day Key**\n\nSend command: `/addkey_3d KEYVALUE`\n\nExample: `/addkey_3d ABC123`\n\n⚠️ Key will be saved EXACTLY as you type it (case sensitive).",
                    parse_mode='Markdown'
                )
            else:
                await query.edit_message_text("❌ You don't have permission to add keys!")
            return
        
        if data == 'addkey_10d_menu':
            if has_permission(user_id, 'add_keys'):
                await query.edit_message_text(
                    "📝 **Add 10-Day Key**\n\nSend command: `/addkey_10d KEYVALUE`\n\nExample: `/addkey_10d XYZ789`\n\n⚠️ Key will be saved EXACTLY as you type it (case sensitive).",
                    parse_mode='Markdown'
                )
            else:
                await query.edit_message_text("❌ You don't have permission to add keys!")
            return
        
        if data == 'addkey_30d_menu':
            if has_permission(user_id, 'add_keys'):
                await query.edit_message_text(
                    "📝 **Add 30-Day Key**\n\nSend command: `/addkey_30d KEYVALUE`\n\nExample: `/addkey_30d LMN456`\n\n⚠️ Key will be saved EXACTLY as you type it (case sensitive).",
                    parse_mode='Markdown'
                )
            else:
                await query.edit_message_text("❌ You don't have permission to add keys!")
            return
        
        if data == 'delkey_menu':
            if has_permission(user_id, 'delete_keys'):
                await query.edit_message_text(
                    "🗑️ **Delete Key**\n\nSend command: `/delkey KEYVALUE`\n\nExample: `/delkey ABC123`\n\n⚠️ Key must match EXACTLY (case sensitive).",
                    parse_mode='Markdown'
                )
            else:
                await query.edit_message_text("❌ You don't have permission to delete keys!")
            return
        
        if data == 'view_stock':
            if has_permission(user_id, 'view_stock'):
                await show_stock(update, context)
            else:
                await query.edit_message_text("❌ You don't have permission to view stock!")
            return
        
        # Price management sub-menus
        if data == 'price_3d_menu':
            if has_permission(user_id, 'change_prices'):
                await query.edit_message_text(
                    f"💰 **Change 3-Day Price**\n\nCurrent Price: ₹{PRODUCT_PRICES['3d']}\n\nSend command: `/price_3d NEW_PRICE`\n\nExample: `/price_3d 300`",
                    parse_mode='Markdown'
                )
            else:
                await query.edit_message_text("❌ You don't have permission to change prices!")
            return
        
        if data == 'price_10d_menu':
            if has_permission(user_id, 'change_prices'):
                await query.edit_message_text(
                    f"💰 **Change 10-Day Price**\n\nCurrent Price: ₹{PRODUCT_PRICES['10d']}\n\nSend command: `/price_10d NEW_PRICE`\n\nExample: `/price_10d 600`",
                    parse_mode='Markdown'
                )
            else:
                await query.edit_message_text("❌ You don't have permission to change prices!")
            return
        
        if data == 'price_30d_menu':
            if has_permission(user_id, 'change_prices'):
                await query.edit_message_text(
                    f"💰 **Change 30-Day Price**\n\nCurrent Price: ₹{PRODUCT_PRICES['30d']}\n\nSend command: `/price_30d NEW_PRICE`\n\nExample: `/price_30d 1300`",
                    parse_mode='Markdown'
                )
            else:
                await query.edit_message_text("❌ You don't have permission to change prices!")
            return
        
        if data == 'view_prices':
            if has_permission(user_id, 'view_payments'):
                await view_prices(update, context)
            else:
                await query.edit_message_text("❌ You don't have permission to view prices!")
            return
        
        # User management sub-menus
        if data == 'block_user_menu':
            if has_permission(user_id, 'block_users'):
                await query.edit_message_text(
                    "🚫 **Block User**\n\nSend command: `/block USER_ID REASON`\n\nExample: `/block 1234567 \"Spamming\"`",
                    parse_mode='Markdown'
                )
            else:
                await query.edit_message_text("❌ You don't have permission to block users!")
            return
        
        if data == 'unblock_user_menu':
            if has_permission(user_id, 'unblock_users'):
                await query.edit_message_text(
                    "✅ **Unblock User**\n\nSend command: `/unblock USER_ID`\n\nExample: `/unblock 1234567`",
                    parse_mode='Markdown'
                )
            else:
                await query.edit_message_text("❌ You don't have permission to unblock users!")
            return
        
        if data == 'userinfo_menu':
            if has_permission(user_id, 'view_user_info'):
                await query.edit_message_text(
                    "👤 **User Information**\n\nSend command: `/userinfo USER_ID`\n\nExample: `/userinfo 1234567`",
                    parse_mode='Markdown'
                )
            else:
                await query.edit_message_text("❌ You don't have permission to view user info!")
            return
        
        if data == 'view_users':
            if has_permission(user_id, 'view_users'):
                await view_users(update, context)
            else:
                await query.edit_message_text("❌ You don't have permission to view users!")
            return
        
        if data == 'manage_user_balance_menu':
            if has_permission(user_id, 'adjust_balance'):
                await query.edit_message_text(
                    "💰 **Manage User Balance**\n\nSend command: `/adjustbalance USER_ID AMOUNT`\n\nExamples:\n• `/adjustbalance 1234567 +500` - Add ₹500\n• `/adjustbalance 1234567 -200` - Subtract ₹200",
                    parse_mode='Markdown'
                )
            else:
                await query.edit_message_text("❌ You don't have permission to adjust balance!")
            return
        
        # Payment methods sub-menus
        if data == 'set_easypaisa_menu':
            if has_permission(user_id, 'change_payments'):
                await query.edit_message_text(
                    "📱 **Set Easypaisa Details**\n\nSend command: `/seteasypaisa NUMBER \"ACCOUNT NAME\"`\n\nExample: `/seteasypaisa 03431178575 \"John Doe\"`",
                    parse_mode='Markdown'
                )
            else:
                await query.edit_message_text("❌ You don't have permission to change payment methods!")
            return
        
        if data == 'set_jazzcash_menu':
            if has_permission(user_id, 'change_payments'):
                await query.edit_message_text(
                    "📱 **Set JazzCash Details**\n\nSend command: `/setjazzcash NUMBER \"ACCOUNT NAME\"`\n\nExample: `/setjazzcash 03001234567 \"Ali Khan\"`",
                    parse_mode='Markdown'
                )
            else:
                await query.edit_message_text("❌ You don't have permission to change payment methods!")
            return
        
        if data == 'set_binance_menu':
            if has_permission(user_id, 'change_payments'):
                await query.edit_message_text(
                    "💰 **Set Binance Pay ID**\n\nSend command: `/setbinance PAY_ID`\n\nExample: `/setbinance 335277914`",
                    parse_mode='Markdown'
                )
            else:
                await query.edit_message_text("❌ You don't have permission to change payment methods!")
            return
        
        if data == 'set_upi_menu':
            if has_permission(user_id, 'change_payments'):
                await query.edit_message_text(
                    "💎 **Set UPI Details**\n\nSend command: `/setupi UPI_ID \"ACCOUNT NAME\"`\n\nExample: `/setupi user@upi \"Account Name\"`",
                    parse_mode='Markdown'
                )
            else:
                await query.edit_message_text("❌ You don't have permission to change payment methods!")
            return
        
        if data == 'set_upi_qr_menu':
            if has_permission(user_id, 'change_payments'):
                await query.edit_message_text(
                    "📸 **Set UPI QR Code**\n\nSend command: `/setupiqr` then send the QR code image.",
                    parse_mode='Markdown'
                )
            else:
                await query.edit_message_text("❌ You don't have permission to change payment methods!")
            return
        
        if data == 'set_binance_qr_menu':
            if has_permission(user_id, 'change_payments'):
                await query.edit_message_text(
                    "📸 **Set Binance QR Code**\n\nSend command: `/setbinanceqr` then send the QR code image.",
                    parse_mode='Markdown'
                )
            else:
                await query.edit_message_text("❌ You don't have permission to change payment methods!")
            return
        
        if data == 'view_payments':
            if has_permission(user_id, 'view_payments'):
                await view_payment_methods(update, context)
            else:
                await query.edit_message_text("❌ You don't have permission to view payment methods!")
            return
        
        # Admin settings sub-menus
        if data == 'addadmin_menu':
            if is_super_admin(user_id):
                await query.edit_message_text(
                    "➕ **Add Admin**\n\nSend command: `/addadmin USER_ID`\n\nExample: `/addadmin 1234567`",
                    parse_mode='Markdown'
                )
            else:
                await query.edit_message_text("❌ Only Super Admin can add admins!")
            return
        
        if data == 'removeadmin_menu':
            if is_super_admin(user_id):
                await query.edit_message_text(
                    "➖ **Remove Admin**\n\nSend command: `/removeadmin USER_ID`\n\nExample: `/removeadmin 1234567`",
                    parse_mode='Markdown'
                )
            else:
                await query.edit_message_text("❌ Only Super Admin can remove admins!")
            return
        
        if data == 'listadmins':
            if is_super_admin(user_id) or has_permission(user_id, 'manage_admins'):
                await list_admins(update, context)
            else:
                await query.edit_message_text("❌ You don't have permission to list admins!")
            return
        
        # Product selection
        if data in ['product_3d', 'product_10d', 'product_30d']:
            await handle_product_selection(update, context)
            return
        
        # Add balance
        if data == 'add_balance':
            await handle_add_balance(update, context)
            return
        
        # Payment method selection
        if data.startswith('payment_'):
            await handle_payment_selection(update, context)
            return
        
        # Amount selection
        if data.startswith('amount_'):
            await handle_amount_selection(update, context)
            return
        
        # Use balance
        if data == 'use_balance':
            await process_balance_purchase(update, context)
            return
        
        # New payment
        if data == 'new_payment':
            await handle_new_payment(update, context)
            return
            
    except Exception as e:
        logger.error(f"Error in callback handler: {e}")
        await query.edit_message_text("❌ An error occurred. Please try again.")

async def admin_panel_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin panel callback handler"""
    query = update.callback_query
    await query.answer()
    
    admin_id = query.from_user.id
    
    if not is_admin(admin_id):
        await query.edit_message_text("❌ Unauthorized!")
        return
    
    stock_info = get_stock_info()
    
    text = f"""🔧 **ADMIN PANEL** - **Control Center**

📊 **Quick Stats:**
• 3-Day Keys: {stock_info.get('3d', 0)} available
• 10-Day Keys: {stock_info.get('10d', 0)} available
• 30-Day Keys: {stock_info.get('30d', 0)} available

🎛️ **Management Sections:**

📦 **Stock Management** - Add/Delete/View keys
💰 **Price Management** - Change product prices
👤 **User Management** - Block/Unblock/View users
💳 **Payment Methods** - Update payment details
📊 **Statistics** - View bot analytics
🔑 **Admin Settings** - Manage admins (Super Admin only)

👇 **Select a section to manage:**"""
    
    reply_markup = get_admin_main_menu(admin_id)
    await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')

async def start_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start callback handler"""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    
    conn = sqlite3.connect('atoplay_bot.db')
    cursor = conn.cursor()
    
    cursor.execute('SELECT balance, unique_id, is_blocked FROM users WHERE telegram_id = ?', (user_id,))
    user_data = cursor.fetchone()
    conn.close()
    
    if user_data:
        balance, unique_id, is_blocked = user_data
        
        if is_blocked == 1:
            text = "❌ You are blocked from using this bot!"
        else:
            text = f"""🏠 **Main Menu**

🆔 **Your ID:** `{unique_id}`
💰 **Balance:** ₹{balance}

👇 **Use buttons below or commands:**"""
    else:
        text = "❌ Account not found! Use /start"
    
    reply_markup = get_user_main_menu(is_admin(user_id))
    await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')

async def admin_stock_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Stock management menu"""
    query = update.callback_query
    await query.answer()
    
    admin_id = query.from_user.id
    
    if not is_admin(admin_id):
        await query.edit_message_text("❌ Unauthorized!")
        return
    
    if not has_permission(admin_id, 'view_stock'):
        await query.edit_message_text("❌ You don't have permission to access Stock Management!")
        return
    
    stock_info = get_stock_info()
    
    text = f"""📦 **Stock Management**

📊 **Current Stock:**
• 3-Day Keys: {stock_info.get('3d', 0)} available - ₹{PRODUCT_PRICES['3d']}
• 10-Day Keys: {stock_info.get('10d', 0)} available - ₹{PRODUCT_PRICES['10d']}
• 30-Day Keys: {stock_info.get('30d', 0)} available - ₹{PRODUCT_PRICES['30d']}

🔧 **Actions:**
• **Add Keys** - Add new keys to stock
• **Delete Key** - Remove a key from stock
• **View All Keys** - See all keys with status

👇 **Select an action:**"""
    
    reply_markup = get_admin_stock_menu(admin_id)
    await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')

async def admin_prices_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Price management menu"""
    query = update.callback_query
    await query.answer()
    
    admin_id = query.from_user.id
    
    if not is_admin(admin_id):
        await query.edit_message_text("❌ Unauthorized!")
        return
    
    if not has_permission(admin_id, 'change_prices') and not has_permission(admin_id, 'view_payments'):
        await query.edit_message_text("❌ You don't have permission to access Price Management!")
        return
    
    text = f"""💰 **Price Management**

💵 **Current Prices:**
• 3-Day Key: ₹{PRODUCT_PRICES['3d']}
• 10-Day Key: ₹{PRODUCT_PRICES['10d']}
• 30-Day Key: ₹{PRODUCT_PRICES['30d']}

🔧 **Actions:**
• Change individual product prices
• View all current prices

👇 **Select an action:**"""
    
    reply_markup = get_admin_prices_menu(admin_id)
    await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')

async def admin_users_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """User management menu"""
    query = update.callback_query
    await query.answer()
    
    admin_id = query.from_user.id
    
    if not is_admin(admin_id):
        await query.edit_message_text("❌ Unauthorized!")
        return
    
    if not has_permission(admin_id, 'view_users'):
        await query.edit_message_text("❌ You don't have permission to access User Management!")
        return
    
    conn = sqlite3.connect('atoplay_bot.db')
    cursor = conn.cursor()
    
    cursor.execute('SELECT COUNT(*) FROM users')
    total_users = cursor.fetchone()[0]
    
    cursor.execute('SELECT COUNT(*) FROM users WHERE is_blocked = 1')
    blocked_users = cursor.fetchone()[0]
    
    conn.close()
    
    text = f"""👤 **User Management**

📊 **User Statistics:**
• Total Users: {total_users}
• Blocked Users: {blocked_users}
• Active Users: {total_users - blocked_users}

🔧 **Actions:**
• **Block User** - Block a user from using bot
• **Unblock User** - Unblock a blocked user
• **User Info** - View user details
• **View All Users** - See all users
• **Manage User Balance** - Add/Subtract user balance

👇 **Select an action:**"""
    
    reply_markup = get_admin_users_menu(admin_id)
    await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')

async def admin_payments_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Payment methods menu"""
    query = update.callback_query
    await query.answer()
    
    admin_id = query.from_user.id
    
    if not is_admin(admin_id):
        await query.edit_message_text("❌ Unauthorized!")
        return
    
    if not has_permission(admin_id, 'view_payments'):
        await query.edit_message_text("❌ You don't have permission to access Payment Methods!")
        return
    
    # Update payment methods
    update_payment_methods_global()
    
    text = """💳 **Payment Methods Management**

🔧 **Available Methods:**
• **Easypaisa** - Update number and account name
• **JazzCash** - Update number and account name
• **Binance** - Update Pay ID and QR Code
• **UPI** - Update UPI ID and QR code

📋 **Actions:**
• Update individual payment methods
• View all current payment details

👇 **Select a payment method to update:**"""
    
    reply_markup = get_admin_payments_menu(admin_id)
    await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')

async def admin_settings_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin settings menu"""
    query = update.callback_query
    await query.answer()
    
    admin_id = query.from_user.id
    
    if not is_super_admin(admin_id):
        await query.edit_message_text("❌ Only Super Admin can access this section!")
        return
    
    admins = get_all_admins()
    
    text = f"""🔑 **Admin Settings** (Super Admin Only)

👑 **Current Admins:** {len(admins)}

🔧 **Actions:**
• **Add Admin** - Add new admin user
• **Remove Admin** - Remove admin privileges
• **List Admins** - View all admin users
• **Set Admin Permissions** - Customize admin access
• **View Admin Permissions** - See current permissions

⚠️ **Warning:** Only Super Admin ({SUPER_ADMIN_ID}) can access these functions.

👇 **Select an action:**"""
    
    reply_markup = get_admin_settings_menu(admin_id)
    await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')

async def set_permissions_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Set permissions menu"""
    query = update.callback_query
    await query.answer()
    
    admin_id = query.from_user.id
    
    if not is_super_admin(admin_id):
        await query.edit_message_text("❌ Only Super Admin can set permissions!")
        return
    
    conn = sqlite3.connect('atoplay_bot.db')
    cursor = conn.cursor()
    
    cursor.execute('''SELECT telegram_id, username FROM users 
                      WHERE is_admin = 1 AND telegram_id != ?''', (SUPER_ADMIN_ID,))
    
    admins = cursor.fetchall()
    conn.close()
    
    if not admins:
        text = "❌ No other admins found to set permissions!"
        keyboard = [[InlineKeyboardButton("🔙 Back to Admin Settings", callback_data='admin_settings')]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')
        return
    
    text = "👥 **Select Admin to Set Permissions:**\n\n"
    
    keyboard = []
    for admin_telegram_id, username in admins:
        username_display = f"@{username}" if username else "No username"
        keyboard.append([InlineKeyboardButton(f"{username_display} ({admin_telegram_id})", 
                                             callback_data=f'select_admin_{admin_telegram_id}')])
    
    keyboard.append([InlineKeyboardButton("🔙 Back to Admin Settings", callback_data='admin_settings')])
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')

async def select_admin_for_permissions(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Select admin for permissions editing - FIXED FUNCTION"""
    query = update.callback_query
    await query.answer()
    
    data = query.data
    target_admin_id = int(data.replace('select_admin_', ''))
    
    # Get admin info
    conn = sqlite3.connect('atoplay_bot.db')
    cursor = conn.cursor()
    
    cursor.execute('SELECT username FROM users WHERE telegram_id = ?', (target_admin_id,))
    result = cursor.fetchone()
    username = result[0] if result else "No username"
    conn.close()
    
    # Get current permissions
    current_permissions = get_admin_permissions(target_admin_id)
    
    text = f"""⚙️ **Set Permissions for Admin**

👤 **Admin:** @{username} ({target_admin_id})

📋 **Current Permissions:**
• Approve Payments: {'✅ Yes' if current_permissions.get('approve_payments') else '❌ No'}
• Add Keys: {'✅ Yes' if current_permissions.get('add_keys') else '❌ No'}
• Delete Keys: {'✅ Yes' if current_permissions.get('delete_keys') else '❌ No'}
• View Stock: {'✅ Yes' if current_permissions.get('view_stock') else '❌ No'}
• Change Prices: {'✅ Yes' if current_permissions.get('change_prices') else '❌ No'}
• View Users: {'✅ Yes' if current_permissions.get('view_users') else '❌ No'}
• Block Users: {'✅ Yes' if current_permissions.get('block_users') else '❌ No'}
• Unblock Users: {'✅ Yes' if current_permissions.get('unblock_users') else '❌ No'}
• View User Info: {'✅ Yes' if current_permissions.get('view_user_info') else '❌ No'}
• Adjust Balance: {'✅ Yes' if current_permissions.get('adjust_balance') else '❌ No'}
• View Payments: {'✅ Yes' if current_permissions.get('view_payments') else '❌ No'}
• Change Payments: {'✅ Yes' if current_permissions.get('change_payments') else '❌ No'}
• View Stats: {'✅ Yes' if current_permissions.get('view_stats') else '❌ No'}
• Manage Admins: {'✅ Yes' if current_permissions.get('manage_admins') else '❌ No'}

👇 **Click on any permission to toggle it:**"""
    
    reply_markup = get_permissions_menu(target_admin_id)
    await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')

async def toggle_permission(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Toggle permission for admin"""
    query = update.callback_query
    await query.answer()
    
    data = query.data
    parts = data.split('_')
    
    if len(parts) < 3:
        return
    
    target_admin_id = int(parts[1])
    permission_key = '_'.join(parts[2:])
    
    # Get current permissions
    current_permissions = get_admin_permissions(target_admin_id)
    
    # Toggle the permission
    current_permissions[permission_key] = not current_permissions.get(permission_key, False)
    
    # Update permissions in context for display
    context.user_data['temp_permissions'] = current_permissions
    context.user_data['target_admin_id'] = target_admin_id
    
    # Get admin info
    conn = sqlite3.connect('atoplay_bot.db')
    cursor = conn.cursor()
    
    cursor.execute('SELECT username FROM users WHERE telegram_id = ?', (target_admin_id,))
    result = cursor.fetchone()
    username = result[0] if result else "No username"
    conn.close()
    
    text = f"""⚙️ **Set Permissions for Admin**

👤 **Admin:** @{username} ({target_admin_id})

📋 **Current Permissions:**
• Approve Payments: {'✅ Yes' if current_permissions.get('approve_payments') else '❌ No'}
• Add Keys: {'✅ Yes' if current_permissions.get('add_keys') else '❌ No'}
• Delete Keys: {'✅ Yes' if current_permissions.get('delete_keys') else '❌ No'}
• View Stock: {'✅ Yes' if current_permissions.get('view_stock') else '❌ No'}
• Change Prices: {'✅ Yes' if current_permissions.get('change_prices') else '❌ No'}
• View Users: {'✅ Yes' if current_permissions.get('view_users') else '❌ No'}
• Block Users: {'✅ Yes' if current_permissions.get('block_users') else '❌ No'}
• Unblock Users: {'✅ Yes' if current_permissions.get('unblock_users') else '❌ No'}
• View User Info: {'✅ Yes' if current_permissions.get('view_user_info') else '❌ No'}
• Adjust Balance: {'✅ Yes' if current_permissions.get('adjust_balance') else '❌ No'}
• View Payments: {'✅ Yes' if current_permissions.get('view_payments') else '❌ No'}
• Change Payments: {'✅ Yes' if current_permissions.get('change_payments') else '❌ No'}
• View Stats: {'✅ Yes' if current_permissions.get('view_stats') else '❌ No'}
• Manage Admins: {'✅ Yes' if current_permissions.get('manage_admins') else '❌ No'}

👇 **Click on any permission to toggle it:**"""
    
    reply_markup = get_permissions_menu(target_admin_id)
    await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')

async def save_permissions(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Save permissions to database"""
    query = update.callback_query
    await query.answer()
    
    data = query.data
    target_admin_id = int(data.replace('save_permissions_', ''))
    
    if 'temp_permissions' not in context.user_data:
        await query.edit_message_text("❌ No permissions to save!")
        return
    
    permissions = context.user_data['temp_permissions']
    
    # Save to database
    update_admin_permissions(target_admin_id, permissions)
    
    # Clear temp data
    context.user_data.pop('temp_permissions', None)
    context.user_data.pop('target_admin_id', None)
    
    # Get admin info
    conn = sqlite3.connect('atoplay_bot.db')
    cursor = conn.cursor()
    
    cursor.execute('SELECT username FROM users WHERE telegram_id = ?', (target_admin_id,))
    result = cursor.fetchone()
    username = result[0] if result else "No username"
    conn.close()
    
    # Log admin action
    log_admin_action(query.from_user.id, 'set_permissions', target_admin_id, 
                    f"Updated permissions for @{username}")
    
    text = f"""✅ **Permissions Updated Successfully!**

👤 **Admin:** @{username} ({target_admin_id})
👑 **Updated by:** Super Admin
⏰ **Time:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

✅ Permissions have been saved to database."""
    
    keyboard = [[InlineKeyboardButton("🔙 Back to Admin Settings", callback_data='admin_settings')]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')

async def view_all_permissions(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """View all admin permissions"""
    query = update.callback_query
    await query.answer()
    
    admin_id = query.from_user.id
    
    if not is_super_admin(admin_id):
        await query.edit_message_text("❌ Only Super Admin can view permissions!")
        return
    
    admins = get_all_admins()
    
    text = "👑 **ADMIN PERMISSIONS OVERVIEW**\n\n"
    
    for admin_telegram_id, username, is_admin_user in admins:
        username_display = f"@{username}" if username else "No username"
        status = "👑 Super Admin" if admin_telegram_id == SUPER_ADMIN_ID else "🔧 Admin"
        
        text += f"**{username_display}** ({admin_telegram_id}) - {status}\n"
        
        if admin_telegram_id != SUPER_ADMIN_ID:
            enabled, disabled = get_admin_permissions_list(admin_telegram_id)
            
            if enabled:
                text += "✅ **Enabled:**\n"
                for perm in enabled:
                    text += f"  • {perm}\n"
            
            if disabled:
                text += "❌ **Disabled:**\n"
                for perm in disabled:
                    text += f"  • {perm}\n"
        
        text += "\n"
    
    keyboard = [[InlineKeyboardButton("🔙 Back to Admin Settings", callback_data='admin_settings')]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')

async def handle_product_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle product selection"""
    query = update.callback_query
    user_id = query.from_user.id
    data = query.data
    
    products = get_products()
    product = products[data]
    context.user_data['selected_product'] = product
    context.user_data['product_id'] = data
    
    conn = sqlite3.connect('atoplay_bot.db')
    cursor = conn.cursor()
    cursor.execute('SELECT balance FROM users WHERE telegram_id = ?', (user_id,))
    result = cursor.fetchone()
    user_balance = result[0] if result else 0
    conn.close()
    
    # Get stock for this specific product
    stock_info = get_stock_info()
    key_type = '3d' if product['days'] == 3 else ('10d' if product['days'] == 10 else '30d')
    available_stock = stock_info.get(key_type, 0)
    
    if available_stock == 0:
        try:
            await query.edit_message_text(f"""❌ **Out of Stock!**

{product['name']} is currently out of stock.

📞 Contact @Aarifseller for availability.
Or choose another product.""", parse_mode='Markdown')
        except Exception as e:
            logger.error(f"Error editing message: {e}")
        return
    
    if user_balance >= product['price']:
        keyboard = [
            [
                InlineKeyboardButton("💳 Use Balance", callback_data='use_balance'),
                InlineKeyboardButton("💸 New Payment", callback_data='new_payment')
            ],
            [InlineKeyboardButton("❌ Cancel", callback_data='cancel')]
        ]
        text = f"""🛒 **Product:** {product['name']}
💰 **Price:** ₹{product['price']}
📦 **Available:** {available_stock} keys

💳 **Your Balance:** ₹{user_balance}

👇 **Choose payment method:**"""
    else:
        text = f"""🛒 **Product:** {product['name']}
💰 **Price:** ₹{product['price']}
📦 **Available:** {available_stock} keys

💸 **Please select payment method:**"""
        keyboard = get_payment_methods_menu()
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    try:
        await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')
    except Exception as e:
        logger.error(f"Error editing message: {e}")
    logger.info(f"Product {product['name']} selected by user: {user_id}")

async def handle_add_balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle add balance"""
    query = update.callback_query
    await query.answer()
    
    keyboard = [
        [
            InlineKeyboardButton("₹500", callback_data='amount_500'),
            InlineKeyboardButton("₹1000", callback_data='amount_1000'),
            InlineKeyboardButton("₹2000", callback_data='amount_2000')
        ],
        [
            InlineKeyboardButton("Other Amount", callback_data='amount_other'),
            InlineKeyboardButton("❌ Cancel", callback_data='cancel')
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    try:
        await query.edit_message_text(
            "💳 **Add Balance**\n\n👇 **Select amount or choose 'Other Amount':**",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
    except Exception as e:
        logger.error(f"Error editing message: {e}")

async def handle_payment_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle payment method selection with exchange rate message"""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    data = query.data
    payment_method = data.replace('payment_', '')
    
    # Update payment methods
    update_payment_methods_global()
    
    if payment_method in PAYMENT_METHODS:
        context.user_data['payment_method'] = payment_method
        payment_info = PAYMENT_METHODS[payment_method]
        
        # Set flag to await screenshot
        context.user_data['awaiting_screenshot'] = True
        
        # Check if this is for product purchase
        if 'selected_product' in context.user_data:
            product = context.user_data.get('selected_product')
            amount = product['price']
            purpose = "Product Purchase"
            
            text = f"""💳 **Payment Details:**

🔸 **Product:** {product['name']}
🔸 **Purpose:** {purpose}
🔸 **Method:** {payment_info['name']}"""
            
            # Add exchange rate message for specific payment methods
            if payment_method in EXCHANGE_RATES:
                exchange_info = EXCHANGE_RATES[payment_method]
                text += f"\n\n{exchange_info['message']}\n"
            
            if payment_method in ['easypaisa', 'jazzcash']:
                account_text = f"\n🔸 **Account Name:** {payment_info.get('account_name', '')}" if payment_info.get('account_name') else ""
                text += f"\n🔸 **Number:** `{payment_info['number']}`{account_text}"
            elif payment_method == 'binance':
                text += f"\n🔸 **Pay ID:** `{payment_info['pay_id']}`"
            elif payment_method == 'upi':
                account_text = f"\n🔸 **Account Name:** {payment_info.get('account_name', '')}" if payment_info.get('account_name') else ""
                text += f"\n🔸 **UPI ID:** `{payment_info['number']}`{account_text}"
            
            text += f"\n🔸 **Amount:** ₹{amount}"
            
            # Add QR code info for UPI and Binance
            if payment_method == 'upi' and payment_info.get('qr_code'):
                text += f"\n\n📱 **UPI QR Code:** Available (Scan to pay)"
            elif payment_method == 'binance' and payment_info.get('qr_code'):
                text += f"\n\n💰 **Binance QR Code:** Available (Scan to pay)"
        
        # If adding balance
        elif 'amount' in context.user_data and context.user_data.get('is_adding_balance', False):
            amount = context.user_data.get('amount')
            purpose = "Add Balance"
            
            text = f"""💳 **Payment Details:**

🔸 **Purpose:** {purpose}
🔸 **Method:** {payment_info['name']}"""
            
            # Add exchange rate message for specific payment methods
            if payment_method in EXCHANGE_RATES:
                exchange_info = EXCHANGE_RATES[payment_method]
                text += f"\n\n{exchange_info['message']}\n"
            
            if payment_method in ['easypaisa', 'jazzcash']:
                account_text = f"\n🔸 **Account Name:** {payment_info.get('account_name', '')}" if payment_info.get('account_name') else ""
                text += f"\n🔸 **Number:** `{payment_info['number']}`{account_text}"
            elif payment_method == 'binance':
                text += f"\n🔸 **Pay ID:** `{payment_info['pay_id']}`"
            elif payment_method == 'upi':
                account_text = f"\n🔸 **Account Name:** {payment_info.get('account_name', '')}" if payment_info.get('account_name') else ""
                text += f"\n🔸 **UPI ID:** `{payment_info['number']}`{account_text}"
            
            text += f"\n🔸 **Amount:** ₹{amount}"
            
            # Add QR code info for UPI and Binance
            if payment_method == 'upi' and payment_info.get('qr_code'):
                text += f"\n\n📱 **UPI QR Code:** Available (Scan to pay)"
            elif payment_method == 'binance' and payment_info.get('qr_code'):
                text += f"\n\n💰 **Binance QR Code:** Available (Scan to pay)"
        
        text += f"""

📋 **Instructions:**
1. Send ₹{amount} to above {payment_info['name']} details
2. Take a clear screenshot of successful payment
3. Send the screenshot here

⚠️ **Make sure screenshot shows:**
• Transaction ID/Reference
• Amount
• Date & Time

📸 **After payment, send the screenshot now.**"""
        
        keyboard = [[InlineKeyboardButton("❌ Cancel", callback_data='cancel')]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        try:
            # If QR code is available, send it first
            if payment_method in ['upi', 'binance'] and payment_info.get('qr_code'):
                await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')
                
                # Send QR code photo
                try:
                    await context.bot.send_photo(
                        chat_id=query.message.chat_id,
                        photo=payment_info['qr_code'],
                        caption=f"📱 **{payment_info['name']} QR Code**\n\nScan this QR code to make payment of ₹{amount}"
                    )
                except Exception as e:
                    logger.error(f"Failed to send QR code: {e}")
                    await query.edit_message_text(f"{text}\n\n⚠️ **Note:** QR code couldn't be loaded. Please use Pay ID/Number instead.", 
                                                 reply_markup=reply_markup, parse_mode='Markdown')
            else:
                await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')
        except Exception as e:
            logger.error(f"Error editing message: {e}")
        logger.info(f"Payment method {payment_method} selected by user: {user_id}")

async def handle_amount_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle amount selection"""
    query = update.callback_query
    await query.answer()
    
    data = query.data
    
    if data == 'amount_other':
        try:
            await query.edit_message_text(
                "💳 **Add Balance**\n\nPlease enter the amount you want to add (in INR).\n\n**Example:** 750\n\n**Minimum:** ₹100",
                parse_mode='Markdown'
            )
        except Exception as e:
            logger.error(f"Error editing message: {e}")
        context.user_data['awaiting_amount'] = True
        return
    
    amount = int(data.replace('amount_', ''))
    context.user_data['amount'] = amount
    context.user_data['is_adding_balance'] = True
    
    keyboard = get_payment_methods_menu()
    
    try:
        await query.edit_message_text(
            f"💳 **Add Balance:** ₹{amount}\n\n👇 **Please select payment method:**",
            reply_markup=keyboard,
            parse_mode='Markdown'
        )
    except Exception as e:
        logger.error(f"Error editing message: {e}")

async def handle_new_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle new payment option"""
    query = update.callback_query
    await query.answer()
    
    product = context.user_data.get('selected_product')
    if product:
        context.user_data['amount'] = product['price']
        context.user_data['is_adding_balance'] = False
    
    keyboard = get_payment_methods_menu()
    
    try:
        await query.edit_message_text(
            "💸 **Please select payment method:**",
            reply_markup=keyboard,
            parse_mode='Markdown'
        )
    except Exception as e:
        logger.error(f"Error editing message: {e}")

async def process_balance_purchase(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Process purchase using balance - WITH ADMIN NOTIFICATION"""
    query = update.callback_query
    user_id = query.from_user.id
    username = query.from_user.username or query.from_user.first_name
    
    if 'selected_product' not in context.user_data:
        try:
            await query.edit_message_text("❌ No product selected!")
        except Exception as e:
            logger.error(f"Error editing message: {e}")
        return
    
    product = context.user_data.get('selected_product')
    
    conn = sqlite3.connect('atoplay_bot.db')
    cursor = conn.cursor()
    
    try:
        # Get user balance and info
        cursor.execute('SELECT user_id, balance, unique_id FROM users WHERE telegram_id = ?', (user_id,))
        user_data = cursor.fetchone()
        
        if not user_data:
            try:
                await query.edit_message_text("❌ User not found!")
            except Exception as e:
                logger.error(f"Error editing message: {e}")
            conn.close()
            return
        
        user_db_id, user_balance, unique_id = user_data
        
        # Check if user has enough balance
        if user_balance < product['price']:
            try:
                await query.edit_message_text(f"""❌ **Insufficient Balance!**

💰 **Price:** ₹{product['price']}
💳 **Your Balance:** ₹{user_balance}

💸 Please add balance or use another payment method.""", parse_mode='Markdown')
            except Exception as e:
                logger.error(f"Error editing message: {e}")
            conn.close()
            return
        
        # Get stock for this product
        key_type = '3d' if product['days'] == 3 else ('10d' if product['days'] == 10 else '30d')
        cursor.execute('''SELECT key_id, key_value FROM keys_stock 
                          WHERE key_type = ? AND status = 'available' 
                          LIMIT 1''', (key_type,))
        
        key_data = cursor.fetchone()
        
        if not key_data:
            try:
                await query.edit_message_text(f"""❌ **Out of Stock!**

{product['name']} is currently out of stock.

📞 Contact @Aarifseller for availability.
Or choose another product.""")
            except Exception as e:
                logger.error(f"Error editing message: {e}")
            conn.close()
            return
        
        key_id, key_value = key_data
        
        # Deduct balance
        new_balance = user_balance - product['price']
        cursor.execute('UPDATE users SET balance = ? WHERE user_id = ?',
                       (new_balance, user_db_id))
        
        # Update key status to 'used' (but don't delete yet for logging)
        cursor.execute('''UPDATE keys_stock 
                          SET status = 'used', used_by = ?, used_at = CURRENT_TIMESTAMP
                          WHERE key_id = ?''',
                       (user_db_id, key_id))
        
        # Add to user_keys table
        cursor.execute('''INSERT INTO user_keys (user_id, key_value, key_type) 
                          VALUES (?, ?, ?)''',
                       (user_db_id, key_value, key_type))
        
        # Create transaction record
        cursor.execute('''INSERT INTO transactions 
                          (user_id, amount, payment_method, status, admin_id) 
                          VALUES (?, ?, 'balance', 'approved', 0)''',
                       (user_db_id, product['price']))
        
        # ========== DELETE KEY FROM STOCK COMPLETELY ==========
        cursor.execute('''DELETE FROM keys_stock 
                          WHERE key_id = ?''', (key_id,))
        
        conn.commit()
        
        # Send key to user
        key_message = f"""✅ **Purchase Successful!**

🎉 Congratulations! Your purchase is complete.

📦 **Product:** {product['name']}
💰 **Price:** ₹{product['price']}
💳 **New Balance:** ₹{new_balance}
🔑 **Your Key:** `{key_value}`

📋 **Instructions:**
1. Open Atoplay application
2. Go to settings or activation section
3. Enter the key: `{key_value}`
4. Enjoy your {product['days']} days subscription!

⚠️ **Important:**
• This key is for ONE-TIME use only
• Do not share with anyone
• Key will expire after {product['days']} days

📞 **Contact:** @Aarifseller for any issues.
📢 **Join:** @SnakeEngine105"""
        
        try:
            await query.edit_message_text(key_message, parse_mode='Markdown')
        except Exception as e:
            logger.error(f"Error editing message: {e}")
        
        # ========== NOTIFY ALL ADMINS ABOUT KEY SALE ==========
        await notify_admins_about_key_sale(
            context=context,
            user_id=user_id,
            username=username,
            product_name=product['name'],
            key_value=key_value,
            key_type=key_type,
            amount=product['price'],
            payment_method="balance"
        )
        
        # Log the purchase
        logger.info(f"User {user_id} purchased {product['name']} with balance. Key: {key_value}")
        
        # Clear user data
        context.user_data.clear()
        
    except Exception as e:
        logger.error(f"Error in process_balance_purchase: {e}")
        try:
            await query.edit_message_text("❌ An error occurred during purchase. Please try again.")
        except:
            pass
    finally:
        conn.close()

async def handle_text_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle text messages for various purposes"""
    try:
        if update.message:
            user_id = update.message.from_user.id
            text = update.message.text
            
            logger.info(f"Text message from user: {user_id}, text: {text}")
            
            # Clear expired user data to prevent unknown command errors
            if 'awaiting_screenshot' in context.user_data:
                if 'screenshot_time' not in context.user_data:
                    context.user_data['screenshot_time'] = datetime.now()
                else:
                    screenshot_time = context.user_data['screenshot_time']
                    if datetime.now() - screenshot_time > timedelta(minutes=10):
                        context.user_data.clear()
                        await update.message.reply_text("⏰ Payment session expired. Please start again with /buy")
                        return
            
            # Check if user is blocked
            conn = sqlite3.connect('atoplay_bot.db')
            cursor = conn.cursor()
            cursor.execute('SELECT is_blocked FROM users WHERE telegram_id = ?', (user_id,))
            user_data = cursor.fetchone()
            conn.close()
            
            if user_data and user_data[0] == 1 and text not in ["/start"]:
                await update.message.reply_text("❌ You are blocked from using this bot!")
                return
            
            # Handle menu button presses for ALL users
            if text == "🛒 Buy Keys":
                return await buy(update, context)
            elif text == "💳 Balance":
                await check_balance(update, context)
            elif text == "🔑 My Keys":
                await my_keys(update, context)
            elif text == "🔧 Admin Panel":
                await admin_panel(update, context)
            elif text == "📞 Contact":
                await update.message.reply_text("📞 **Contact:** @Aarifseller\n📢 **Channel:** @SnakeEngine105", parse_mode='Markdown')
            elif text == "📢 Channel":
                await update.message.reply_text("📢 **Channel:** @SnakeEngine105", parse_mode='Markdown')
            elif 'awaiting_amount' in context.user_data and context.user_data['awaiting_amount']:
                try:
                    amount = float(text)
                    if amount <= 0:
                        await update.message.reply_text("❌ Amount must be greater than 0!")
                        return
                    
                    if amount < 100:
                        await update.message.reply_text("❌ Minimum amount is ₹100!")
                        return
                    
                    context.user_data['amount'] = amount
                    context.user_data['is_adding_balance'] = True
                    context.user_data.pop('awaiting_amount', None)
                    
                    keyboard = get_payment_methods_menu()
                    
                    await update.message.reply_text(
                        f"💳 **Add Balance:** ₹{amount}\n\n👇 **Please select payment method:**",
                        reply_markup=keyboard,
                        parse_mode='Markdown'
                    )
                except ValueError:
                    await update.message.reply_text("❌ Invalid amount! Please send a valid number.")
                return
            elif 'awaiting_reject_reason' in context.user_data and context.user_data['awaiting_reject_reason']:
                await handle_reject_reason(update, context)
                return
            elif text.startswith('/approve_'):
                await approve_payment(update, context)
                return
            elif text.startswith('/reject_'):
                await reject_payment(update, context)
                return
            # Check if this is an adjustbalance command (handle it separately)
            elif text.startswith('/adjustbalance'):
                # یہاں ہم adjustbalance کمانڈ کو ہینڈل کریں گے
                parts = text.split()
                if len(parts) == 3:
                    await adjust_balance_handler(update, context)
                else:
                    await update.message.reply_text("❌ Invalid format! Use: `/adjustbalance USER_ID AMOUNT`\n\n**Examples:**\n• `/adjustbalance 1234567 +500` - Add ₹500\n• `/adjustbalance 1234567 -200` - Subtract ₹200", parse_mode='Markdown')
                return
                
    except Exception as e:
        logger.error(f"Error in handle_text_message: {e}")

# ========== FIXED ADJUST BALANCE HANDLER ==========
async def adjust_balance_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle adjustbalance command - FIXED AND WORKING VERSION"""
    try:
        admin_id = update.effective_user.id
        
        # Check if user is admin
        if not is_admin(admin_id):
            await update.message.reply_text("❌ Unauthorized! Only admins can manage user balance.")
            return
        
        # Check if admin has permission
        if not has_permission(admin_id, 'adjust_balance'):
            await update.message.reply_text("❌ You don't have permission to adjust user balance!")
            return
        
        command_text = update.message.text
        parts = command_text.split()
        
        if len(parts) != 3:
            await update.message.reply_text("❌ Invalid format! Use: `/adjustbalance USER_ID AMOUNT`\n\n**Examples:**\n• `/adjustbalance 1234567 +500` - Add ₹500\n• `/adjustbalance 1234567 -200` - Subtract ₹200", parse_mode='Markdown')
            return
        
        try:
            target_user_id = int(parts[1])
        except ValueError:
            await update.message.reply_text("❌ Invalid user ID! Please enter a valid number.")
            return
        
        amount_str = parts[2]
        
        # Parse amount with + or - sign
        try:
            if amount_str.startswith('+'):
                amount = float(amount_str[1:])
                operation = 'add'
            elif amount_str.startswith('-'):
                amount = float(amount_str[1:])
                operation = 'subtract'
            else:
                await update.message.reply_text("❌ Invalid amount format! Use +AMOUNT or -AMOUNT\n\n**Examples:**\n• `/adjustbalance 1234567 +500`\n• `/adjustbalance 1234567 -200`")
                return
        except ValueError:
            await update.message.reply_text("❌ Invalid amount! Please enter a valid number.")
            return
        
        if amount <= 0:
            await update.message.reply_text("❌ Amount must be greater than 0!")
            return
        
        conn = sqlite3.connect('atoplay_bot.db')
        cursor = conn.cursor()
        
        # Check if user exists
        cursor.execute('SELECT user_id, telegram_id, username, balance FROM users WHERE telegram_id = ?', (target_user_id,))
        user_data = cursor.fetchone()
        
        if not user_data:
            await update.message.reply_text(f"❌ User with ID {target_user_id} not found!")
            conn.close()
            return
        
        user_db_id, target_telegram_id, username, current_balance = user_data
        
        # Calculate new balance
        if operation == 'add':
            new_balance = current_balance + amount
            operation_text = "added"
            emoji = "➕"
        else:  # subtract
            if current_balance < amount:
                await update.message.reply_text(f"❌ User doesn't have enough balance! Current balance: ₹{current_balance}")
                conn.close()
                return
            new_balance = current_balance - amount
            operation_text = "subtracted"
            emoji = "➖"
        
        # Update user balance
        cursor.execute('UPDATE users SET balance = ? WHERE user_id = ?',
                       (new_balance, user_db_id))
        
        # Create transaction record
        cursor.execute('''INSERT INTO transactions 
                          (user_id, amount, payment_method, status, admin_id) 
                          VALUES (?, ?, 'admin_adjustment', 'approved', ?)''',
                       (user_db_id, amount if operation == 'add' else -amount, admin_id))
        
        conn.commit()
        
        # Log admin action
        log_admin_action(admin_id, 'adjust_balance', user_db_id, 
                        f"{operation_text} ₹{amount}. Old: ₹{current_balance}, New: ₹{new_balance}")
        
        # Notify user if they haven't blocked the bot
        user_notified = False
        try:
            user_message = f"""📢 **Balance Update**

Your account balance has been updated by admin.

{emoji} **Details:**
• **Operation:** {operation_text.capitalize()} ₹{amount}
• **Previous Balance:** ₹{current_balance}
• **New Balance:** ₹{new_balance}
• **Updated by:** Admin
• **Time:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

💰 You can now use your balance to purchase keys!

📞 **Contact:** @Aarifseller for any queries."""
            
            await context.bot.send_message(
                chat_id=target_user_id,
                text=user_message,
                parse_mode='Markdown'
            )
            user_notified = True
            logger.info(f"Balance update notification sent to user: {target_user_id}")
        except Exception as e:
            logger.error(f"Failed to notify user {target_user_id}: {e}")
            user_notified = False
        
        # Send confirmation to admin
        if user_notified:
            notification_status = "✅ User has been notified."
        else:
            notification_status = "⚠️ User could not be notified (may have blocked the bot)."
        
        admin_message = f"""✅ **Balance Updated Successfully!**

👤 **User:** @{username if username else 'No username'} ({target_user_id})
{emoji} **Operation:** {operation_text.capitalize()} ₹{amount}
💰 **Previous Balance:** ₹{current_balance}
💰 **New Balance:** ₹{new_balance}
👤 **Updated by:** Admin ({admin_id})
⏰ **Time:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

{notification_status}"""
        
        await update.message.reply_text(admin_message, parse_mode='Markdown')
        
        conn.close()
        logger.info(f"Admin {admin_id} {operation_text} ₹{amount} for user {target_user_id}")
        
    except Exception as e:
        logger.error(f"Error in adjust_balance_handler: {e}")
        await update.message.reply_text(f"❌ An error occurred while adjusting balance: {str(e)}")

async def approve_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Approve a payment transaction - WITH KEY DELIVERY AND ADMIN NOTIFICATION"""
    try:
        admin_id = update.effective_user.id
        admin_username = update.effective_user.username or update.effective_user.first_name
        
        # Check if user is admin and has permission
        if not is_admin(admin_id):
            await update.message.reply_text("❌ Unauthorized! Only admins can approve payments.")
            return
        
        if not has_permission(admin_id, 'approve_payments'):
            await update.message.reply_text("❌ You don't have permission to approve payments!")
            return
        
        # Get transaction ID from command
        command_text = update.message.text
        if not command_text.startswith('/approve_'):
            await update.message.reply_text("❌ Invalid command format!")
            return
        
        try:
            transaction_id = int(command_text.replace('/approve_', '').strip())
        except ValueError:
            await update.message.reply_text("❌ Invalid transaction ID!")
            return
        
        conn = sqlite3.connect('atoplay_bot.db')
        cursor = conn.cursor()
        
        # Get transaction details
        cursor.execute('''SELECT t.transaction_id, t.user_id, t.amount, t.status, 
                                 u.telegram_id, u.username, u.balance, u.unique_id,
                                 t.payment_method
                          FROM transactions t
                          JOIN users u ON t.user_id = u.user_id
                          WHERE t.transaction_id = ?''', (transaction_id,))
        
        transaction_data = cursor.fetchone()
        
        if not transaction_data:
            await update.message.reply_text(f"❌ Transaction #{transaction_id} not found!")
            conn.close()
            return
        
        (trans_id, user_db_id, amount, status, user_telegram_id, 
         username, user_balance, unique_id, payment_method) = transaction_data
        
        if status != 'pending':
            await update.message.reply_text(f"❌ Transaction #{transaction_id} is already {status}!")
            conn.close()
            return
        
        # Determine product type from amount
        product_name = ""
        key_type = ""
        if amount == PRODUCT_PRICES['3d']:
            product_name = "3-Day Key"
            key_type = '3d'
        elif amount == PRODUCT_PRICES['10d']:
            product_name = "10-Day Key"
            key_type = '10d'
        elif amount == PRODUCT_PRICES['30d']:
            product_name = "30-Day Key"
            key_type = '30d'
        else:
            # For balance addition, no key needed
            product_name = "Balance Addition"
        
        # If this is for a product purchase (not balance addition), get a key
        key_value = None
        if product_name != "Balance Addition":
            # Get a key from stock
            cursor.execute('''SELECT key_id, key_value FROM keys_stock 
                              WHERE key_type = ? AND status = 'available' 
                              LIMIT 1''', (key_type,))
            
            key_data = cursor.fetchone()
            
            if not key_data:
                await update.message.reply_text(f"❌ No {key_type}-day keys available in stock!")
                conn.close()
                return
            
            key_id, key_value = key_data
            
            # Update key status to 'used' and mark as used
            cursor.execute('''UPDATE keys_stock 
                              SET status = 'used', used_by = ?, used_at = CURRENT_TIMESTAMP
                              WHERE key_id = ?''',
                           (user_db_id, key_id))
        
        # Update transaction status
        cursor.execute('''UPDATE transactions 
                          SET status = 'approved', admin_id = ?
                          WHERE transaction_id = ?''',
                       (admin_id, transaction_id))
        
        # Update user balance
        new_balance = user_balance + amount
        cursor.execute('UPDATE users SET balance = ? WHERE user_id = ?',
                       (new_balance, user_db_id))
        
        # If this was a product purchase, add to user_keys
        if key_value:
            cursor.execute('''INSERT INTO user_keys (user_id, key_value, key_type) 
                              VALUES (?, ?, ?)''',
                           (user_db_id, key_value, key_type))
            
            # ========== DELETE KEY FROM STOCK COMPLETELY ==========
            cursor.execute('''DELETE FROM keys_stock 
                              WHERE key_id = ?''', (key_id,))
        
        conn.commit()
        
        # Log admin action
        log_admin_action(admin_id, 'approve_payment', user_db_id, f"Transaction #{transaction_id} - ₹{amount}")
        
        # Send notification to user
        try:
            if key_value:
                # Product purchase - send key
                days = 3 if key_type == '3d' else (10 if key_type == '10d' else 30)
                user_message = f"""✅ **Payment Approved!**

🎉 Congratulations! Your payment has been approved.

📋 **Transaction Details:**
• **Transaction ID:** #{transaction_id}
• **Product:** {product_name}
• **Amount:** ₹{amount}
• **Status:** ✅ Approved
• **Approved by:** Admin

💰 **Your New Balance:** ₹{new_balance}

🔑 **Your Key:** `{key_value}`

📋 **Instructions:**
1. Open Atoplay application
2. Go to settings or activation section
3. Enter the key: `{key_value}`
4. Enjoy your {days} days subscription!

📞 **Contact:** @Aarifseller for any queries."""
            else:
                # Balance addition
                user_message = f"""✅ **Payment Approved!**

🎉 Congratulations! Your payment has been approved.

📋 **Transaction Details:**
• **Transaction ID:** #{transaction_id}
• **Amount:** ₹{amount}
• **Status:** ✅ Approved
• **Approved by:** Admin

💰 **Your New Balance:** ₹{new_balance}

💸 You can now use your balance to purchase keys!
Use /buy to get started.

📞 **Contact:** @Aarifseller for any queries."""
            
            await context.bot.send_message(
                chat_id=user_telegram_id,
                text=user_message,
                parse_mode='Markdown'
            )
        except Exception as e:
            logger.error(f"Failed to notify user {user_telegram_id}: {e}")
        
        # ========== NOTIFY ALL ADMINS ABOUT KEY SALE (if it was a product purchase) ==========
        if key_value:
            await notify_admins_about_key_sale(
                context=context,
                user_id=user_telegram_id,
                username=username,
                product_name=product_name,
                key_value=key_value,
                key_type=key_type,
                amount=amount,
                payment_method=payment_method if payment_method else "manual_approval"
            )
        
        # Send confirmation to admin
        if key_value:
            admin_message = f"""✅ **Payment Approved Successfully!**

📋 **Transaction Details:**
• **Transaction ID:** #{transaction_id}
• **User:** @{username} ({user_telegram_id})
• **Product:** {product_name}
• **Amount:** ₹{amount}
• **Status:** ✅ Approved
• **Previous Balance:** ₹{user_balance}
• **New Balance:** ₹{new_balance}
• **Key:** `{key_value}`

✅ User has been notified with key.
✅ Key has been removed from stock."""
        else:
            admin_message = f"""✅ **Payment Approved Successfully!**

📋 **Transaction Details:**
• **Transaction ID:** #{transaction_id}
• **User:** @{username} ({user_telegram_id})
• **Amount:** ₹{amount}
• **Status:** ✅ Approved
• **Previous Balance:** ₹{user_balance}
• **New Balance:** ₹{new_balance}

✅ User has been notified."""
        
        await update.message.reply_text(admin_message, parse_mode='Markdown')
        
        conn.close()
        logger.info(f"Transaction #{transaction_id} approved by admin {admin_id}")
        
    except Exception as e:
        logger.error(f"Error in approve_payment: {e}")

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle photo messages (payment screenshots)"""
    try:
        if not update.message or not update.message.photo:
            return
        
        user_id = update.message.from_user.id
        username = update.message.from_user.username or update.message.from_user.first_name
        
        logger.info(f"Photo received from user: {user_id}")
        
        # Check if user is blocked
        conn = sqlite3.connect('atoplay_bot.db')
        cursor = conn.cursor()
        cursor.execute('SELECT is_blocked FROM users WHERE telegram_id = ?', (user_id,))
        user_data = cursor.fetchone()
        
        if user_data and user_data[0] == 1:
            await update.message.reply_text("❌ You are blocked from using this bot!")
            conn.close()
            return
        
        # Check if this is for QR code setup
        if context.user_data.get('awaiting_upi_qr_code'):
            await handle_upi_qr_code_setup(update, context)
            conn.close()
            return
        
        if context.user_data.get('awaiting_binance_qr_code'):
            await handle_binance_qr_code_setup(update, context)
            conn.close()
            return
        
        # Check if we're expecting a screenshot
        if 'awaiting_screenshot' not in context.user_data or not context.user_data['awaiting_screenshot']:
            await update.message.reply_text("⚠️ I'm not expecting a screenshot right now. Please use /buy to start a purchase.")
            conn.close()
            return
        
        # Get the photo (largest size)
        photo = update.message.photo[-1]
        file_id = photo.file_id
        
        # Get user info
        cursor.execute('SELECT user_id, unique_id FROM users WHERE telegram_id = ?', (user_id,))
        user_data = cursor.fetchone()
        
        if not user_data:
            await update.message.reply_text("❌ User not found! Please use /start first.")
            conn.close()
            return
        
        user_db_id, unique_id = user_data
        
        # Determine payment purpose and amount
        purpose = "Product Purchase" if 'selected_product' in context.user_data else "Add Balance"
        
        if 'selected_product' in context.user_data:
            product = context.user_data.get('selected_product')
            amount = product['price']
            product_name = product['name']
        elif 'amount' in context.user_data:
            amount = context.user_data.get('amount')
            product_name = "Balance Addition"
        else:
            amount = 0
            product_name = "Unknown"
        
        payment_method = context.user_data.get('payment_method', 'unknown')
        payment_method_name = PAYMENT_METHODS.get(payment_method, {}).get('name', 'Unknown')
        
        # Save transaction to database
        cursor.execute('''INSERT INTO transactions 
                          (user_id, amount, payment_method, screenshot, status) 
                          VALUES (?, ?, ?, ?, 'pending')''',
                       (user_db_id, amount, payment_method, file_id))
        conn.commit()
        transaction_id = cursor.lastrowid
        
        conn.close()
        
        # Send confirmation to user
        await update.message.reply_text(
            f"""✅ **Screenshot Received!**

📋 **Transaction Details:**
• **Transaction ID:** {transaction_id}
• **Purpose:** {purpose}
• **Amount:** ₹{amount}
• **Status:** ⏳ Pending

✅ Your payment screenshot has been received and forwarded to admin for verification.

⏳ Please wait for admin approval. You will be notified once approved.

📞 **Contact:** @Aarifseller if you have any questions."""
        )
        
        # Forward screenshot to all admins with details
        caption = f"""🆕 **Payment Request #{transaction_id}**

👤 **User:** @{username} ({user_id})
🆔 **Unique ID:** {unique_id}
💰 **Amount:** ₹{amount}
🎯 **Purpose:** {purpose}
📦 **Product:** {product_name}
💳 **Method:** {payment_method_name}
⏰ **Time:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
📊 **Status:** ⏳ Pending

**Actions:**
/approve_{transaction_id} - Approve payment
/reject_{transaction_id} - Reject payment"""
        
        # Forward to all admins with permission
        admins = get_all_admins()
        for admin_id, admin_name, _ in admins:
            if has_permission(admin_id, 'approve_payments'):
                try:
                    # Forward the photo
                    await context.bot.forward_message(
                        chat_id=admin_id,
                        from_chat_id=user_id,
                        message_id=update.message.message_id
                    )
                    
                    # Send details
                    await context.bot.send_message(
                        chat_id=admin_id,
                        text=caption
                    )
                    logger.info(f"Screenshot forwarded to admin: {admin_id}")
                except Exception as e:
                    logger.error(f"Failed to forward to admin {admin_id}: {e}")
        
        # Clear user data
        context.user_data.clear()
        
        logger.info(f"Transaction #{transaction_id} created for user: {user_id}")
        
    except Exception as e:
        logger.error(f"Error in handle_photo: {e}")

async def reject_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Reject a payment transaction"""
    try:
        admin_id = update.effective_user.id
        
        # Check if user is admin and has permission
        if not is_admin(admin_id):
            await update.message.reply_text("❌ Unauthorized! Only admins can reject payments.")
            return
        
        if not has_permission(admin_id, 'approve_payments'):
            await update.message.reply_text("❌ You don't have permission to reject payments!")
            return
        
        # Get transaction ID from command
        command_text = update.message.text
        if not command_text.startswith('/reject_'):
            await update.message.reply_text("❌ Invalid command format!")
            return
        
        try:
            transaction_id = int(command_text.replace('/reject_', '').strip())
        except ValueError:
            await update.message.reply_text("❌ Invalid transaction ID!")
            return
        
        conn = sqlite3.connect('atoplay_bot.db')
        cursor = conn.cursor()
        
        # Get transaction details
        cursor.execute('''SELECT t.transaction_id, t.user_id, t.amount, t.status, 
                                 u.telegram_id, u.username
                          FROM transactions t
                          JOIN users u ON t.user_id = u.user_id
                          WHERE t.transaction_id = ?''', (transaction_id,))
        
        transaction_data = cursor.fetchone()
        
        if not transaction_data:
            await update.message.reply_text(f"❌ Transaction #{transaction_id} not found!")
            conn.close()
            return
        
        (trans_id, user_db_id, amount, status, user_telegram_id, username) = transaction_data
        
        if status != 'pending':
            await update.message.reply_text(f"❌ Transaction #{transaction_id} is already {status}!")
            conn.close()
            return
        
        # Ask for reason
        context.user_data['awaiting_reject_reason'] = True
        context.user_data['reject_transaction_id'] = transaction_id
        context.user_data['reject_user_id'] = user_telegram_id
        context.user_data['reject_amount'] = amount
        
        await update.message.reply_text(
            f"""❌ **Reject Payment #{transaction_id}**

**User:** @{username}
**Amount:** ₹{amount}

Please provide reason for rejection:"""
        )
        
        conn.close()
        
    except Exception as e:
        logger.error(f"Error in reject_payment: {e}")

async def handle_reject_reason(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle rejection reason"""
    try:
        admin_id = update.effective_user.id
        
        if not is_admin(admin_id):
            return
        
        if not has_permission(admin_id, 'approve_payments'):
            return
        
        if 'awaiting_reject_reason' not in context.user_data:
            return
        
        reason = update.message.text
        transaction_id = context.user_data.get('reject_transaction_id')
        user_telegram_id = context.user_data.get('reject_user_id')
        amount = context.user_data.get('reject_amount')
        
        conn = sqlite3.connect('atoplay_bot.db')
        cursor = conn.cursor()
        
        # Update transaction status
        cursor.execute('''UPDATE transactions 
                          SET status = 'rejected', admin_id = ?
                          WHERE transaction_id = ?''',
                       (admin_id, transaction_id))
        
        conn.commit()
        
        # Log admin action
        cursor.execute('SELECT user_id FROM users WHERE telegram_id = ?', (user_telegram_id,))
        user_data = cursor.fetchone()
        if user_data:
            log_admin_action(admin_id, 'reject_payment', user_data[0], 
                            f"Transaction #{transaction_id} - ₹{amount} - Reason: {reason}")
        
        # Send notification to user
        try:
            await context.bot.send_message(
                chat_id=user_telegram_id,
                text=f"""❌ **Payment Rejected!**

📋 **Transaction Details:**
• **Transaction ID:** #{transaction_id}
• **Amount:** ₹{amount}
• **Status:** ❌ Rejected
• **Reason:** {reason}

⚠️ If you believe this is a mistake, please contact @Aarifseller with your payment proof.

📞 **Contact:** @Aarifseller for assistance."""
            )
        except Exception as e:
            logger.error(f"Failed to notify user {user_telegram_id}: {e}")
        
        # Clear user data
        context.user_data.clear()
        
        # Send confirmation to admin
        await update.message.reply_text(
            f"""✅ **Payment Rejected Successfully!**

📋 **Transaction Details:**
• **Transaction ID:** #{transaction_id}
• **Amount:** ₹{amount}
• **Reason:** {reason}

✅ User has been notified."""
        )
        
        conn.close()
        logger.info(f"Transaction #{transaction_id} rejected by admin {admin_id}")
        
    except Exception as e:
        logger.error(f"Error in handle_reject_reason: {e}")

# ========== EXISTING FUNCTIONS ==========
async def handle_add_key(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle adding keys by admin - CASE SENSITIVE (EXACT CASE PRESERVED)"""
    admin_id = update.effective_user.id
    
    if not is_admin(admin_id):
        await update.message.reply_text("❌ Unauthorized!")
        return
    
    if not has_permission(admin_id, 'add_keys'):
        await update.message.reply_text("❌ You don't have permission to add keys!")
        return
    
    command_text = update.message.text
    parts = command_text.split()
    
    if len(parts) < 2:
        await update.message.reply_text("❌ Invalid format! Use: `/addkey_3d KEYVALUE`", parse_mode='Markdown')
        return
    
    command = parts[0]
    
    # Extract key value exactly as admin sent it (including case)
    key_value = parts[1]
    
    # If key has spaces or multiple parts, join them
    if len(parts) > 2:
        key_value = " ".join(parts[1:])
    
    # Keep the EXACT case as sent by admin - NO UPPERCASE CONVERSION
    # Determine key type from command
    if command == "/addkey_3d":
        key_type = '3d'
    elif command == "/addkey_10d":
        key_type = '10d'
    elif command == "/addkey_30d":
        key_type = '30d'
    else:
        await update.message.reply_text("❌ Invalid command! Use /addkey_3d, /addkey_10d, or /addkey_30d")
        return
    
    conn = sqlite3.connect('atoplay_bot.db')
    cursor = conn.cursor()
    
    try:
        # Check if key already exists (CASE SENSITIVE check)
        cursor.execute('SELECT key_value FROM keys_stock WHERE key_value = ?', (key_value,))
        existing_key = cursor.fetchone()
        
        if existing_key:
            await update.message.reply_text(f"❌ Key '{key_value}' already exists!")
            conn.close()
            return
        
        # Add the key with exact case
        cursor.execute('INSERT INTO keys_stock (key_value, key_type) VALUES (?, ?)', 
                      (key_value, key_type))
        conn.commit()
        
        # Log admin action
        log_admin_action(admin_id, 'add_key', 0, f"{key_type} key: {key_value}")
        
        # Get updated stock
        stock_info = get_stock_info()
        
        await update.message.reply_text(
            f"""✅ **Key Added Successfully!**

🔑 **Key:** `{key_value}`
📦 **Type:** {key_type.upper()}-Day Key
💰 **Price:** ₹{PRODUCT_PRICES[key_type]}
👤 **Added by:** Admin

📊 **Updated Stock:**
• 3-Day Keys: {stock_info.get('3d', 0)} available
• 10-Day Keys: {stock_info.get('10d', 0)} available  
• 30-Day Keys: {stock_info.get('30d', 0)} available""",
            parse_mode='Markdown'
        )
        
        logger.info(f"Admin {admin_id} added {key_type} key: {key_value} (exact case preserved)")
        
    except Exception as e:
        await update.message.reply_text(f"❌ Error adding key: {str(e)}")
    finally:
        conn.close()

async def handle_delete_key(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle deleting keys by admin - CASE SENSITIVE (EXACT MATCH)"""
    admin_id = update.effective_user.id
    
    if not is_admin(admin_id):
        await update.message.reply_text("❌ Unauthorized!")
        return
    
    if not has_permission(admin_id, 'delete_keys'):
        await update.message.reply_text("❌ You don't have permission to delete keys!")
        return
    
    command_text = update.message.text
    parts = command_text.split()
    
    if len(parts) < 2:
        await update.message.reply_text("❌ Invalid format! Use: `/delkey KEYVALUE`", parse_mode='Markdown')
        return
    
    # Extract key value exactly as admin sent it (including case)
    key_value = parts[1]
    
    # If key has spaces or multiple parts, join them
    if len(parts) > 2:
        key_value = " ".join(parts[1:])
    
    conn = sqlite3.connect('atoplay_bot.db')
    cursor = conn.cursor()
    
    try:
        # Check if key exists (EXACT CASE SENSITIVE MATCH)
        cursor.execute('''SELECT key_id, key_type, status, key_value 
                          FROM keys_stock 
                          WHERE key_value = ?''', (key_value,))
        key_data = cursor.fetchone()
        
        if not key_data:
            # Try case-insensitive search for better UX
            cursor.execute('''SELECT key_id, key_type, status, key_value 
                              FROM keys_stock 
                              WHERE LOWER(key_value) = LOWER(?)''', (key_value,))
            key_data = cursor.fetchone()
            
            if not key_data:
                await update.message.reply_text(f"❌ Key '{key_value}' not found!")
                conn.close()
                return
            else:
                key_id, key_type, status, actual_key_value = key_data
                await update.message.reply_text(f"⚠️ **Note:** Key found with different case: '{actual_key_value}'", parse_mode='Markdown')
        else:
            key_id, key_type, status, actual_key_value = key_data
        
        # Delete the key using exact key value from database
        cursor.execute('DELETE FROM keys_stock WHERE key_id = ?', (key_id,))
        conn.commit()
        
        # Log admin action
        log_admin_action(admin_id, 'delete_key', 0, f"{key_type} key: {actual_key_value} (Status: {status})")
        
        # Get updated stock
        stock_info = get_stock_info()
        
        await update.message.reply_text(
            f"""✅ **Key Deleted Successfully!**

🔑 **Key:** `{actual_key_value}`
📦 **Type:** {key_type.upper()}-Day Key
📊 **Status:** {status}
👤 **Deleted by:** Admin

📊 **Updated Stock:**
• 3-Day Keys: {stock_info.get('3d', 0)} available
• 10-Day Keys: {stock_info.get('10d', 0)} available  
• 30-Day Keys: {stock_info.get('30d', 0)} available""",
            parse_mode='Markdown'
        )
        
        logger.info(f"Admin {admin_id} deleted {key_type} key: {actual_key_value}")
        
    except Exception as e:
        await update.message.reply_text(f"❌ Error deleting key: {str(e)}")
    finally:
        conn.close()

async def handle_price_change(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle price changes by admin"""
    admin_id = update.effective_user.id
    
    if not is_admin(admin_id):
        await update.message.reply_text("❌ Unauthorized!")
        return
    
    if not has_permission(admin_id, 'change_prices'):
        await update.message.reply_text("❌ You don't have permission to change prices!")
        return
    
    command_text = update.message.text
    parts = command_text.split()
    
    if len(parts) != 2:
        await update.message.reply_text("❌ Invalid format! Use: `/price_3d NEW_PRICE`", parse_mode='Markdown')
        return
    
    command = parts[0]
    try:
        new_price = int(parts[1])
        if new_price <= 0:
            await update.message.reply_text("❌ Price must be greater than 0!")
            return
    except ValueError:
        await update.message.reply_text("❌ Invalid price! Please enter a valid number.")
        return
    
    # Determine product type from command
    if command == "/price_3d":
        product_type = '3d'
        product_name = '3-Day Key'
        old_price = PRODUCT_PRICES['3d']
        PRODUCT_PRICES['3d'] = new_price
    elif command == "/price_10d":
        product_type = '10d'
        product_name = '10-Day Key'
        old_price = PRODUCT_PRICES['10d']
        PRODUCT_PRICES['10d'] = new_price
    elif command == "/price_30d":
        product_type = '30d'
        product_name = '30-Day Key'
        old_price = PRODUCT_PRICES['30d']
        PRODUCT_PRICES['30d'] = new_price
    else:
        await update.message.reply_text("❌ Invalid command! Use /price_3d, /price_10d, or /price_30d")
        return
    
    # Save price to database
    conn = sqlite3.connect('atoplay_bot.db')
    cursor = conn.cursor()
    
    cursor.execute('''INSERT OR REPLACE INTO settings (setting_key, setting_value) 
                      VALUES (?, ?)''',
                   (f'price_{product_type}', str(new_price)))
    
    conn.commit()
    conn.close()
    
    # Log admin action
    log_admin_action(admin_id, 'change_price', 0, f"{product_name}: ₹{old_price} → ₹{new_price}")
    
    await update.message.reply_text(
        f"""✅ **Price Updated Successfully!**

📦 **Product:** {product_name}
💰 **Old Price:** ₹{old_price}
💰 **New Price:** ₹{new_price}
👤 **Changed by:** Admin

✅ Price has been updated for all users.""",
        parse_mode='Markdown'
    )
    
    logger.info(f"Admin {admin_id} changed {product_name} price: ₹{old_price} → ₹{new_price}")

async def show_stock(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show current stock"""
    admin_id = update.effective_user.id
    
    if not is_admin(admin_id):
        await update.message.reply_text("❌ Unauthorized!")
        return
    
    if not has_permission(admin_id, 'view_stock'):
        await update.message.reply_text("❌ You don't have permission to view stock!")
        return
    
    stock_info = get_stock_info()
    
    conn = sqlite3.connect('atoplay_bot.db')
    cursor = conn.cursor()
    
    # Get all keys with details
    cursor.execute('''SELECT key_type, key_value, status, 
                             strftime('%Y-%m-%d %H:%M', created_at) as created
                      FROM keys_stock 
                      ORDER BY key_type, created_at DESC''')
    
    all_keys = cursor.fetchall()
    conn.close()
    
    # Group keys by type
    keys_by_type = {'3d': [], '10d': [], '30d': []}
    
    for key_type, key_value, status, created in all_keys:
        keys_by_type[key_type].append(f"`{key_value}` - {status} ({created})")
    
    text = f"""📊 **STOCK REPORT**

📈 **Available Keys:**
• 3-Day Keys: {stock_info.get('3d', 0)} available - ₹{PRODUCT_PRICES['3d']}
• 10-Day Keys: {stock_info.get('10d', 0)} available - ₹{PRODUCT_PRICES['10d']}
• 30-Day Keys: {stock_info.get('3d', 0)} available - ₹{PRODUCT_PRICES['30d']}

🔑 **All Keys:**

📅 **3-Day Keys:**"""
    
    if keys_by_type['3d']:
        for key_info in keys_by_type['3d']:
            text += f"\n• {key_info}"
    else:
        text += "\n• No 3-day keys"
    
    text += "\n\n📅 **10-Day Keys:**"
    if keys_by_type['10d']:
        for key_info in keys_by_type['10d']:
            text += f"\n• {key_info}"
    else:
        text += "\n• No 10-day keys"
    
    text += "\n\n📅 **30-Day Keys:**"
    if keys_by_type['30d']:
        for key_info in keys_by_type['30d']:
            text += f"\n• {key_info}"
    else:
        text += "\n• No 30-day keys"
    
    # Add back button for callback
    if update.callback_query:
        keyboard = [[InlineKeyboardButton("🔙 Back to Stock Menu", callback_data='admin_stock')]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.callback_query.edit_message_text(text, parse_mode='Markdown', reply_markup=reply_markup)
    else:
        await update.message.reply_text(text, parse_mode='Markdown')

async def view_prices(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """View all prices"""
    admin_id = update.effective_user.id
    
    if not is_admin(admin_id):
        await update.message.reply_text("❌ Unauthorized!")
        return
    
    if not has_permission(admin_id, 'view_payments'):
        await update.message.reply_text("❌ You don't have permission to view prices!")
        return
    
    text = f"""💰 **CURRENT PRICES**

📦 **3-Day Key:** ₹{PRODUCT_PRICES['3d']}
📦 **10-Day Key:** ₹{PRODUCT_PRICES['10d']}
📦 **30-Day Key:** ₹{PRODUCT_PRICES['30d']}

📝 **To Change Prices:**
• `/price_3d NEW_PRICE` - Change 3-day price
• `/price_10d NEW_PRICE` - Change 10-day price  
• `/price_30d NEW_PRICE` - Change 30-day price

**Examples:**
• `/price_3d 300`
• `/price_10d 600`
• `/price_30d 1300`"""
    
    # Add back button for callback
    if update.callback_query:
        keyboard = [[InlineKeyboardButton("🔙 Back to Price Menu", callback_data='admin_prices')]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.callback_query.edit_message_text(text, parse_mode='Markdown', reply_markup=reply_markup)
    else:
        await update.message.reply_text(text, parse_mode='Markdown')

async def view_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """View all users summary - FIXED VERSION"""
    admin_id = update.effective_user.id
    
    if not is_admin(admin_id):
        await update.message.reply_text("❌ Unauthorized!")
        return
    
    if not has_permission(admin_id, 'view_users'):
        await update.message.reply_text("❌ You don't have permission to view users!")
        return
    
    conn = sqlite3.connect('atoplay_bot.db')
    cursor = conn.cursor()
    
    try:
        # Get user statistics
        cursor.execute('SELECT COUNT(*) FROM users')
        total_users = cursor.fetchone()[0]
        
        cursor.execute('SELECT COUNT(*) FROM users WHERE is_blocked = 1')
        blocked_users = cursor.fetchone()[0]
        
        cursor.execute('SELECT COUNT(*) FROM users WHERE is_admin = 1')
        admin_users = cursor.fetchone()[0]
        
        # Get today's buyers
        cursor.execute('''SELECT COUNT(DISTINCT t.user_id) 
                          FROM transactions t
                          WHERE t.status = 'approved' 
                          AND DATE(t.created_at) = DATE('now')''')
        today_buyers_result = cursor.fetchone()
        today_buyers = today_buyers_result[0] if today_buyers_result else 0
        
        # Get recent users
        cursor.execute('''SELECT telegram_id, username, unique_id, balance, is_blocked,
                                 strftime('%Y-%m-%d %H:%M', created_at) as created
                          FROM users 
                          ORDER BY created_at DESC 
                          LIMIT 10''')
        
        recent_users = cursor.fetchall()
        
        text = f"""👥 **USER STATISTICS**

📊 **Overview:**
• **Total Users:** {total_users}
• **Active Users:** {total_users - blocked_users}
• **Blocked Users:** {blocked_users}
• **Admin Users:** {admin_users}
• **Today's Buyers:** {today_buyers}

👤 **Recent Users (Last 10):**"""
        
        for i, (telegram_id, username, unique_id, balance, is_blocked, created) in enumerate(recent_users, 1):
            status = "🚫" if is_blocked == 1 else "✅"
            username_display = f"@{username}" if username else "No username"
            text += f"\n\n{i}. {status} **Telegram ID:** {telegram_id}"
            text += f"\n   **User:** {username_display}"
            text += f"\n   **Unique ID:** {unique_id}"
            text += f"\n   **Balance:** ₹{balance}"
            text += f"\n   **Joined:** {created}"
        
        text += "\n\n📝 **User Management Commands:**"
        text += "\n• `/block USER_ID REASON` - Block a user"
        text += "\n• `/unblock USER_ID` - Unblock a user"  
        text += "\n• `/userinfo USER_ID` - Get user details"
        text += "\n• `/adjustbalance USER_ID AMOUNT` - Manage user balance"
    
    except Exception as e:
        logger.error(f"Error in view_users: {e}")
        text = "❌ An error occurred while fetching user data. Please try again."
    finally:
        conn.close()

    # Add back button for callback
    if update.callback_query:
        keyboard = [[InlineKeyboardButton("🔙 Back to User Menu", callback_data='admin_users')]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.callback_query.edit_message_text(text, parse_mode='Markdown', reply_markup=reply_markup)
    else:
        await update.message.reply_text(text, parse_mode='Markdown')

async def view_payment_methods(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """View all payment methods"""
    admin_id = update.effective_user.id
    
    if not is_admin(admin_id):
        await update.message.reply_text("❌ Unauthorized!")
        return
    
    if not has_permission(admin_id, 'view_payments'):
        await update.message.reply_text("❌ You don't have permission to view payment methods!")
        return
    
    # Update payment methods
    update_payment_methods_global()
    
    text = """💳 **PAYMENT METHODS**

📋 **Current Payment Details:**"""
    
    for method_key, method_data in PAYMENT_METHODS.items():
        text += f"\n\n🔸 **{method_data['name']}:**"
        
        if method_key in ['easypaisa', 'jazzcash', 'upi']:
            if method_data.get('number'):
                text += f"\n   • **Number/UPI ID:** {method_data['number']}"
            if method_data.get('account_name'):
                text += f"\n   • **Account Name:** {method_data['account_name']}"
            if method_key == 'upi' and method_data.get('qr_code'):
                text += f"\n   • **QR Code:** ✅ Available"
        elif method_key == 'binance':
            if method_data.get('pay_id'):
                text += f"\n   • **Pay ID:** {method_data['pay_id']}"
            if method_data.get('qr_code'):
                text += f"\n   • **QR Code:** ✅ Available"
    
    text += "\n\n📝 **Update Commands:**"
    text += "\n• `/seteasypaisa NUMBER \"ACCOUNT NAME\"` - Update Easypaisa"
    text += "\n• `/setjazzcash NUMBER \"ACCOUNT NAME\"` - Update JazzCash"
    text += "\n• `/setbinance PAY_ID` - Update Binance Pay ID"
    text += "\n• `/setupi UPI_ID \"ACCOUNT NAME\"` - Update UPI details"
    text += "\n• `/setupiqr` - Update UPI QR code (send photo after command)"
    text += "\n• `/setbinanceqr` - Update Binance QR code (send photo after command)"

    text += "\n\n**Examples:**"
    text += "\n• `/seteasypaisa 03431178575 \"John Doe\"`"
    text += "\n• `/setjazzcash 03001234567 \"Ali Khan\"`"
    text += "\n• `/setbinance 335277914`"
    text += "\n• `/setupi user@upi \"Account Name\"`"

    # Add back button for callback
    if update.callback_query:
        keyboard = [[InlineKeyboardButton("🔙 Back to Payment Menu", callback_data='admin_payments')]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.callback_query.edit_message_text(text, parse_mode='Markdown', reply_markup=reply_markup)
    else:
        await update.message.reply_text(text, parse_mode='Markdown')

async def show_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show bot statistics - FIXED VERSION"""
    admin_id = update.effective_user.id
    
    if not is_admin(admin_id):
        await update.message.reply_text("❌ Unauthorized!")
        return
    
    if not has_permission(admin_id, 'view_stats'):
        await update.message.reply_text("❌ You don't have permission to view statistics!")
        return
    
    conn = sqlite3.connect('atoplay_bot.db')
    cursor = conn.cursor()
    
    try:
        # Get total users
        cursor.execute('SELECT COUNT(*) FROM users')
        total_users_result = cursor.fetchone()
        total_users = total_users_result[0] if total_users_result else 0
        
        # Get total blocked users
        cursor.execute('SELECT COUNT(*) FROM users WHERE is_blocked = 1')
        blocked_users_result = cursor.fetchone()
        blocked_users = blocked_users_result[0] if blocked_users_result else 0
        
        # Get total admins
        cursor.execute('SELECT COUNT(*) FROM users WHERE is_admin = 1')
        total_admins_result = cursor.fetchone()
        total_admins = total_admins_result[0] if total_admins_result else 0
        
        # Get total transactions
        cursor.execute('SELECT COUNT(*) FROM transactions')
        total_transactions_result = cursor.fetchone()
        total_transactions = total_transactions_result[0] if total_transactions_result else 0
        
        # Get total approved transactions amount
        cursor.execute('SELECT SUM(amount) FROM transactions WHERE status = "approved"')
        total_revenue_result = cursor.fetchone()
        total_revenue = total_revenue_result[0] if total_revenue_result else 0
        
        # Get today's transactions
        cursor.execute('''SELECT COUNT(*), SUM(amount) FROM transactions 
                          WHERE DATE(created_at) = DATE('now') AND status = "approved"''')
        today_data = cursor.fetchone()
        today_transactions = today_data[0] if today_data and today_data[0] else 0
        today_revenue = today_data[1] if today_data and today_data[1] else 0
        
        # Get stock info
        stock_info = get_stock_info()
        
        # Get total keys sold
        cursor.execute('SELECT COUNT(*) FROM keys_stock WHERE status = "used"')
        total_keys_sold_result = cursor.fetchone()
        total_keys_sold = total_keys_sold_result[0] if total_keys_sold_result else 0
        
        # Get today's keys sold
        cursor.execute('''SELECT COUNT(*) FROM keys_stock 
                          WHERE status = "used" AND DATE(used_at) = DATE('now')''')
        today_keys_sold_result = cursor.fetchone()
        today_keys_sold = today_keys_sold_result[0] if today_keys_sold_result else 0
        
    except Exception as e:
        logger.error(f"Error in show_stats: {e}")
        text = "❌ An error occurred while fetching statistics. Please try again."
        return
    finally:
        conn.close()
    
    text = f"""📊 **BOT STATISTICS**

👥 **Users:**
• **Total Users:** {total_users}
• **Blocked Users:** {blocked_users}
• **Active Users:** {total_users - blocked_users}
• **Total Admins:** {total_admins}

💰 **Revenue:**
• **Total Revenue:** ₹{total_revenue}
• **Today's Revenue:** ₹{today_revenue}

💳 **Transactions:**
• **Total Transactions:** {total_transactions}
• **Today's Transactions:** {today_transactions}

📦 **Stock & Sales:**
• **3-Day Keys:** {stock_info.get('3d', 0)} available
• **10-Day Keys:** {stock_info.get('10d', 0)} available
• **30-Day Keys:** {stock_info.get('30d', 0)} available
• **Total Keys Sold:** {total_keys_sold}
• **Today's Keys Sold:** {today_keys_sold}

⏰ **Last Updated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"""
    
    # Add back button for callback
    if update.callback_query:
        keyboard = [[InlineKeyboardButton("🔙 Back to Admin Panel", callback_data='admin_back')]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.callback_query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')
    else:
        await update.message.reply_text(text, parse_mode='Markdown')

async def check_balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        await update.message.chat.send_action(action="typing")
        
        user_id = update.effective_user.id
        
        conn = sqlite3.connect('atoplay_bot.db')
        cursor = conn.cursor()
        
        cursor.execute('SELECT unique_id, balance, is_blocked FROM users WHERE telegram_id = ?', (user_id,))
        user_data = cursor.fetchone()
        conn.close()
        
        if user_data:
            unique_id, balance, is_blocked = user_data
            
            if is_blocked == 1:
                text = "❌ You are blocked from using this bot!"
            else:
                text = f"""💳 **Your Account**

🆔 **ID:** `{unique_id}`
💰 **Balance:** ₹{balance}

💸 **Add Balance:**
Use /buy → Add Balance

📞 **Contact:** @Aarifseller
📢 **Channel:** @SnakeEngine105

🛒 Use /buy to purchase keys!"""
        else:
            text = "❌ Account not found! Use /start"
        
        await update.message.reply_text(text, parse_mode='Markdown')
        
    except Exception as e:
        logger.error(f"Error in check_balance: {e}")

async def my_keys(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        await update.message.chat.send_action(action="typing")
        
        user_id = update.effective_user.id
        
        conn = sqlite3.connect('atoplay_bot.db')
        cursor = conn.cursor()
        
        cursor.execute('SELECT user_id, unique_id, is_blocked FROM users WHERE telegram_id = ?', (user_id,))
        user_data = cursor.fetchone()
        
        if not user_data:
            await update.message.reply_text("❌ Account not found! Use /start")
            conn.close()
            return
        
        user_db_id, unique_id, is_blocked = user_data
        
        if is_blocked == 1:
            await update.message.reply_text("❌ You are blocked from using this bot!")
            conn.close()
            return
        
        # Get user's purchased keys
        cursor.execute('''SELECT key_value, key_type, 
                                 strftime('%Y-%m-%d %H:%M', purchased_at) as purchase_time,
                                 status
                          FROM user_keys 
                          WHERE user_id = ? 
                          ORDER BY purchased_at DESC''', (user_db_id,))
        
        keys = cursor.fetchall()
        conn.close()
        
        if not keys:
            text = f"""🔑 **My Keys**

🆔 **Your ID:** `{unique_id}`
📦 **No keys purchased yet.**

🛒 Use /buy to purchase your first key!"""
        else:
            text = f"""🔑 **My Keys**

🆔 **Your ID:** `{unique_id}`
📦 **Total Keys:** {len(keys)}

📋 **Your Purchased Keys:**"""
            
            for i, (key_value, key_type, purchase_time, status) in enumerate(keys, 1):
                days = 3 if key_type == '3d' else (10 if key_type == '10d' else 30)
                text += f"\n\n{i}. 🔑 **Key:** `{key_value}`"
                text += f"\n   📅 **Type:** {days}-Day"
                text += f"\n   🕒 **Purchased:** {purchase_time}"
                text += f"\n   📊 **Status:** {status}"
        
        await update.message.reply_text(text, parse_mode='Markdown')
        
    except Exception as e:
        logger.error(f"Error in my_keys: {e}")

async def block_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Block a user"""
    try:
        admin_id = update.effective_user.id
        
        if not is_admin(admin_id):
            await update.message.reply_text("❌ Unauthorized!")
            return
        
        if not has_permission(admin_id, 'block_users'):
            await update.message.reply_text("❌ You don't have permission to block users!")
            return
        
        command_text = update.message.text
        parts = command_text.split()
        
        if len(parts) < 3:
            await update.message.reply_text("❌ Invalid format! Use: `/block USER_ID REASON`", parse_mode='Markdown')
            return
        
        try:
            target_user_id = int(parts[1])
        except ValueError:
            await update.message.reply_text("❌ Invalid user ID!")
            return
        
        reason = " ".join(parts[2:])
        
        conn = sqlite3.connect('atoplay_bot.db')
        cursor = conn.cursor()
        
        # Check if user exists
        cursor.execute('SELECT telegram_id, username FROM users WHERE telegram_id = ?', (target_user_id,))
        user_data = cursor.fetchone()
        
        if not user_data:
            await update.message.reply_text(f"❌ User with ID {target_user_id} not found!")
            conn.close()
            return
        
        target_telegram_id, username = user_data
        
        # Update user status
        cursor.execute('''UPDATE users 
                          SET is_blocked = 1, blocked_reason = ?, blocked_at = CURRENT_TIMESTAMP
                          WHERE telegram_id = ?''',
                       (reason, target_user_id))
        
        conn.commit()
        
        # Log admin action
        cursor.execute('SELECT user_id FROM users WHERE telegram_id = ?', (target_user_id,))
        target_db_id = cursor.fetchone()[0]
        log_admin_action(admin_id, 'block_user', target_db_id, f"Reason: {reason}")
        
        # Notify user
        try:
            await context.bot.send_message(
                chat_id=target_user_id,
                text=f"""❌ **You have been blocked!**

You have been blocked from using the Atoplay Shop bot.

📋 **Block Details:**
• **Reason:** {reason}
• **Blocked by:** Admin
• **Time:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

⚠️ You can no longer use the bot commands or make purchases.

📞 **Contact:** @Aarifseller for assistance.""",
                parse_mode='Markdown'
            )
        except Exception as e:
            logger.error(f"Failed to notify blocked user {target_user_id}: {e}")
        
        await update.message.reply_text(
            f"""✅ **User Blocked Successfully!**

👤 **User:** @{username} ({target_user_id})
📝 **Reason:** {reason}
⏰ **Time:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

✅ User has been notified.""",
            parse_mode='Markdown'
        )
        
        conn.close()
        logger.info(f"User {target_user_id} blocked by admin {admin_id}")
        
    except Exception as e:
        logger.error(f"Error in block_user: {e}")

async def unblock_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Unblock a user"""
    try:
        admin_id = update.effective_user.id
        
        if not is_admin(admin_id):
            await update.message.reply_text("❌ Unauthorized!")
            return
        
        if not has_permission(admin_id, 'unblock_users'):
            await update.message.reply_text("❌ You don't have permission to unblock users!")
            return
        
        command_text = update.message.text
        parts = command_text.split()
        
        if len(parts) < 2:
            await update.message.reply_text("❌ Invalid format! Use: `/unblock USER_ID`", parse_mode='Markdown')
            return
        
        try:
            target_user_id = int(parts[1])
        except ValueError:
            await update.message.reply_text("❌ Invalid user ID!")
            return
        
        conn = sqlite3.connect('atoplay_bot.db')
        cursor = conn.cursor()
        
        # Check if user exists
        cursor.execute('SELECT telegram_id, username FROM users WHERE telegram_id = ?', (target_user_id,))
        user_data = cursor.fetchone()
        
        if not user_data:
            await update.message.reply_text(f"❌ User with ID {target_user_id} not found!")
            conn.close()
            return
        
        target_telegram_id, username = user_data
        
        # Update user status
        cursor.execute('''UPDATE users 
                          SET is_blocked = 0, blocked_reason = NULL, blocked_at = NULL
                          WHERE telegram_id = ?''',
                       (target_user_id,))
        
        conn.commit()
        
        # Log admin action
        cursor.execute('SELECT user_id FROM users WHERE telegram_id = ?', (target_user_id,))
        target_db_id = cursor.fetchone()[0]
        log_admin_action(admin_id, 'unblock_user', target_db_id, "")
        
        # Notify user
        try:
            await context.bot.send_message(
                chat_id=target_user_id,
                text=f"""✅ **You have been unblocked!**

Your access to Atoplay Shop bot has been restored.

📋 **Unblock Details:**
• **Unblocked by:** Admin
• **Time:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

✅ You can now use the bot commands and make purchases.

📞 **Contact:** @Aarifseller for assistance.""",
                parse_mode='Markdown'
            )
        except Exception as e:
            logger.error(f"Failed to notify unblocked user {target_user_id}: {e}")
        
        await update.message.reply_text(
            f"""✅ **User Unblocked Successfully!**

👤 **User:** @{username} ({target_user_id})
⏰ **Time:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

✅ User has been notified.""",
            parse_mode='Markdown'
        )
        
        conn.close()
        logger.info(f"User {target_user_id} unblocked by admin {admin_id}")
        
    except Exception as e:
        logger.error(f"Error in unblock_user: {e}")

async def user_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Get user information"""
    try:
        admin_id = update.effective_user.id
        
        if not is_admin(admin_id):
            await update.message.reply_text("❌ Unauthorized!")
            return
        
        if not has_permission(admin_id, 'view_user_info'):
            await update.message.reply_text("❌ You don't have permission to view user info!")
            return
        
        command_text = update.message.text
        parts = command_text.split()
        
        if len(parts) < 2:
            await update.message.reply_text("❌ Invalid format! Use: `/userinfo USER_ID`", parse_mode='Markdown')
            return
        
        try:
            target_user_id = int(parts[1])
        except ValueError:
            await update.message.reply_text("❌ Invalid user ID!")
            return
        
        conn = sqlite3.connect('atoplay_bot.db')
        cursor = conn.cursor()
        
        # Get user details
        cursor.execute('''SELECT telegram_id, username, unique_id, balance, 
                                 is_blocked, blocked_reason, blocked_at, is_admin,
                                 strftime('%Y-%m-%d %H:%M', blocked_at) as blocked_time
                          FROM users WHERE telegram_id = ?''', (target_user_id,))
        
        user_data = cursor.fetchone()
        
        if not user_data:
            await update.message.reply_text(f"❌ User with ID {target_user_id} not found!")
            conn.close()
            return
        
        (telegram_id, username, unique_id, balance, is_blocked, 
         blocked_reason, blocked_at, is_admin_user, blocked_time) = user_data
        
        # Get user's purchase history
        cursor.execute('''SELECT COUNT(*), SUM(amount) 
                          FROM transactions 
                          WHERE user_id = (SELECT user_id FROM users WHERE telegram_id = ?)
                          AND status = 'approved' ''', (target_user_id,))
        
        purchase_data = cursor.fetchone()
        total_purchases = purchase_data[0] or 0
        total_spent = purchase_data[1] or 0
        
        # Get user's keys
        cursor.execute('''SELECT COUNT(*) 
                          FROM user_keys 
                          WHERE user_id = (SELECT user_id FROM users WHERE telegram_id = ?)''', 
                       (target_user_id,))
        
        keys_count = cursor.fetchone()[0] or 0
        
        conn.close()
        
        text = f"""📋 **USER INFORMATION**

👤 **Basic Info:**
• **User ID:** {telegram_id}
• **Username:** @{username}
• **Unique ID:** {unique_id}
• **Balance:** ₹{balance}
• **Is Admin:** {'✅ Yes' if is_admin_user == 1 else '❌ No'}

📊 **Statistics:**
• **Total Purchases:** {total_purchases}
• **Total Spent:** ₹{total_spent}
• **Keys Purchased:** {keys_count}

🔒 **Block Status:** {'❌ BLOCKED' if is_blocked == 1 else '✅ ACTIVE'}"""
        
        if is_blocked == 1:
            text += f"\n• **Block Reason:** {blocked_reason}"
            text += f"\n• **Blocked At:** {blocked_time}"
        
        text += f"\n\n🛠️ **Actions:**"
        text += f"\n• `/block_{telegram_id} REASON` - Block user"
        text += f"\n• `/unblock_{telegram_id}` - Unblock user"
        text += f"\n• `/adjustbalance_{telegram_id} +AMOUNT` - Add balance"
        text += f"\n• `/adjustbalance_{telegram_id} -AMOUNT` - Subtract balance"
        
        await update.message.reply_text(text, parse_mode='Markdown')
        
    except Exception as e:
        logger.error(f"Error in user_info: {e}")

async def set_easypaisa(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Set Easypaisa details"""
    try:
        admin_id = update.effective_user.id
        
        if not is_admin(admin_id):
            await update.message.reply_text("❌ Unauthorized!")
            return
        
        if not has_permission(admin_id, 'change_payments'):
            await update.message.reply_text("❌ You don't have permission to change payment methods!")
            return
        
        command_text = update.message.text
        parts = command_text.split()
        
        if len(parts) < 2:
            await update.message.reply_text("❌ Invalid format! Use: `/seteasypaisa NUMBER \"ACCOUNT NAME\"`\n\n**Example:** `/seteasypaisa 03431178575 \"John Doe\"`", parse_mode='Markdown')
            return
        
        number = parts[1]
        account_name = " ".join(parts[2:]) if len(parts) > 2 else ""
        
        # Update Easypaisa in database
        update_payment_method('easypaisa', {
            'number': number,
            'account_name': account_name
        })
        
        # Log admin action
        log_admin_action(admin_id, 'set_easypaisa', 0, f"Number: {number}, Account: {account_name}")
        
        await update.message.reply_text(
            f"""✅ **Easypaisa Updated Successfully!**

📱 **Number:** {number}
👤 **Account Name:** {account_name if account_name else 'Not set'}
👤 **Changed by:** Admin

✅ Easypaisa details have been updated for all users.""",
            parse_mode='Markdown'
        )
        
        logger.info(f"Admin {admin_id} updated Easypaisa: {number}")
        
    except Exception as e:
        logger.error(f"Error in set_easypaisa: {e}")

async def set_jazzcash(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Set JazzCash details"""
    try:
        admin_id = update.effective_user.id
        
        if not is_admin(admin_id):
            await update.message.reply_text("❌ Unauthorized!")
            return
        
        if not has_permission(admin_id, 'change_payments'):
            await update.message.reply_text("❌ You don't have permission to change payment methods!")
            return
        
        command_text = update.message.text
        parts = command_text.split()
        
        if len(parts) < 2:
            await update.message.reply_text("❌ Invalid format! Use: `/setjazzcash NUMBER \"ACCOUNT NAME\"`\n\n**Example:** `/setjazzcash 03001234567 \"Ali Khan\"`", parse_mode='Markdown')
            return
        
        number = parts[1]
        account_name = " ".join(parts[2:]) if len(parts) > 2 else ""
        
        # Update JazzCash in database
        update_payment_method('jazzcash', {
            'number': number,
            'account_name': account_name
        })
        
        # Log admin action
        log_admin_action(admin_id, 'set_jazzcash', 0, f"Number: {number}, Account: {account_name}")
        
        await update.message.reply_text(
            f"""✅ **JazzCash Updated Successfully!**

📱 **Number:** {number}
👤 **Account Name:** {account_name if account_name else 'Not set'}
👤 **Changed by:** Admin

✅ JazzCash details have been updated for all users.""",
            parse_mode='Markdown'
        )
        
        logger.info(f"Admin {admin_id} updated JazzCash: {number}")
        
    except Exception as e:
        logger.error(f"Error in set_jazzcash: {e}")

async def set_binance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Set Binance Pay ID"""
    try:
        admin_id = update.effective_user.id
        
        if not is_admin(admin_id):
            await update.message.reply_text("❌ Unauthorized!")
            return
        
        if not has_permission(admin_id, 'change_payments'):
            await update.message.reply_text("❌ You don't have permission to change payment methods!")
            return
        
        command_text = update.message.text
        parts = command_text.split()
        
        if len(parts) < 2:
            await update.message.reply_text("❌ Invalid format! Use: `/setbinance PAY_ID`\n\n**Example:** `/setbinance 335277914`", parse_mode='Markdown')
            return
        
        pay_id = parts[1]
        
        # Update Binance in database
        update_payment_method('binance', {'pay_id': pay_id})
        
        # Log admin action
        log_admin_action(admin_id, 'set_binance', 0, f"Pay ID: {pay_id}")
        
        await update.message.reply_text(
            f"""✅ **Binance Updated Successfully!**

💰 **Pay ID:** {pay_id}
👤 **Changed by:** Admin

✅ Binance Pay ID has been updated for all users.""",
            parse_mode='Markdown'
        )
        
        logger.info(f"Admin {admin_id} updated Binance Pay ID: {pay_id}")
        
    except Exception as e:
        logger.error(f"Error in set_binance: {e}")

async def set_upi(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Set UPI details"""
    try:
        admin_id = update.effective_user.id
        
        if not is_admin(admin_id):
            await update.message.reply_text("❌ Unauthorized!")
            return
        
        if not has_permission(admin_id, 'change_payments'):
            await update.message.reply_text("❌ You don't have permission to change payment methods!")
            return
        
        command_text = update.message.text
        parts = command_text.split()
        
        if len(parts) < 2:
            await update.message.reply_text("❌ Invalid format! Use: `/setupi UPI_ID \"ACCOUNT NAME\"`\n\n**Example:** `/setupi user@upi \"Account Name\"`", parse_mode='Markdown')
            return
        
        number = parts[1]
        account_name = " ".join(parts[2:]) if len(parts) > 2 else ""
        
        # Update UPI in database
        update_payment_method('upi', {
            'number': number,
            'account_name': account_name
        })
        
        # Log admin action
        log_admin_action(admin_id, 'set_upi', 0, f"Number: {number}, Account: {account_name}")
        
        await update.message.reply_text(
            f"""✅ **UPI Updated Successfully!**

📱 **UPI ID:** {number}
👤 **Account Name:** {account_name if account_name else 'Not set'}
👤 **Changed by:** Admin

✅ UPI details have been updated for all users.""",
            parse_mode='Markdown'
        )
        
        logger.info(f"Admin {admin_id} updated UPI: {number}")
        
    except Exception as e:
        logger.error(f"Error in set_upi: {e}")

async def set_upi_qr_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Set UPI QR code"""
    try:
        admin_id = update.effective_user.id
        
        if not is_admin(admin_id):
            await update.message.reply_text("❌ Unauthorized!")
            return
        
        if not has_permission(admin_id, 'change_payments'):
            await update.message.reply_text("❌ You don't have permission to change payment methods!")
            return
        
        # Set flag to await QR code photo
        context.user_data['awaiting_upi_qr_code'] = True
        
        await update.message.reply_text(
            """📱 **Set UPI QR Code**

Please send the UPI QR code image now.

⚠️ **Requirements:**
• Clear QR code image
• Good resolution
• Square aspect ratio

📸 **Send the QR code photo now.**

❌ Send /cancel to cancel.""",
            parse_mode='Markdown'
        )
        
    except Exception as e:
        logger.error(f"Error in set_upi_qr_code: {e}")

async def handle_upi_qr_code_setup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle UPI QR code setup"""
    try:
        admin_id = update.effective_user.id
        
        if not update.message or not update.message.photo:
            return
        
        # Get the photo (largest size)
        photo = update.message.photo[-1]
        file_id = photo.file_id
        
        # Update UPI QR code in database
        update_payment_method('upi', {'qr_code': file_id})
        
        # Clear the flag
        context.user_data.pop('awaiting_upi_qr_code', None)
        
        # Log admin action
        log_admin_action(admin_id, 'set_upi_qr_code', 0, "UPI QR code updated")
        
        await update.message.reply_text(
            f"""✅ **UPI QR Code Updated Successfully!**

📱 UPI QR code has been updated.
👤 **Changed by:** Admin

✅ QR code is now available for users when they select UPI payment.""",
            parse_mode='Markdown'
        )
        
        logger.info(f"Admin {admin_id} updated UPI QR code")
        
    except Exception as e:
        logger.error(f"Error in handle_upi_qr_code_setup: {e}")
        await update.message.reply_text("❌ An error occurred while updating UPI QR code. Please try again.")

async def set_binance_qr_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Set Binance QR code"""
    try:
        admin_id = update.effective_user.id
        
        if not is_admin(admin_id):
            await update.message.reply_text("❌ Unauthorized!")
            return
        
        if not has_permission(admin_id, 'change_payments'):
            await update.message.reply_text("❌ You don't have permission to change payment methods!")
            return
        
        # Set flag to await QR code photo
        context.user_data['awaiting_binance_qr_code'] = True
        
        await update.message.reply_text(
            """💰 **Set Binance QR Code**

Please send the Binance QR code image now.

⚠️ **Requirements:**
• Clear QR code image
• Good resolution
• Square aspect ratio

📸 **Send the QR code photo now.**

❌ Send /cancel to cancel.""",
            parse_mode='Markdown'
        )
        
    except Exception as e:
        logger.error(f"Error in set_binance_qr_code: {e}")

async def handle_binance_qr_code_setup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle Binance QR code setup"""
    try:
        admin_id = update.effective_user.id
        
        if not update.message or not update.message.photo:
            return
        
        # Get the photo (largest size)
        photo = update.message.photo[-1]
        file_id = photo.file_id
        
        # Update Binance QR code in database
        update_payment_method('binance', {'qr_code': file_id})
        
        # Clear the flag
        context.user_data.pop('awaiting_binance_qr_code', None)
        
        # Log admin action
        log_admin_action(admin_id, 'set_binance_qr_code', 0, "Binance QR code updated")
        
        await update.message.reply_text(
            f"""✅ **Binance QR Code Updated Successfully!**

💰 Binance QR code has been updated.
👤 **Changed by:** Admin

✅ QR code is now available for users when they select Binance payment.""",
            parse_mode='Markdown'
        )
        
        logger.info(f"Admin {admin_id} updated Binance QR code")
        
    except Exception as e:
        logger.error(f"Error in handle_binance_qr_code_setup: {e}")
        await update.message.reply_text("❌ An error occurred while updating Binance QR code. Please try again.")

async def add_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Add new admin (Super Admin only)"""
    try:
        admin_id = update.effective_user.id
        
        if not is_super_admin(admin_id):
            await update.message.reply_text("❌ Unauthorized! Only Super Admin can add admins.")
            return
        
        command_text = update.message.text
        parts = command_text.split()
        
        if len(parts) < 2:
            await update.message.reply_text("❌ Invalid format! Use: `/addadmin USER_ID`", parse_mode='Markdown')
            return
        
        try:
            new_admin_id = int(parts[1])
        except ValueError:
            await update.message.reply_text("❌ Invalid user ID!")
            return
        
        conn = sqlite3.connect('atoplay_bot.db')
        cursor = conn.cursor()
        
        # Check if user exists
        cursor.execute('SELECT telegram_id, username FROM users WHERE telegram_id = ?', (new_admin_id,))
        user_data = cursor.fetchone()
        
        if not user_data:
            await update.message.reply_text(f"❌ User with ID {new_admin_id} not found!")
            conn.close()
            return
        
        target_telegram_id, username = user_data
        
        # Check if already admin
        cursor.execute('SELECT is_admin FROM users WHERE telegram_id = ?', (new_admin_id,))
        is_admin_user = cursor.fetchone()
        
        if is_admin_user and is_admin_user[0] == 1:
            await update.message.reply_text(f"❌ User @{username} is already an admin!")
            conn.close()
            return
        
        # Make user admin with default permissions (only approve payments)
        default_permissions = ADMIN_PERMISSIONS.copy()
        default_permissions['approve_payments'] = True
        
        cursor.execute('UPDATE users SET is_admin = 1, added_by = ?, permissions = ? WHERE telegram_id = ?',
                       (admin_id, str(default_permissions), new_admin_id))
        
        conn.commit()
        
        # Log admin action
        cursor.execute('SELECT user_id FROM users WHERE telegram_id = ?', (new_admin_id,))
        target_db_id = cursor.fetchone()[0]
        log_admin_action(admin_id, 'add_admin', target_db_id, f"Added new admin: {username}")
        
        # Notify new admin
        try:
            await context.bot.send_message(
                chat_id=new_admin_id,
                text=f"""🎉 **Congratulations!**

You have been promoted to Admin in Atoplay Shop bot.

🔧 **Admin Privileges:**
• Approve/Reject payments (Default permission)

📋 **Admin Commands:**
• `/admin` - Admin panel

⚠️ **Note:** Super Admin can grant you additional permissions as needed.

📞 **Contact** Super Admin for assistance.""",
                parse_mode='Markdown'
            )
        except Exception as e:
            logger.error(f"Failed to notify new admin {new_admin_id}: {e}")
        
        await update.message.reply_text(
            f"""✅ **Admin Added Successfully!**

👤 **New Admin:** @{username} ({new_admin_id})
👑 **Added by:** Super Admin
⏰ **Time:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

✅ New admin has been notified with default permissions (Approve Payments only).
✅ You can now set additional permissions for this admin.""",
            parse_mode='Markdown'
        )
        
        conn.close()
        logger.info(f"Admin {new_admin_id} added by Super Admin {admin_id}")
        
    except Exception as e:
        logger.error(f"Error in add_admin: {e}")

async def remove_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Remove admin (Super Admin only)"""
    try:
        admin_id = update.effective_user.id
        
        if not is_super_admin(admin_id):
            await update.message.reply_text("❌ Unauthorized! Only Super Admin can remove admins.")
            return
        
        command_text = update.message.text
        parts = command_text.split()
        
        if len(parts) < 2:
            await update.message.reply_text("❌ Invalid format! Use: `/removeadmin USER_ID`", parse_mode='Markdown')
            return
        
        try:
            target_admin_id = int(parts[1])
        except ValueError:
            await update.message.reply_text("❌ Invalid user ID!")
            return
        
        # Prevent removing self
        if target_admin_id == admin_id:
            await update.message.reply_text("❌ You cannot remove yourself as admin!")
            return
        
        conn = sqlite3.connect('atoplay_bot.db')
        cursor = conn.cursor()
        
        # Check if user exists and is admin
        cursor.execute('SELECT telegram_id, username, is_admin FROM users WHERE telegram_id = ?', (target_admin_id,))
        user_data = cursor.fetchone()
        
        if not user_data:
            await update.message.reply_text(f"❌ User with ID {target_admin_id} not found!")
            conn.close()
            return
        
        target_telegram_id, username, is_admin_user = user_data
        
        if is_admin_user != 1:
            await update.message.reply_text(f"❌ User @{username} is not an admin!")
            conn.close()
            return
        
        # Remove admin privileges
        cursor.execute('UPDATE users SET is_admin = 0, added_by = NULL, permissions = "{}" WHERE telegram_id = ?',
                       (target_admin_id,))
        
        conn.commit()
        
        # Log admin action
        cursor.execute('SELECT user_id FROM users WHERE telegram_id = ?', (target_admin_id,))
        target_db_id = cursor.fetchone()[0]
        log_admin_action(admin_id, 'remove_admin', target_db_id, f"Removed admin: {username}")
        
        # Notify removed admin
        try:
            await context.bot.send_message(
                chat_id=target_admin_id,
                text=f"""📢 **Notice**

Your admin privileges have been removed from Atoplay Shop bot.

📋 **Details:**
• **Removed by:** Super Admin
• **Time:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

⚠️ You no longer have access to admin commands.

📞 **Contact** Super Admin for more information.""",
                parse_mode='Markdown'
            )
        except Exception as e:
            logger.error(f"Failed to notify removed admin {target_admin_id}: {e}")
        
        await update.message.reply_text(
            f"""✅ **Admin Removed Successfully!**

👤 **Removed Admin:** @{username} ({target_admin_id})
👑 **Removed by:** Super Admin
⏰ **Time:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

✅ Admin has been notified.""",
            parse_mode='Markdown'
        )
        
        conn.close()
        logger.info(f"Admin {target_admin_id} removed by Super Admin {admin_id}")
        
    except Exception as e:
        logger.error(f"Error in remove_admin: {e}")

async def list_admins(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """List all admins"""
    try:
        admin_id = update.effective_user.id
        
        if not is_admin(admin_id):
            await update.message.reply_text("❌ Unauthorized!")
            return
        
        if not is_super_admin(admin_id) and not has_permission(admin_id, 'manage_admins'):
            await update.message.reply_text("❌ You don't have permission to list admins!")
            return
        
        admins = get_all_admins()
        
        text = "👑 **ADMIN LIST**\n\n"
        
        for i, (admin_telegram_id, username, is_admin_user) in enumerate(admins, 1):
            status = "👑 Super Admin" if admin_telegram_id == SUPER_ADMIN_ID else "🔧 Admin"
            username_display = f"@{username}" if username else "No username"
            text += f"{i}. {username_display} ({admin_telegram_id}) - {status}\n"
        
        text += f"\n📊 **Total Admins:** {len(admins)}"
        
        if is_super_admin(admin_id):
            text += "\n\n🛠️ **Super Admin Commands:**"
            text += "\n• `/addadmin USER_ID` - Add new admin"
            text += "\n• `/removeadmin USER_ID` - Remove admin"
            text += "\n• Use Admin Panel → Admin Settings to manage permissions"
        
        # Add back button for callback
        if update.callback_query:
            keyboard = [[InlineKeyboardButton("🔙 Back to Admin Settings", callback_data='admin_settings')]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await update.callback_query.edit_message_text(text, parse_mode='Markdown', reply_markup=reply_markup)
        else:
            await update.message.reply_text(text, parse_mode='Markdown')
        
    except Exception as e:
        logger.error(f"Error in list_admins: {e}")

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Log errors"""
    logger.error(f"Update {update} caused error {context.error}")

def main():
    # First delete old database and create new one
    init_db()
    add_sample_keys()
    
    print("=" * 50)
    print("🤖 Bot starting...")
    print(f"📱 Token: {TOKEN[:10]}...")
    print(f"👑 Super Admin ID: {SUPER_ADMIN_ID}")
    print("=" * 50)
    
    try:
        # Create application with build method
        application = Application.builder().token(TOKEN).build()
        
        # Add error handler
        application.add_error_handler(error_handler)
        
        # Basic command handlers
        application.add_handler(CommandHandler('start', start))
        application.add_handler(CommandHandler('buy', buy))
        application.add_handler(CommandHandler('balance', check_balance))
        application.add_handler(CommandHandler('mykeys', my_keys))
        application.add_handler(CommandHandler('admin', admin_panel))
        application.add_handler(CommandHandler('stats', show_stats))
        application.add_handler(CommandHandler('stock', show_stock))
        application.add_handler(CommandHandler('listadmins', list_admins))
        
        # Admin command handlers for adding keys
        application.add_handler(CommandHandler('addkey_3d', handle_add_key))
        application.add_handler(CommandHandler('addkey_10d', handle_add_key))
        application.add_handler(CommandHandler('addkey_30d', handle_add_key))
        
        # Admin command handlers for deleting keys
        application.add_handler(CommandHandler('delkey', handle_delete_key))
        
        # Admin command handlers for price changes
        application.add_handler(CommandHandler('price_3d', handle_price_change))
        application.add_handler(CommandHandler('price_10d', handle_price_change))
        application.add_handler(CommandHandler('price_30d', handle_price_change))
        
        # Admin user management commands
        application.add_handler(CommandHandler('block', block_user))
        application.add_handler(CommandHandler('unblock', unblock_user))
        application.add_handler(CommandHandler('userinfo', user_info))
        
        # Adjusted balance handler - یہ لائن ضرور شامل کریں
        application.add_handler(CommandHandler('adjustbalance', adjust_balance_handler))
        
        # Admin payment methods commands
        application.add_handler(CommandHandler('seteasypaisa', set_easypaisa))
        application.add_handler(CommandHandler('setjazzcash', set_jazzcash))
        application.add_handler(CommandHandler('setbinance', set_binance))
        application.add_handler(CommandHandler('setupi', set_upi))
        application.add_handler(CommandHandler('setupiqr', set_upi_qr_code))
        application.add_handler(CommandHandler('setbinanceqr', set_binance_qr_code))
        
        # Super Admin commands
        application.add_handler(CommandHandler('addadmin', add_admin))
        application.add_handler(CommandHandler('removeadmin', remove_admin))
        
        # Admin payment approval handlers
        application.add_handler(MessageHandler(filters.Regex(r'^/approve_\d+$'), approve_payment))
        application.add_handler(MessageHandler(filters.Regex(r'^/reject_\d+$'), reject_payment))
        
        # Handle text messages for ALL users (including admin menu buttons)
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_message))
        
        # SINGLE callback query handler for ALL callbacks
        application.add_handler(CallbackQueryHandler(callback_handler))
        
        # Photo handler for payment screenshots and QR codes
        application.add_handler(MessageHandler(filters.PHOTO, handle_photo))
        
        print("✅ All handlers registered successfully!")
        print("⏳ Starting polling...")
        
        # Start polling with simple parameters
        application.run_polling()
        
    except Exception as e:
        print(f"❌ CRITICAL ERROR: {e}")
        import traceback
        traceback.print_exc()

if __name__ == '__main__':
    main()