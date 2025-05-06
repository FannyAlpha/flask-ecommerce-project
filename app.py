from flask import Flask, render_template, request, redirect, url_for, flash, session
from flask_mysqldb import MySQL
from werkzeug.security import generate_password_hash, check_password_hash
import config

app = Flask(__name__)
app.secret_key = config.SECRET_KEY

# MySQL Configuration
app.config['MYSQL_HOST'] = config.MYSQL_HOST
app.config['MYSQL_USER'] = config.MYSQL_USER
app.config['MYSQL_PASSWORD'] = config.MYSQL_PASSWORD
app.config['MYSQL_DB'] = config.MYSQL_DB

mysql = MySQL(app)

# Routes
@app.route('/')
def index():
    if 'user_id' in session:
        cur = mysql.connection.cursor()
        cur.execute("SELECT * FROM products LIMIT 8")
        products = cur.fetchall()
        cur.close()
        return render_template('index.html', products=products)
    return redirect(url_for('login'))

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        email = request.form['email']
        password = request.form['password']
        is_admin = True if username == 'admin' else False  # For demo purposes
        
        hashed_password = generate_password_hash(password)
        
        cur = mysql.connection.cursor()
        try:
            cur.execute(
                "INSERT INTO users (username, email, password_hash, is_admin) VALUES (%s, %s, %s, %s)",
                (username, email, hashed_password, is_admin)
            )
            mysql.connection.commit()
            flash('Registration successful! Please login.', 'success')
            return redirect(url_for('login'))
        except Exception as e:
            mysql.connection.rollback()
            flash('Username or email already exists!', 'danger')
        finally:
            cur.close()
    
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        cur = mysql.connection.cursor()
        cur.execute("SELECT * FROM users WHERE username = %s", (username,))
        user = cur.fetchone()
        cur.close()
        
        if user and check_password_hash(user[3], password):
            session['user_id'] = user[0]
            session['username'] = user[1]
            flash('Login successful!', 'success')
            return redirect(url_for('index'))
        else:
            flash('Invalid username or password', 'danger')
    
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    flash('You have been logged out.', 'info')
    return redirect(url_for('login'))

@app.route('/products')
def products():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    cur = mysql.connection.cursor()
    cur.execute("SELECT * FROM products")
    products = cur.fetchall()
    cur.close()
    
    return render_template('products.html', products=products)

