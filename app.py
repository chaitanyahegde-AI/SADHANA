from flask import Flask, render_template, request, redirect, url_for, session, abort
from werkzeug.security import generate_password_hash, check_password_hash
from authlib.integrations.flask_client import OAuth
import os
import razorpay
RAZORPAY_KEY_ID = "rzp_test_StjcPeX6kaaRAF"
RAZORPAY_SECRET = "pA0m7t47e5JYGkIVZdzd3Lz0"

client = razorpay.Client(
    auth=(
        RAZORPAY_KEY_ID,
        RAZORPAY_SECRET
    )
)

import mysql.connector

def get_db():
    return mysql.connector.connect(
        host="localhost",
        user="root",
        password="chait",
        database="honey_business"
    )

app = Flask(__name__)
app.secret_key = "change-this-secret"

ADMIN_USERNAME = "admin"
ADMIN_PASSWORD = "secret123"



orders = []

oauth = OAuth(app)
oauth.register(
    name='google',
    client_id=os.environ.get('GOOGLE_CLIENT_ID'),
    client_secret=os.environ.get('GOOGLE_CLIENT_SECRET'),
    server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
    client_kwargs={'scope': 'openid email profile'},
)

@app.route("/")
def home():
    return render_template("index.html")

@app.route("/products")
def products_page():
    conn = get_db()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("SELECT * FROM products")
    products = cursor.fetchall()

    cursor.close()
    conn.close()

    # Map database columns to the template's expected keys.
    mapped = []
    for p in products:
        mapped.append({
            'product_id': p.get('product_id'),
            'name': p.get('product_name') or p.get('name'),
            'desc': p.get('description') or p.get('desc') or 'Our pure natural honey.',
            'price': p.get('price') or 0,
            'image': p.get('image') or '/static/sidehon.jpeg'
        })

    # If no products in DB, show a sample/demo product so UI can be tested.
    if not mapped:
        mapped = [{
            'product_id': 0,
            'name': 'Sample Honey',
            'desc': 'Pure natural honey (demo item).',
            'price': '199.00',
            'image': '/static/sidehon.jpeg'
        }]

    return render_template("products.html", products=mapped)

@app.route("/order/<int:product_id>")
def order_page(product_id):

    conn = get_db()

    cursor = conn.cursor(dictionary=True)

    # GET PRODUCT

    cursor.execute("""
        SELECT *
        FROM products
        WHERE product_id=%s
    """, (product_id,))

    product = cursor.fetchone()

    # GET REVIEWS

    cursor.execute("""
        SELECT r.*, c.name
        FROM reviews r
        JOIN customers c
        ON r.customer_id = c.customer_id
        WHERE r.product_id=%s
        ORDER BY r.review_date DESC
    """, (product_id,))

    reviews = cursor.fetchall()

    cursor.close()

    conn.close()

    # DEMO PRODUCT

    if not product:

        if product_id == 0:

            product = {
                'product_id': 0,
                'name': 'Sample Honey',
                'desc': 'Pure natural honey (demo item).',
                'price': '199.00',
                'image': '/static/sidehon.jpeg'
            }

        else:

            abort(404)

    return render_template(
        "order.html",
        product=product,
        reviews=reviews
    )
