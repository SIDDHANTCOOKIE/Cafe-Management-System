"""
Cafe Management System
Single-file Flask app using SQLite (no ORM).
Features:
- Menu management (admin)
- Inventory management
- Place orders (customer-facing)
- Order history and billing
- Simple HTML pages using render_template_string for quick testing

Run:
1. pip install flask
2. python cafe_management.py
3. Open http://127.0.0.1:5000

This file is meant to be a starting point. Expand as needed.
"""

from flask import Flask, g, render_template_string, request, redirect, url_for, flash
import sqlite3
import os
from datetime import datetime

DATABASE = 'cafe.db'
APP_SECRET = 'change_this_secret'

app = Flask(__name__)
app.config['SECRET_KEY'] = APP_SECRET

# ---------- Database helpers ----------

def get_db():
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = sqlite3.connect(DATABASE)
        db.row_factory = sqlite3.Row
    return db


def init_db():
    db = get_db()
    cur = db.cursor()
    # Tables: menu_items, inventory, orders, order_items
    cur.executescript('''
    CREATE TABLE IF NOT EXISTS menu_items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        description TEXT,
        price REAL NOT NULL,
        sku TEXT UNIQUE,
        active INTEGER NOT NULL DEFAULT 1
    );

    CREATE TABLE IF NOT EXISTS inventory (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        sku TEXT NOT NULL UNIQUE,
        quantity INTEGER NOT NULL DEFAULT 0
    );

    CREATE TABLE IF NOT EXISTS orders (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        created_at TEXT NOT NULL,
        total REAL NOT NULL
    );

    CREATE TABLE IF NOT EXISTS order_items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        order_id INTEGER NOT NULL,
        menu_item_id INTEGER NOT NULL,
        qty INTEGER NOT NULL,
        price REAL NOT NULL,
        FOREIGN KEY(order_id) REFERENCES orders(id),
        FOREIGN KEY(menu_item_id) REFERENCES menu_items(id)
    );
    ''')
    db.commit()


@app.teardown_appcontext
def close_connection(exception):
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()


# ---------- Utility helpers ----------

def query_db(query, args=(), one=False):
    cur = get_db().execute(query, args)
    rv = cur.fetchall()
    cur.close()
    return (rv[0] if rv else None) if one else rv


def execute_db(query, args=()):
    db = get_db()
    cur = db.cursor()
    cur.execute(query, args)
    db.commit()
    return cur.lastrowid


# ---------- Initialization sample data ----------

def seed_if_empty():
    items = query_db('SELECT COUNT(*) as c FROM menu_items', one=True)
    if items['c'] == 0:
        sample_menu = [
            ('Espresso', 'Strong classic espresso', 80.0, 'ESP-01', 1),
            ('Cappuccino', 'Espresso with steamed milk foam', 120.0, 'CAP-01', 1),
            ('Veg Sandwich', 'Grilled vegetables with chutney', 140.0, 'SND-01', 1),
            ('Cold Coffee', 'Iced cold coffee with milk', 110.0, 'CFC-01', 1)
        ]
        for name, desc, price, sku, active in sample_menu:
            execute_db('INSERT INTO menu_items (name, description, price, sku, active) VALUES (?, ?, ?, ?, ?)',
                       (name, desc, price, sku, active))
            execute_db('INSERT OR IGNORE INTO inventory (sku, quantity) VALUES (?, ?)', (sku, 50))


# ---------- Templates (minimal) ----------

BASE = '''
<!doctype html>
<html>
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Cafe Manager</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/css/bootstrap.min.css" rel="stylesheet">
  </head>
  <body class="bg-light">
  <nav class="navbar navbar-expand-lg navbar-dark bg-dark mb-4">
    <div class="container-fluid">
      <a class="navbar-brand" href="{{ url_for('index') }}">Cafe</a>
      <div class="collapse navbar-collapse">
        <ul class="navbar-nav me-auto mb-2 mb-lg-0">
          <li class="nav-item"><a class="nav-link" href="{{ url_for('index') }}">Menu</a></li>
          <li class="nav-item"><a class="nav-link" href="{{ url_for('view_orders') }}">Orders</a></li>
          <li class="nav-item"><a class="nav-link" href="{{ url_for('admin_menu') }}">Admin</a></li>
        </ul>
      </div>
    </div>
  </nav>
  <div class="container">
    {% with messages = get_flashed_messages() %}
      {% if messages %}
        {% for m in messages %}
          <div class="alert alert-info">{{ m }}</div>
        {% endfor %}
      {% endif %}
    {% endwith %}
    {{ body }}
  </div>
  </body>
</html>
'''

INDEX_BODY = '''
<h1>Menu</h1>
<form method="post" action="{{ url_for('place_order') }}">
  <div class="row">
    {% for item in menu %}
      <div class="col-md-6 mb-3">
        <div class="card">
          <div class="card-body">
            <h5 class="card-title">{{ item['name'] }} - Rs {{ item['price'] }}</h5>
            <p class="card-text">{{ item['description'] }}</p>
            <div class="input-group mb-3" style="max-width:200px;">
              <input type="number" name="qty_{{ item['id'] }}" min="0" value="0" class="form-control">
              <span class="input-group-text">qty</span>
            </div>
          </div>
        </div>
      </div>
    {% endfor %}
  </div>
  <button class="btn btn-primary" type="submit">Place Order</button>
</form>
'''