@app.route('/product/<int:product_id>')
def product_detail(product_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    cur = mysql.connection.cursor()
    cur.execute("SELECT * FROM products WHERE id = %s", (product_id,))
    product = cur.fetchone()
    cur.close()
    
    if not product:
        flash('Product not found!', 'danger')
        return redirect(url_for('products'))
    
    return render_template('product_detail.html', product=product)

@app.route('/add_to_cart/<int:product_id>', methods=['POST'])
def add_to_cart(product_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    quantity = int(request.form.get('quantity', 1))
    
    cur = mysql.connection.cursor()
    
    # Check if product already in cart
    cur.execute(
        "SELECT * FROM cart WHERE user_id = %s AND product_id = %s",
        (session['user_id'], product_id)
    )
    existing_item = cur.fetchone()
    
    if existing_item:
        # Update quantity
        new_quantity = existing_item[3] + quantity
        cur.execute(
            "UPDATE cart SET quantity = %s WHERE id = %s",
            (new_quantity, existing_item[0])
        )
    else:
        # Add new item
        cur.execute(
            "INSERT INTO cart (user_id, product_id, quantity) VALUES (%s, %s, %s)",
            (session['user_id'], product_id, quantity)
        )
    
    mysql.connection.commit()
    cur.close()
    
    flash('Product added to cart!', 'success')
    return redirect(url_for('cart'))

@app.route('/cart')
def cart():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    cur = mysql.connection.cursor()
    cur.execute("""
        SELECT p.id, p.name, p.price, p.image_url, c.quantity, (p.price * c.quantity) as total
        FROM cart c
        JOIN products p ON c.product_id = p.id
        WHERE c.user_id = %s
    """, (session['user_id'],))
    cart_items = cur.fetchall()
    
    # Calculate grand total
    grand_total = sum(item[5] for item in cart_items) if cart_items else 0
    
    cur.close()
    
    return render_template('cart.html', cart_items=cart_items, grand_total=grand_total)

@app.route('/remove_from_cart/<int:product_id>')
def remove_from_cart(product_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    cur = mysql.connection.cursor()
    cur.execute(
        "DELETE FROM cart WHERE user_id = %s AND product_id = %s",
        (session['user_id'], product_id)
    )
    mysql.connection.commit()
    cur.close()
    
    flash('Product removed from cart!', 'info')
    return redirect(url_for('cart'))

@app.route('/checkout', methods=['GET', 'POST'])
def checkout():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    if request.method == 'POST':
        # Process the order
        cur = mysql.connection.cursor()
        
        # Get cart items
        cur.execute("""
            SELECT p.id, p.price, c.quantity
            FROM cart c
            JOIN products p ON c.product_id = p.id
            WHERE c.user_id = %s
        """, (session['user_id'],))
        cart_items = cur.fetchall()
        
        if not cart_items:
            flash('Your cart is empty!', 'danger')
            return redirect(url_for('cart'))
        
        # Calculate total amount
        total_amount = sum(item[1] * item[2] for item in cart_items)
        
        # Create order
        cur.execute(
            "INSERT INTO orders (user_id, total_amount) VALUES (%s, %s)",
            (session['user_id'], total_amount)
        )
        order_id = cur.lastrowid
        
        # Add order items
        for item in cart_items:
            product_id, price, quantity = item
            cur.execute(
                "INSERT INTO order_items (order_id, product_id, quantity, price) VALUES (%s, %s, %s, %s)",
                (order_id, product_id, quantity, price)
            )
            # Update product stock
            cur.execute(
                "UPDATE products SET stock = stock - %s WHERE id = %s",
                (quantity, product_id)
            )
        
        # Clear cart
        cur.execute(
            "DELETE FROM cart WHERE user_id = %s",
            (session['user_id'],)
        )
        
        mysql.connection.commit()
        cur.close()
        
        flash('Order placed successfully!', 'success')
        return redirect(url_for('index'))
    
    return render_template('checkout.html')


# Admin Dashboard
# @app.route('/admin')
# def admin_dashboard():
#     if 'user_id' not in session:
#         return redirect(url_for('login'))
    
#     cur = mysql.connection.cursor()
#     cur.execute("SELECT is_admin FROM users WHERE id = %s", (session['user_id'],))
#     user = cur.fetchone()
#     cur.close()
    
#     if not user or not user[0]:
#         flash('You do not have permission to access this page', 'danger')
#         return redirect(url_for('index'))
    
#     return render_template('admin/dashboard.html')

@app.route('/admin')
def admin_dashboard():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    cur = mysql.connection.cursor()
    cur.execute("SELECT is_admin FROM users WHERE id = %s", (session['user_id'],))
    user = cur.fetchone()
    
    if not user or not user[0]:
        cur.close()
        flash('You do not have permission to access this page', 'danger')
        return redirect(url_for('index'))
    
    # Get counts for dashboard
    cur.execute("SELECT COUNT(*) FROM products")
    products_count = cur.fetchone()[0]
    
    cur.execute("SELECT COUNT(*) FROM orders")
    orders_count = cur.fetchone()[0]
    
    cur.execute("SELECT COUNT(*) FROM users")
    users_count = cur.fetchone()[0]
    
    cur.close()
    
    return render_template('admin/dashboard.html', 
                         products_count=products_count,
                         orders_count=orders_count,
                         users_count=users_count)

# Admin Products List
@app.route('/admin/products')
def admin_products():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    # Check if user is admin
    cur = mysql.connection.cursor()
    cur.execute("SELECT is_admin FROM users WHERE id = %s", (session['user_id'],))
    user = cur.fetchone()
    
    if not user or not user[0]:
        cur.close()
        flash('You do not have permission to access this page', 'danger')
        return redirect(url_for('index'))
    
    cur.execute("SELECT * FROM products")
    products = cur.fetchall()
    cur.close()
    
    return render_template('admin/products.html', products=products)

# Add Product
@app.route('/admin/products/add', methods=['GET', 'POST'])
def add_product():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    # Check if user is admin
    cur = mysql.connection.cursor()
    cur.execute("SELECT is_admin FROM users WHERE id = %s", (session['user_id'],))
    user = cur.fetchone()
    cur.close()
    
    if not user or not user[0]:
        flash('You do not have permission to access this page', 'danger')
        return redirect(url_for('index'))
    
    if request.method == 'POST':
        name = request.form['name']
        description = request.form['description']
        price = float(request.form['price'])
        stock = int(request.form['stock'])
        image_url = request.form['image_url']
        
        cur = mysql.connection.cursor()
        try:
            cur.execute(
                "INSERT INTO products (name, description, price, stock, image_url) VALUES (%s, %s, %s, %s, %s)",
                (name, description, price, stock, image_url)
            )
            mysql.connection.commit()
            flash('Product added successfully!', 'success')
            return redirect(url_for('admin_products'))
        except Exception as e:
            mysql.connection.rollback()
            flash(f'Error adding product: {str(e)}', 'danger')
        finally:
            cur.close()
    
    return render_template('admin/add_product.html')

# Edit Product
@app.route('/admin/products/edit/<int:product_id>', methods=['GET', 'POST'])
def edit_product(product_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    # Check if user is admin
    cur = mysql.connection.cursor()
    cur.execute("SELECT is_admin FROM users WHERE id = %s", (session['user_id'],))
    user = cur.fetchone()
    
    if not user or not user[0]:
        cur.close()
        flash('You do not have permission to access this page', 'danger')
        return redirect(url_for('index'))
    
    if request.method == 'POST':
        name = request.form['name']
        description = request.form['description']
        price = float(request.form['price'])
        stock = int(request.form['stock'])
        image_url = request.form['image_url']
        
        try:
            cur.execute(
                """UPDATE products SET 
                    name = %s, 
                    description = %s, 
                    price = %s, 
                    stock = %s, 
                    image_url = %s 
                WHERE id = %s""",
                (name, description, price, stock, image_url, product_id)
            )
            mysql.connection.commit()
            flash('Product updated successfully!', 'success')
            return redirect(url_for('admin_products'))
        except Exception as e:
            mysql.connection.rollback()
            flash(f'Error updating product: {str(e)}', 'danger')
        finally:
            cur.close()
    else:
        cur.execute("SELECT * FROM products WHERE id = %s", (product_id,))
        product = cur.fetchone()
        cur.close()
        
        if not product:
            flash('Product not found!', 'danger')
            return redirect(url_for('admin_products'))
        
        return render_template('admin/edit_product.html', product=product)

# Delete Product
@app.route('/admin/products/delete/<int:product_id>')
def delete_product(product_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    # Check if user is admin
    cur = mysql.connection.cursor()
    cur.execute("SELECT is_admin FROM users WHERE id = %s", (session['user_id'],))
    user = cur.fetchone()
    
    if not user or not user[0]:
        cur.close()
        flash('You do not have permission to access this page', 'danger')
        return redirect(url_for('index'))
    
    try:
        cur.execute("DELETE FROM products WHERE id = %s", (product_id,))
        mysql.connection.commit()
        flash('Product deleted successfully!', 'success')
    except Exception as e:
        mysql.connection.rollback()
        flash(f'Error deleting product: {str(e)}', 'danger')
    finally:
        cur.close()
    
    return redirect(url_for('admin_products'))

# About Us Page
@app.route('/about')
def about():
    return render_template('about.html')

# Contact Us Page
@app.route('/contact', methods=['GET', 'POST'])
def contact():
    if request.method == 'POST':
        # Process form data
        name = request.form.get('name')
        email = request.form.get('email')
        message = request.form.get('message')
        
        # Here you would typically:
        # 1. Save to database
        # 2. Send email notification
        # 3. Or both
        
        flash('Thank you for your message! We will contact you soon.', 'success')
        return redirect(url_for('contact'))
    
    return render_template('contact.html')


@app.route('/search')
def search():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    query = request.args.get('q', '')
    page = request.args.get('page', 1, type=int)
    per_page = 9  # Products per page
    
    cur = mysql.connection.cursor()
    
    if query:
        # Using MATCH AGAINST for full-text search
        cur.execute("""
            SELECT *, 
                   MATCH(name, description) AGAINST(%s IN NATURAL LANGUAGE MODE) as relevance
            FROM products
            WHERE MATCH(name, description) AGAINST(%s IN NATURAL LANGUAGE MODE)
            ORDER BY relevance DESC
            LIMIT %s OFFSET %s
        """, (query, query, per_page, (page-1)*per_page))
    else:
        # If no query, return all products with pagination
        cur.execute("SELECT * FROM products LIMIT %s OFFSET %s", 
                   (per_page, (page-1)*per_page))
    
    products = cur.fetchall()
    
    # Get total count for pagination
    if query:
        cur.execute("""
            SELECT COUNT(*) 
            FROM products
            WHERE MATCH(name, description) AGAINST(%s IN NATURAL LANGUAGE MODE)
        """, (query,))
    else:
        cur.execute("SELECT COUNT(*) FROM products")
    
    total = cur.fetchone()[0]
    cur.close()
    
    return render_template('search.html', 
                         products=products,
                         query=query,
                         page=page,
                         per_page=per_page,
                         total=total)

if __name__ == '__main__':
    app.run(debug=True)