@app.route("/submit_order", methods=["POST"])
def submit_order():
    name = request.form["name"]
    phone = request.form["phone"]
    address = request.form["address"]
    product_id = request.form.get("product_id")

    # normalize phone: strip non-digits
    phone_digits = ''.join([c for c in phone if c.isdigit()])
    if len(phone_digits) != 10:
        return "Invalid phone number"

    conn = get_db()
    cursor = conn.cursor()

    try:
        # check if customer exists by phone
        cursor.execute(
            "SELECT customer_id, name FROM customers WHERE phone=%s",
            (phone_digits,)
        )
        existing = cursor.fetchone()

        if existing:
            customer_id, db_name = existing

            if db_name.strip().lower() != name.strip().lower():
                return "⚠️ Phone already registered with different name"

            cursor.execute(
                "UPDATE customers SET address=%s, phone=%s WHERE customer_id=%s",
                (address, phone_digits, customer_id)
            )
        else:
            cursor.execute(
                "INSERT INTO customers (name, phone, address) VALUES (%s, %s, %s)",
                (name, phone_digits, address)
            )
            customer_id = cursor.lastrowid

        # CREATE ORDER
        cursor.execute(
            """
            INSERT INTO orders (order_status, customer_id)
            VALUES (%s, %s)
            """,
            ("Placed", customer_id)
        )

        order_id = cursor.lastrowid

        cursor.execute(
            "SELECT price FROM products WHERE product_id=%s",
            (product_id,)
        )
        prod = cursor.fetchone()
        price_per_unit = float(prod[0]) if prod else 0

        # ADD PRODUCT TO ORDER_ITEMS
        cursor.execute(
            """
            INSERT INTO order_items (order_id, product_id, quantity, price_per_unit)
            VALUES (%s, %s, %s, %s)
            """,
            (order_id, product_id, 1, price_per_unit)
        )

        conn.commit()
    except Exception as e:
        conn.rollback()
        return f"Error: {str(e)}"
    finally:
        cursor.close()
        conn.close()

    order = {'name': name, 'order_id': order_id}
    return render_template("thank_you.html", order=order)

@app.route("/admin", methods=["GET", "POST"])
def admin_login():
    if session.get("admin"):
        return redirect(url_for("admin_orders"))

    error = None
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]

        if username == ADMIN_USERNAME and password == ADMIN_PASSWORD:
            session["admin"] = True
            return redirect(url_for("admin_orders"))
        error = "Invalid username or password"

    return render_template("admin_login.html", error=error)


@app.route("/signup", methods=["GET", "POST"])
def signup():

    if session.get("user"):
        return redirect(url_for("dashboard"))

    error = None

    if request.method == "POST":

        username = request.form.get("username")
        password = request.form.get("password")
        first_name = request.form.get("first_name")
        last_name = request.form.get("last_name")
        email = request.form.get("email")

        if not (username and password and first_name and email):

            error = "All fields required"

        else:

            conn = get_db()
            cursor = conn.cursor()

            try:

                cursor.execute(
                    "SELECT customer_id FROM customers WHERE username=%s OR email=%s",
                    (username, email)
                )
                existing_user = cursor.fetchone()

                if existing_user:
                    error = "Username or email already registered"
                else:
                    hashed_password = generate_password_hash(password)

                    cursor.execute("""
                        INSERT INTO customers
                        (name, email, username, password)
                        VALUES (%s, %s, %s, %s)
                    """, (
                        first_name + " " + last_name,
                        email,
                        username,
                        hashed_password
                    ))

                    conn.commit()

                    session["user"] = email
                    session["user_fullname"] = first_name + " " + last_name

                    return redirect(url_for("dashboard"))

            except Exception as e:

                error = f"Error: {str(e)}"

            finally:

                cursor.close()
                conn.close()

    return render_template("signup.html", error=error)
@app.route("/login", methods=["GET", "POST"])
def login():

    if session.get("user"):
        return redirect(url_for("dashboard"))

    error = None

    if request.method == "POST":

        credential = request.form.get("username")
        password = request.form.get("password")

        conn = get_db()
        cursor = conn.cursor(dictionary=True)

        cursor.execute("""
            SELECT *
            FROM customers
            WHERE username=%s OR email=%s
        """, (credential, credential))

        user = cursor.fetchone()

        cursor.close()
        conn.close()

        if user and user.get("password") and check_password_hash(user["password"], password):
            session["user"] = user["email"]
            session["user_fullname"] = user["name"]
            return redirect(url_for("dashboard"))

        error = "Invalid username/email or password"

    return render_template("login.html", error=error)

@app.route("/logout")
def logout():
    session.pop("user", None)
    session.pop("user_fullname", None)
    return redirect(url_for("home"))


