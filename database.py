import sqlite3

def init_db():
    conn = sqlite3.connect('shop.db')
    cur = conn.cursor()
    
    # Товары (добавлено поле server)
    cur.execute('''
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            price INTEGER NOT NULL,
            server TEXT NOT NULL,
            description TEXT,
            file_id TEXT
        )
    ''')
    
    # Заказы (добавлено поле server)
    cur.execute('''
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            product_id INTEGER NOT NULL,
            product_name TEXT,
            server TEXT,
            amount INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Админы
    cur.execute('''
        CREATE TABLE IF NOT EXISTS admins (
            user_id INTEGER PRIMARY KEY
        )
    ''')
    
    conn.commit()
    conn.close()

def add_admin(user_id):
    conn = sqlite3.connect('shop.db')
    cur = conn.cursor()
    cur.execute("INSERT OR IGNORE INTO admins (user_id) VALUES (?)", (user_id,))
    conn.commit()
    conn.close()

def get_admins():
    conn = sqlite3.connect('shop.db')
    cur = conn.cursor()
    cur.execute("SELECT user_id FROM admins")
    admins = [row[0] for row in cur.fetchall()]
    conn.close()
    return admins

def get_products():
    conn = sqlite3.connect('shop.db')
    cur = conn.cursor()
    cur.execute("SELECT id, name, price, server, description FROM products")
    products = cur.fetchall()
    conn.close()
    return products

def add_product(name, price, server, description, file_id=None):
    conn = sqlite3.connect('shop.db')
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO products (name, price, server, description, file_id) VALUES (?, ?, ?, ?, ?)",
        (name, price, server, description, file_id)
    )
    conn.commit()
    conn.close()

def delete_product(product_id):
    conn = sqlite3.connect('shop.db')
    cur = conn.cursor()
    cur.execute("DELETE FROM products WHERE id = ?", (product_id,))
    conn.commit()
    conn.close()

def save_order(user_id, product_id, product_name, server, amount):
    conn = sqlite3.connect('shop.db')
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO orders (user_id, product_id, product_name, server, amount) VALUES (?, ?, ?, ?, ?)",
        (user_id, product_id, product_name, server, amount)
    )
    conn.commit()
    conn.close()