ADMIN_MENU_BODY = '''
<h1>Admin Menu Management</h1>
<a class="btn btn-success mb-3" href="{{ url_for('admin_add_item') }}">Add Item</a>
<table class="table table-striped">
  <thead><tr><th>ID</th><th>Name</th><th>SKU</th><th>Price</th><th>Inventory</th><th>Actions</th></tr></thead>
  <tbody>
    {% for m in menu %}
      <tr>
        <td>{{ m['id'] }}</td>
        <td>{{ m['name'] }}</td>
        <td>{{ m['sku'] }}</td>
        <td>{{ m['price'] }}</td>
        <td>{{ inventory.get(m['sku'], 0) }}</td>
        <td>
          <a class="btn btn-sm btn-primary" href="{{ url_for('admin_edit_item', item_id=m['id']) }}">Edit</a>
          <a class="btn btn-sm btn-danger" href="{{ url_for('admin_delete_item', item_id=m['id']) }}">Delete</a>
        </td>
      </tr>
    {% endfor %}
  </tbody>
</table>

<h3>Inventory Management</h3>
<form method="post" action="{{ url_for('admin_update_inventory') }}" class="row g-3">
  <div class="col-md-4">
    <label class="form-label">SKU</label>
    <input class="form-control" name="sku" required>
  </div>
  <div class="col-md-4">
    <label class="form-label">Quantity</label>
    <input type="number" class="form-control" name="qty" required>
  </div>
  <div class="col-md-4 align-self-end">
    <button class="btn btn-secondary">Update Inventory</button>
  </div>
</form>
'''

ADD_EDIT_BODY = '''
<h1>{{ 'Edit' if item else 'Add' }} Menu Item</h1>
<form method="post">
  <div class="mb-3">
    <label class="form-label">Name</label>
    <input class="form-control" name="name" value="{{ item['name'] if item else '' }}" required>
  </div>
  <div class="mb-3">
    <label class="form-label">Description</label>
    <textarea class="form-control" name="description">{{ item['description'] if item else '' }}</textarea>
  </div>
  <div class="row">
    <div class="col-md-4 mb-3">
      <label class="form-label">Price</label>
      <input type="number" step="0.01" class="form-control" name="price" value="{{ item['price'] if item else '0.0' }}" required>
    </div>
    <div class="col-md-4 mb-3">
      <label class="form-label">SKU</label>
      <input class="form-control" name="sku" value="{{ item['sku'] if item else '' }}" required>
    </div>
    <div class="col-md-4 mb-3">
      <label class="form-label">Active</label>
      <select class="form-select" name="active">
        <option value="1" {% if item and item['active'] %}selected{% endif %}>Yes</option>
        <option value="0" {% if item and not item['active'] %}selected{% endif %}>No</option>
      </select>
    </div>
  </div>
  <button class="btn btn-primary">Save</button>
</form>
'''

ORDERS_BODY = '''
<h1>Orders</h1>
<table class="table">
  <thead><tr><th>ID</th><th>Created</th><th>Total</th><th>Details</th></tr></thead>
  <tbody>
    {% for o in orders %}
      <tr>
        <td>{{ o['id'] }}</td>
        <td>{{ o['created_at'] }}</td>
        <td>Rs {{ o['total'] }}</td>
        <td><a href="{{ url_for('view_order', order_id=o['id']) }}">View</a></td>
      </tr>
    {% endfor %}
  </tbody>
</table>
'''

ORDER_VIEW_BODY = '''
<h1>Order #{{ order['id'] }}</h1>
<p>Placed at {{ order['created_at'] }}</p>
<table class="table">
  <thead><tr><th>Item</th><th>Qty</th><th>Price</th><th>Subtotal</th></tr></thead>
  <tbody>
    {% for it in items %}
      <tr>
        <td>{{ it['name'] }}</td>
        <td>{{ it['qty'] }}</td>
        <td>Rs {{ it['price'] }}</td>
        <td>Rs {{ '%.2f'|format(it['qty'] * it['price']) }}</td>
      </tr>
    {% endfor %}
  </tbody>
</table>
<p><strong>Total: Rs {{ order['total'] }}</strong></p>
<a class="btn btn-secondary" href="{{ url_for('view_orders') }}">Back</a>
'''

# ---------- Routes ----------

@app.route('/')
def index():
    menu = query_db('SELECT * FROM menu_items WHERE active = 1')
    body = render_template_string(INDEX_BODY, menu=menu)
    return render_template_string(BASE, body=body)