@app.route('/login/google')
def login_google():
    redirect_uri = url_for('authorize_google', _external=True)
    return oauth.google.authorize_redirect(redirect_uri)


@app.route('/authorize/google')
def authorize_google():
    token = oauth.google.authorize_access_token()
    # try to parse id token or fetch userinfo
    user_info = None
    try:
        user_info = oauth.google.parse_id_token(token)
    except Exception:
        try:
            resp = oauth.google.get('userinfo')
            user_info = resp.json()
        except Exception:
            user_info = {}

    email = user_info.get('email')
    given = user_info.get('given_name') or ''
    family = user_info.get('family_name') or ''
    name = user_info.get('name') or ''

    conn = get_db()
    cursor = conn.cursor(dictionary=True)

    cursor.execute(
        "SELECT * FROM customers WHERE email=%s",
        (email,)
    )

    existing_user = cursor.fetchone()

    if not existing_user:
        full_name = (given + " " + family).strip()

        cursor.execute(
            "INSERT INTO customers(name, email) VALUES(%s, %s)",
            (full_name, email)
        )

        conn.commit()

    session['user'] = email
    session['user_fullname'] = (given + " " + family).strip()

    cursor.close()
    conn.close()

    return redirect(url_for('dashboard'))

@app.route("/admin/orders")
def admin_orders():
    if not session.get("admin"):
        return redirect(url_for("admin_login"))

    conn = get_db()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("""
        SELECT
            o.order_id,
            p.product_name AS product,
            c.name,
            c.phone,
            c.address,
            o.order_status
        FROM orders o
        JOIN customers c ON o.customer_id = c.customer_id
        LEFT JOIN order_items oi ON oi.order_id = o.order_id
        LEFT JOIN products p ON p.product_id = oi.product_id
    """)

    orders = cursor.fetchall()

    cursor.close()
    conn.close()

    return render_template("admin_orders.html", orders=orders)


@app.route("/admin/logout")
def admin_logout():
    session.pop("admin", None)
    return redirect(url_for("admin_login"))

@app.route("/dashboard")
def dashboard():

    if not session.get("user"):
        return redirect(url_for("login"))

    conn = get_db()

    # CUSTOMER QUERY
    cursor1 = conn.cursor(dictionary=True)

    cursor1.execute("""
        SELECT *
        FROM customers
        WHERE email=%s
    """, (session["user"],))

    customer = cursor1.fetchone()

    cursor1.close()

    if not customer:
        return redirect(url_for("logout"))

    customer_id = customer["customer_id"]

    # ORDERS QUERY
    cursor2 = conn.cursor(dictionary=True)

    cursor2.execute("""
    SELECT 
        o.order_id,
        o.order_status,
        oi.product_id,
        p.product_name,
        p.price,
        p.image

    FROM orders o

    JOIN order_items oi
        ON o.order_id = oi.order_id

    JOIN products p
        ON oi.product_id = p.product_id

    WHERE o.customer_id=%s

    ORDER BY o.order_id DESC
""", (customer_id,))

    orders = cursor2.fetchall()

    cursor2.close()

    # REVIEW QUERY
    cursor3 = conn.cursor(dictionary=True)

    cursor3.execute("""
        SELECT
            r.*,
            c.name AS customer_name,
            p.product_name
        FROM reviews r
        JOIN customers c
            ON r.customer_id = c.customer_id
        JOIN products p
            ON r.product_id = p.product_id
        WHERE r.customer_id=%s
        ORDER BY r.review_date DESC
    """, (customer_id,))

    reviews = cursor3.fetchall()

    cursor3.close()

    # REVIEW COUNT
    cursor4 = conn.cursor(dictionary=True)
    cursor4.execute("""
        SELECT COUNT(*) AS total_reviews
        FROM reviews
        WHERE customer_id=%s
    """, (customer_id,))

    review_data = cursor4.fetchone()
    cursor4.close()

    conn.close()

    # STATS
    total_orders = len(orders)

    delivered_orders = len([
        o for o in orders
        if o["order_status"] == "Delivered"
    ])

    upcoming_orders = len([
        o for o in orders
        if o["order_status"] != "Delivered"
    ])

    total_reviews = review_data["total_reviews"]

    return render_template(
        "dashboard.html",
        customer=customer,
        orders=orders,
        reviews=reviews,
        total_orders=total_orders,
        delivered_orders=delivered_orders,
        upcoming_orders=upcoming_orders,
        total_reviews=total_reviews
    )
@app.route("/add_to_cart/<int:product_id>/<int:qty>")
def add_to_cart(product_id, qty):

    if "cart" not in session:
        session["cart"] = []

    session["cart"].append({
        "product_id": product_id,
        "qty": qty
    })

    session.modified = True

    return redirect(url_for("cart"))
@app.route("/cart")
def cart():

    cart_items = session.get("cart", [])

    conn = get_db()
    cursor = conn.cursor(dictionary=True)

    products = []

    total = 0

    for item in cart_items:

        cursor.execute("""
            SELECT *
            FROM products
            WHERE product_id=%s
        """, (item["product_id"],))

        p = cursor.fetchone()

        if p:

            p["qty"] = item["qty"]

            p["subtotal"] = (
                float(p["price"]) * item["qty"]
            )

            total += p["subtotal"]

            products.append(p)

    cursor.close()
    conn.close()

    return render_template(
        "cart.html",
        products=products,
        total=total
    )
@app.route("/remove_from_cart/<int:index>")
def remove_from_cart(index):

    cart = session.get("cart", [])

    if 0 <= index < len(cart):
        cart.pop(index)

    session["cart"] = cart
    session.modified = True

    return redirect(url_for("cart"))

@app.route("/checkout")
def checkout():

    cart_items = session.get("cart", [])

    conn = get_db()

    cursor = conn.cursor(dictionary=True)

    products = []

    total = 0

    for item in cart_items:

        cursor.execute("""
            SELECT *
            FROM products
            WHERE product_id=%s
        """, (item["product_id"],))

        p = cursor.fetchone()

        if p:

            p["qty"] = item["qty"]

            p["subtotal"] = (
                float(p["price"]) * item["qty"]
            )

            total += p["subtotal"]

            products.append(p)

    cursor.close()
    conn.close()

    shipping = 150
    tax = total * 0.05

    grand_total = total + shipping + tax
    razorpay_order = client.order.create({
    "amount": int(grand_total * 100),
    "currency": "INR",
    "payment_capture": 1
    })


    return render_template(
        "checkout.html",
        products=products,
        total=total,
        shipping=shipping,
        tax=tax,
        grand_total=grand_total,
        razorpay_order=razorpay_order,
razorpay_key=RAZORPAY_KEY_ID
    )
@app.route('/place_order', methods=['POST'])
def place_order():
    # Save shipping info to session and (if logged in) update customer record
    fullname = request.form.get('fullname') or request.form.get('name')
    phone = request.form.get('phone') or ''
    phone_digits = ''.join([c for c in phone if c.isdigit()])
    address = request.form.get('address')
    city = request.form.get('city')
    postal_code = request.form.get('postal_code')

    session['shipping'] = {
        'name': fullname,
        'phone': phone_digits,
        'address': address,
        'city': city,
        'postal_code': postal_code
    }

    if session.get('user'):
        conn = get_db()
        cursor = conn.cursor()

        try:
            cursor.execute(
                "SELECT customer_id FROM customers WHERE email=%s",
                (session['user'],)
            )

            row = cursor.fetchone()

            if row:
                customer_id = row[0]

                cursor.execute(
                    """
                    UPDATE customers
                    SET address=%s,
                        phone=%s,
                        name=%s
                    WHERE customer_id=%s
                    """,
                    (
                        address,
                        phone_digits,
                        fullname,
                        customer_id
                    )
                )

                conn.commit()

        finally:
            cursor.close()
            conn.close()

    return "OK"