@app.route('/place_order', methods=['POST'])
def place_order():
    menu = query_db('SELECT * FROM menu_items WHERE active = 1')
    order_items = []
    total = 0.0
    for m in menu:
        qty = int(request.form.get(f'qty_{m['id']}', 0))
        if qty > 0:
            subtotal = qty * m['price']
            order_items.append((m['id'], m['sku'], m['name'], qty, m['price'], subtotal))
            total += subtotal

    if not order_items:
        flash('No items selected')
        return redirect(url_for('index'))

    # Check inventory
    for _, sku, name, qty, price, _ in order_items:
        inv = query_db('SELECT quantity FROM inventory WHERE sku = ?', (sku,), one=True)
        if not inv or inv['quantity'] < qty:
            flash(f'Insufficient inventory for {name}')
            return redirect(url_for('index'))

    # Deduct inventory and create order
    order_id = execute_db('INSERT INTO orders (created_at, total) VALUES (?, ?)', (datetime.now().isoformat(), total))
    for menu_id, sku, name, qty, price, _ in order_items:
        execute_db('INSERT INTO order_items (order_id, menu_item_id, qty, price) VALUES (?, ?, ?, ?)',
                   (order_id, menu_id, qty, price))
        execute_db('UPDATE inventory SET quantity = quantity - ? WHERE sku = ?', (qty, sku))

    flash(f'Order placed. ID {order_id} — Total Rs {total:.2f}')
    return redirect(url_for('view_order', order_id=order_id))


@app.route('/orders')
def view_orders():
    orders = query_db('SELECT * FROM orders ORDER BY id DESC')
    body = render_template_string(ORDERS_BODY, orders=orders)
    return render_template_string(BASE, body=body)


@app.route('/orders/<int:order_id>')
def view_order(order_id):
    order = query_db('SELECT * FROM orders WHERE id = ?', (order_id,), one=True)
    if not order:
        flash('Order not found')
        return redirect(url_for('view_orders'))
    items = query_db('''
        SELECT oi.qty, oi.price, mi.name
        FROM order_items oi
        JOIN menu_items mi ON mi.id = oi.menu_item_id
        WHERE oi.order_id = ?
    ''', (order_id,))
    body = render_template_string(ORDER_VIEW_BODY, order=order, items=items)
    return render_template_string(BASE, body=body)


# ---------- Admin routes ----------

@app.route('/admin/menu')
def admin_menu():
    menu = query_db('SELECT * FROM menu_items')
    inv_rows = query_db('SELECT sku, quantity FROM inventory')
    inventory = {r['sku']: r['quantity'] for r in inv_rows}
    body = render_template_string(ADMIN_MENU_BODY, menu=menu, inventory=inventory)
    return render_template_string(BASE, body=body)


@app.route('/admin/menu/add', methods=['GET', 'POST'])
def admin_add_item():
    if request.method == 'POST':
        name = request.form['name'].strip()
        desc = request.form.get('description', '').strip()
        price = float(request.form['price'])
        sku = request.form['sku'].strip()
        active = int(request.form.get('active', 1))
        try:
            execute_db('INSERT INTO menu_items (name, description, price, sku, active) VALUES (?, ?, ?, ?, ?)',
                       (name, desc, price, sku, active))
            execute_db('INSERT OR IGNORE INTO inventory (sku, quantity) VALUES (?, ?)', (sku, 0))
            flash('Item added')
            return redirect(url_for('admin_menu'))
        except sqlite3.IntegrityError:
            flash('SKU must be unique')
    body = render_template_string(ADD_EDIT_BODY, item=None)
    return render_template_string(BASE, body=body)


@app.route('/admin/menu/edit/<int:item_id>', methods=['GET', 'POST'])
def admin_edit_item(item_id):
    item = query_db('SELECT * FROM menu_items WHERE id = ?', (item_id,), one=True)
    if not item:
        flash('Item not found')
        return redirect(url_for('admin_menu'))
    if request.method == 'POST':
        name = request.form['name'].strip()
        desc = request.form.get('description', '').strip()
        price = float(request.form['price'])
        sku = request.form['sku'].strip()
        active = int(request.form.get('active', 1))
        try:
            execute_db('UPDATE menu_items SET name = ?, description = ?, price = ?, sku = ?, active = ? WHERE id = ?',
                       (name, desc, price, sku, active, item_id))
            execute_db('INSERT OR IGNORE INTO inventory (sku, quantity) VALUES (?, ?)', (sku, 0))
            flash('Item updated')
            return redirect(url_for('admin_menu'))
        except sqlite3.IntegrityError:
            flash('SKU must be unique')
    body = render_template_string(ADD_EDIT_BODY, item=item)
    return render_template_string(BASE, body=body)


@app.route('/admin/menu/delete/<int:item_id>')
def admin_delete_item(item_id):
    execute_db('DELETE FROM menu_items WHERE id = ?', (item_id,))
    flash('Item deleted')
    return redirect(url_for('admin_menu'))


@app.route('/admin/inventory', methods=['POST'])
def admin_update_inventory():
    sku = request.form['sku'].strip()
    qty = int(request.form['qty'])
    execute_db('INSERT OR REPLACE INTO inventory (sku, quantity) VALUES (?, ?)', (sku, qty))
    flash('Inventory updated')
    return redirect(url_for('admin_menu'))


# ---------- CLI entry ----------

if __name__ == '__main__':
    first_time = not os.path.exists(DATABASE)
    with app.app_context():
        init_db()
        seed_if_empty()
    app.run(debug=True)