@app.route("/payment_success")
def payment_success():

    if not session.get("user"):
        return redirect(url_for("login"))

    cart_items = session.get("cart", [])

    conn = get_db()

    cursor = conn.cursor()

    try:

        # GET CUSTOMER

        cursor.execute("""
            SELECT customer_id
            FROM customers
            WHERE email=%s
        """, (session["user"],))

        customer = cursor.fetchone()

        if not customer:
            return "Customer record not found"

        customer_id = customer[0]

        # Prefer shipping info saved in session (from checkout) when available
        shipping = session.get('shipping', {})
        address = shipping.get('address') or request.values.get("address")
        phone = shipping.get('phone')
        name = shipping.get('name')
        if address:
            cursor.execute(
                "UPDATE customers SET address=%s WHERE customer_id=%s",
                (address, customer_id)
            )
        if phone:
            cursor.execute(
                "UPDATE customers SET phone=%s WHERE customer_id=%s",
                (phone, customer_id)
            )
        if name:
            cursor.execute(
                "UPDATE customers SET name=%s WHERE customer_id=%s",
                (name, customer_id)
            )

        # CREATE ORDER

        cursor.execute("""
            INSERT INTO orders
            (customer_id, order_status)
            VALUES (%s, %s)
        """, (
            customer_id,
            "Paid"
        ))

        order_id = cursor.lastrowid

        total_amount = 0

        # INSERT ORDER ITEMS

                # INSERT ORDER ITEMS

        for item in cart_items:

            # GET PRODUCT PRICE

            cursor.execute("""
                SELECT price
                FROM products
                WHERE product_id=%s
            """, (item["product_id"],))

            product = cursor.fetchone()

            price = float(product[0])

            # INSERT ORDER ITEM

            cursor.execute("""
                INSERT INTO order_items
                (order_id, product_id, quantity, price_per_unit)
                VALUES (%s, %s, %s, %s)
            """, (
                order_id,
                item["product_id"],
                item["qty"],
                price
            ))

            total_amount += (
                price * item["qty"]
            )

            # GET PRICE


        # INSERT PAYMENT

        cursor.execute("""
    INSERT INTO payments
    (
        order_id,
        payment_method,
        payment_status,
        amount
    )
    VALUES (%s, %s, %s, %s)
""", (
    order_id,
    "UPI",
    "Completed",
    total_amount
))

        conn.commit()

        # CLEAR CART

        session["cart"] = []

        return render_template(
            "thank_you.html",
            order={
                "name":
                    session.get("user_fullname"),

                "order_id":
                    order_id
            }
        )

    except Exception as e:

        conn.rollback()

        return f"Error: {str(e)}"

    finally:

        cursor.close()
        conn.close()
@app.route("/about")
def about():
    return render_template("about.html")
@app.route("/add_review", methods=["POST"])
def add_review():

    # USER MUST LOGIN

    if not session.get("user"):
        return redirect(url_for("login"))

    # GET FORM DATA

    product_id = request.form.get("product_id")
    rating = request.form.get("rating")
    comment = request.form.get("comment")

    # VALIDATION

    if not product_id:
        return "Product ID missing"

    if not rating:
        return "Rating missing"

    conn = get_db()
    cursor = conn.cursor()

    try:

        # GET CUSTOMER ID

        cursor.execute("""
            SELECT customer_id
            FROM customers
            WHERE email=%s
        """, (session["user"],))

        customer = cursor.fetchone()

        if not customer:
            return "Customer not found"

        customer_id = customer[0]

        # INSERT REVIEW

        cursor.execute("""
            INSERT INTO reviews
            (
                customer_id,
                product_id,
                rating,
                comment
            )
            VALUES (%s, %s, %s, %s)
        """, (
            customer_id,
            int(product_id),
            int(rating),
            comment
        ))

        conn.commit()

    except Exception as e:

        conn.rollback()

        return f"Error: {str(e)}"

    finally:

        cursor.close()
        conn.close()

    return redirect(request.referrer)

if __name__ == "__main__":
    app.run(debug=True)

