import os
from datetime import datetime, date
from decimal import Decimal
from functools import wraps

import click
from flask import Flask, render_template, redirect, url_for, flash, request, abort
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from flask_sqlalchemy import SQLAlchemy
from flask_wtf.csrf import CSRFProtect
from sqlalchemy import func, or_
from werkzeug.security import generate_password_hash, check_password_hash

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'change-this-secret-key-before-deployment')
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv(
    'DATABASE_URL', 'mysql+pymysql://fertilizer_user:change_me@localhost/fertilizer_store?charset=utf8mb4'
)
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {'pool_pre_ping': True}

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'
login_manager.login_message_category = 'warning'
csrf = CSRFProtect(app)


def money(value):
    return f"₹{Decimal(value or 0):,.2f}"
app.jinja_env.filters['money'] = money


class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    full_name = db.Column(db.String(120), nullable=False)
    username = db.Column(db.String(80), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False, default='Employee')
    active = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    @property
    def is_active(self):
        return self.active

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


class Product(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(160), nullable=False, index=True)
    sku = db.Column(db.String(60), unique=True, nullable=False)
    category = db.Column(db.String(100), nullable=False, default='Fertilizer')
    unit = db.Column(db.String(30), nullable=False, default='bag')
    purchase_price = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    selling_price = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    stock_qty = db.Column(db.Integer, nullable=False, default=0)
    min_stock = db.Column(db.Integer, nullable=False, default=5)
    active = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)


class Customer(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    phone = db.Column(db.String(30), nullable=True)
    address = db.Column(db.String(255), nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)


class Supplier(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(140), nullable=False)
    phone = db.Column(db.String(30), nullable=True)
    email = db.Column(db.String(120), nullable=True)
    address = db.Column(db.String(255), nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)


class Purchase(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    supplier_id = db.Column(db.Integer, db.ForeignKey('supplier.id'), nullable=True)
    product_id = db.Column(db.Integer, db.ForeignKey('product.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    unit_cost = db.Column(db.Numeric(12, 2), nullable=False)
    total_cost = db.Column(db.Numeric(12, 2), nullable=False)
    notes = db.Column(db.String(255), nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    supplier = db.relationship('Supplier')
    product = db.relationship('Product')
    user = db.relationship('User')


class Sale(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    invoice_number = db.Column(db.String(40), unique=True, nullable=False, index=True)
    customer_id = db.Column(db.Integer, db.ForeignKey('customer.id'), nullable=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    subtotal = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    discount = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    total = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    payment_method = db.Column(db.String(30), nullable=False, default='Cash')
    notes = db.Column(db.String(255), nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    customer = db.relationship('Customer')
    user = db.relationship('User')
    items = db.relationship('SaleItem', backref='sale', cascade='all, delete-orphan', lazy=True)


class SaleItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    sale_id = db.Column(db.Integer, db.ForeignKey('sale.id'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('product.id'), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    unit_price = db.Column(db.Numeric(12, 2), nullable=False)
    line_total = db.Column(db.Numeric(12, 2), nullable=False)
    product = db.relationship('Product')


class Expense(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(140), nullable=False)
    amount = db.Column(db.Numeric(12, 2), nullable=False)
    category = db.Column(db.String(80), nullable=False, default='General')
    notes = db.Column(db.String(255), nullable=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    user = db.relationship('User')


class StockMovement(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey('product.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    movement_type = db.Column(db.String(20), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    reference = db.Column(db.String(80), nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    product = db.relationship('Product')
    user = db.relationship('User')


@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))


def owner_required(view):
    @wraps(view)
    @login_required
    def wrapped(*args, **kwargs):
        if current_user.role != 'Owner':
            abort(403)
        return view(*args, **kwargs)
    return wrapped


def parse_decimal(value, field_name, minimum=Decimal('0')):
    try:
        amount = Decimal(value or '0')
        if not amount.is_finite() or amount < minimum:
            raise ValueError
        return amount.quantize(Decimal('0.01'))
    except Exception:
        raise ValueError(f'{field_name} must be a valid amount greater than or equal to {minimum}.')


def parse_int(value, field_name, minimum=0):
    try:
        number = int(value)
        if number < minimum:
            raise ValueError
        return number
    except Exception:
        raise ValueError(f'{field_name} must be a whole number greater than or equal to {minimum}.')


@app.cli.command('init-db')
def init_db_command():
    """Create database tables after configuring DATABASE_URL."""
    db.create_all()
    click.echo('Database tables created.')


@app.cli.command('create-owner')
@click.option('--name', prompt='Owner full name')
@click.option('--username', prompt='Owner username')
@click.password_option()
def create_owner(name, username, password):
    """Create the first Owner account; never exposes public registration."""
    db.create_all()
    if User.query.filter_by(username=username).first():
        raise click.ClickException('That username already exists.')
    if User.query.filter_by(role='Owner').first():
        raise click.ClickException('An Owner account already exists. Add further employees from the Owner dashboard.')
    user = User(full_name=name.strip(), username=username.strip(), role='Owner')
    user.set_password(password)
    db.session.add(user)
    db.session.commit()
    click.echo(f'Owner account created for {username}.')


@app.route('/')
def index():
    return redirect(url_for('dashboard' if current_user.is_authenticated else 'login'))


@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        user = User.query.filter_by(username=username, active=True).first()
        if user and user.check_password(password):
            login_user(user)
            flash('Welcome back.', 'success')
            return redirect(url_for('dashboard'))
        flash('Invalid username or password.', 'danger')
    return render_template('login.html')


@app.route('/logout', methods=['POST'])
@login_required
def logout():
    logout_user()
    flash('You have been logged out.', 'info')
    return redirect(url_for('login'))


@app.route('/dashboard')
@login_required
def dashboard():
    today = date.today()
    today_start = datetime.combine(today, datetime.min.time())
    if current_user.role == 'Owner':
        today_sales = db.session.query(func.coalesce(func.sum(Sale.total), 0)).filter(Sale.created_at >= today_start).scalar()
        all_sales = db.session.query(func.coalesce(func.sum(Sale.total), 0)).scalar()
        expenses_today = db.session.query(func.coalesce(func.sum(Expense.amount), 0)).filter(Expense.created_at >= today_start).scalar()
        product_count = Product.query.filter_by(active=True).count()
        low_stock = Product.query.filter(Product.active.is_(True), Product.stock_qty <= Product.min_stock).order_by(Product.stock_qty.asc()).limit(8).all()
        recent_sales = Sale.query.order_by(Sale.created_at.desc()).limit(8).all()
        return render_template('dashboard_owner.html', today_sales=today_sales, all_sales=all_sales,
                               expenses_today=expenses_today, product_count=product_count,
                               low_stock=low_stock, recent_sales=recent_sales)
    own_today = db.session.query(func.coalesce(func.sum(Sale.total), 0)).filter(Sale.user_id == current_user.id, Sale.created_at >= today_start).scalar()
    own_count = Sale.query.filter_by(user_id=current_user.id).filter(Sale.created_at >= today_start).count()
    products = Product.query.filter_by(active=True).order_by(Product.name.asc()).all()
    low_stock_count = Product.query.filter(Product.active.is_(True), Product.stock_qty <= Product.min_stock).count()
    recent_sales = Sale.query.filter_by(user_id=current_user.id).order_by(Sale.created_at.desc()).limit(8).all()
    return render_template('dashboard_employee.html', own_today=own_today, own_count=own_count,
                           products=products, low_stock_count=low_stock_count, recent_sales=recent_sales)


@app.route('/products')
@login_required
def products():
    search = request.args.get('q', '').strip()
    query = Product.query.filter_by(active=True)
    if search:
        like = f'%{search}%'
        query = query.filter(or_(Product.name.ilike(like), Product.sku.ilike(like), Product.category.ilike(like)))
    items = query.order_by(Product.name.asc()).all()
    return render_template('products.html', products=items, search=search)


@app.route('/products/new', methods=['GET', 'POST'])
@owner_required
def product_new():
    if request.method == 'POST':
        try:
            name = request.form.get('name', '').strip()
            sku = request.form.get('sku', '').strip().upper()
            if not name or not sku:
                raise ValueError('Product name and SKU are required.')
            if Product.query.filter_by(sku=sku).first():
                raise ValueError('SKU already exists. Use a unique SKU.')
            p = Product(name=name, sku=sku, category=request.form.get('category', 'Fertilizer').strip() or 'Fertilizer',
                        unit=request.form.get('unit', 'bag').strip() or 'bag',
                        purchase_price=parse_decimal(request.form.get('purchase_price'), 'Purchase price'),
                        selling_price=parse_decimal(request.form.get('selling_price'), 'Selling price'),
                        stock_qty=parse_int(request.form.get('stock_qty'), 'Opening stock'),
                        min_stock=parse_int(request.form.get('min_stock'), 'Minimum stock'))
            db.session.add(p)
            db.session.flush()
            if p.stock_qty:
                db.session.add(StockMovement(product_id=p.id, user_id=current_user.id, movement_type='Opening', quantity=p.stock_qty, reference='Opening stock'))
            db.session.commit()
            flash('Product created successfully.', 'success')
            return redirect(url_for('products'))
        except ValueError as exc:
            db.session.rollback()
            flash(str(exc), 'danger')
    return render_template('product_form.html', product=None)


@app.route('/products/<int:product_id>/edit', methods=['GET', 'POST'])
@owner_required
def product_edit(product_id):
    product = db.get_or_404(Product, product_id)
    if request.method == 'POST':
        try:
            name = request.form.get('name', '').strip()
            sku = request.form.get('sku', '').strip().upper()
            duplicate = Product.query.filter(Product.sku == sku, Product.id != product.id).first()
            if not name or not sku:
                raise ValueError('Product name and SKU are required.')
            if duplicate:
                raise ValueError('SKU already exists. Use a unique SKU.')
            product.name = name
            product.sku = sku
            product.category = request.form.get('category', 'Fertilizer').strip() or 'Fertilizer'
            product.unit = request.form.get('unit', 'bag').strip() or 'bag'
            product.purchase_price = parse_decimal(request.form.get('purchase_price'), 'Purchase price')
            product.selling_price = parse_decimal(request.form.get('selling_price'), 'Selling price')
            product.min_stock = parse_int(request.form.get('min_stock'), 'Minimum stock')
            db.session.commit()
            flash('Product updated.', 'success')
            return redirect(url_for('products'))
        except ValueError as exc:
            db.session.rollback()
            flash(str(exc), 'danger')
    return render_template('product_form.html', product=product)


@app.route('/products/<int:product_id>/archive', methods=['POST'])
@owner_required
def product_archive(product_id):
    product = db.get_or_404(Product, product_id)
    product.active = False
    db.session.commit()
    flash('Product archived. Past sales records are preserved.', 'success')
    return redirect(url_for('products'))


@app.route('/customers', methods=['GET', 'POST'])
@login_required
def customers():
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        if not name:
            flash('Customer name is required.', 'danger')
        else:
            db.session.add(Customer(name=name, phone=request.form.get('phone', '').strip() or None,
                                    address=request.form.get('address', '').strip() or None))
            db.session.commit()
            flash('Customer added.', 'success')
            return redirect(url_for('customers'))
    items = Customer.query.order_by(Customer.name.asc()).all()
    return render_template('customers.html', customers=items)


@app.route('/suppliers', methods=['GET', 'POST'])
@owner_required
def suppliers():
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        if not name:
            flash('Supplier name is required.', 'danger')
        else:
            db.session.add(Supplier(name=name, phone=request.form.get('phone', '').strip() or None,
                                    email=request.form.get('email', '').strip() or None,
                                    address=request.form.get('address', '').strip() or None))
            db.session.commit()
            flash('Supplier added.', 'success')
            return redirect(url_for('suppliers'))
    items = Supplier.query.order_by(Supplier.name.asc()).all()
    return render_template('suppliers.html', suppliers=items)


@app.route('/employees', methods=['GET', 'POST'])
@owner_required
def employees():
    if request.method == 'POST':
        name = request.form.get('full_name', '').strip()
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        if not name or not username or len(password) < 8:
            flash('Name and username are required; password must contain at least 8 characters.', 'danger')
        elif User.query.filter_by(username=username).first():
            flash('That username is already in use.', 'danger')
        else:
            employee = User(full_name=name, username=username, role='Employee')
            employee.set_password(password)
            db.session.add(employee)
            db.session.commit()
            flash('Employee account created.', 'success')
            return redirect(url_for('employees'))
    items = User.query.order_by(User.created_at.desc()).all()
    return render_template('employees.html', employees=items)


@app.route('/employees/<int:user_id>/toggle', methods=['POST'])
@owner_required
def employee_toggle(user_id):
    user = db.get_or_404(User, user_id)
    if user.role == 'Owner':
        abort(403)
    user.active = not user.active
    db.session.commit()
    flash(f"Employee account {'enabled' if user.active else 'disabled'}.", 'success')
    return redirect(url_for('employees'))


@app.route('/purchases', methods=['GET', 'POST'])
@owner_required
def purchases():
    if request.method == 'POST':
        try:
            product = db.get_or_404(Product, parse_int(request.form.get('product_id'), 'Product', 1))
            quantity = parse_int(request.form.get('quantity'), 'Quantity', 1)
            unit_cost = parse_decimal(request.form.get('unit_cost'), 'Unit cost')
            supplier_raw = request.form.get('supplier_id', '').strip()
            supplier_id = parse_int(supplier_raw, 'Supplier', 1) if supplier_raw else None
            if supplier_id and not db.session.get(Supplier, supplier_id):
                raise ValueError('Select a valid supplier.')
            purchase = Purchase(supplier_id=supplier_id, product_id=product.id, user_id=current_user.id,
                                quantity=quantity, unit_cost=unit_cost, total_cost=unit_cost * quantity,
                                notes=request.form.get('notes', '').strip() or None)
            product.stock_qty += quantity
            product.purchase_price = unit_cost
            db.session.add(purchase)
            db.session.flush()
            db.session.add(StockMovement(product_id=product.id, user_id=current_user.id, movement_type='Purchase', quantity=quantity, reference=f'Purchase #{purchase.id}'))
            db.session.commit()
            flash('Purchase recorded and stock increased.', 'success')
            return redirect(url_for('purchases'))
        except ValueError as exc:
            db.session.rollback()
            flash(str(exc), 'danger')
    records = Purchase.query.order_by(Purchase.created_at.desc()).limit(100).all()
    return render_template('purchases.html', purchases=records, products=Product.query.filter_by(active=True).order_by(Product.name).all(), suppliers=Supplier.query.order_by(Supplier.name).all())


@app.route('/sales/new', methods=['GET', 'POST'])
@login_required
def sale_new():
    active_products = Product.query.filter_by(active=True).filter(Product.stock_qty > 0).order_by(Product.name).all()
    customer_list = Customer.query.order_by(Customer.name).all()
    if request.method == 'POST':
        try:
            product_ids = request.form.getlist('product_id[]')
            quantities = request.form.getlist('quantity[]')
            if not product_ids or len(product_ids) != len(quantities):
                raise ValueError('Add at least one valid product to the bill.')
            customer_raw = request.form.get('customer_id', '').strip()
            customer_id = parse_int(customer_raw, 'Customer', 1) if customer_raw else None
            if customer_id and not db.session.get(Customer, customer_id):
                raise ValueError('Select a valid customer.')
            discount = parse_decimal(request.form.get('discount', '0'), 'Discount')
            payment_method = request.form.get('payment_method', 'Cash')
            if payment_method not in {'Cash', 'UPI', 'Card', 'Bank Transfer', 'Credit'}:
                raise ValueError('Select a valid payment method.')
            parsed = []
            subtotal = Decimal('0.00')
            aggregated = {}
            for raw_id, raw_qty in zip(product_ids, quantities):
                pid = parse_int(raw_id, 'Product', 1)
                qty = parse_int(raw_qty, 'Quantity', 1)
                aggregated[pid] = aggregated.get(pid, 0) + qty
            # Lock product rows where supported to reduce overselling in concurrent sales.
            for pid, qty in aggregated.items():
                product = Product.query.filter_by(id=pid, active=True).with_for_update().first()
                if not product:
                    raise ValueError('One selected product is no longer available.')
                if product.stock_qty < qty:
                    raise ValueError(f'Insufficient stock for {product.name}. Available: {product.stock_qty}.')
                line_total = Decimal(product.selling_price) * qty
                subtotal += line_total
                parsed.append((product, qty, Decimal(product.selling_price), line_total))
            if discount > subtotal:
                raise ValueError('Discount cannot exceed the subtotal.')
            sale = Sale(invoice_number='TEMP', customer_id=customer_id, user_id=current_user.id,
                        subtotal=subtotal, discount=discount, total=subtotal-discount,
                        payment_method=payment_method, notes=request.form.get('notes', '').strip() or None)
            db.session.add(sale)
            db.session.flush()
            sale.invoice_number = f'INV-{datetime.utcnow():%Y%m%d}-{sale.id:06d}'
            for product, qty, unit_price, line_total in parsed:
                product.stock_qty -= qty
                db.session.add(SaleItem(sale_id=sale.id, product_id=product.id, quantity=qty,
                                        unit_price=unit_price, line_total=line_total))
                db.session.add(StockMovement(product_id=product.id, user_id=current_user.id,
                                             movement_type='Sale', quantity=-qty, reference=sale.invoice_number))
            db.session.commit()
            flash(f'Sale completed. Invoice {sale.invoice_number} created.', 'success')
            return redirect(url_for('invoice', sale_id=sale.id))
        except ValueError as exc:
            db.session.rollback()
            flash(str(exc), 'danger')
    return render_template('sale_new.html', products=active_products, customers=customer_list)


@app.route('/sales')
@login_required
def sales():
    query = Sale.query
    if current_user.role != 'Owner':
        query = query.filter_by(user_id=current_user.id)
    records = query.order_by(Sale.created_at.desc()).limit(200).all()
    return render_template('sales.html', sales=records)


@app.route('/invoice/<int:sale_id>')
@login_required
def invoice(sale_id):
    sale = db.get_or_404(Sale, sale_id)
    if current_user.role != 'Owner' and sale.user_id != current_user.id:
        abort(403)
    return render_template('invoice.html', sale=sale)


@app.route('/expenses', methods=['GET', 'POST'])
@owner_required
def expenses():
    if request.method == 'POST':
        try:
            title = request.form.get('title', '').strip()
            if not title:
                raise ValueError('Expense title is required.')
            amount = parse_decimal(request.form.get('amount'), 'Amount', Decimal('0.01'))
            db.session.add(Expense(title=title, amount=amount,
                                   category=request.form.get('category', 'General').strip() or 'General',
                                   notes=request.form.get('notes', '').strip() or None, user_id=current_user.id))
            db.session.commit()
            flash('Expense recorded.', 'success')
            return redirect(url_for('expenses'))
        except ValueError as exc:
            db.session.rollback()
            flash(str(exc), 'danger')
    records = Expense.query.order_by(Expense.created_at.desc()).limit(200).all()
    return render_template('expenses.html', expenses=records)


@app.route('/reports')
@owner_required
def reports():
    start_text = request.args.get('start', date.today().replace(day=1).isoformat())
    end_text = request.args.get('end', date.today().isoformat())
    try:
        start_date = date.fromisoformat(start_text)
        end_date = date.fromisoformat(end_text)
        if end_date < start_date:
            raise ValueError
    except ValueError:
        flash('Choose a valid date range.', 'danger')
        start_date = date.today().replace(day=1)
        end_date = date.today()
    start_dt = datetime.combine(start_date, datetime.min.time())
    end_dt = datetime.combine(end_date, datetime.max.time())
    range_sales = Sale.query.filter(Sale.created_at >= start_dt, Sale.created_at <= end_dt).order_by(Sale.created_at.desc()).all()
    revenue = sum((Decimal(s.total) for s in range_sales), Decimal('0.00'))
    expenses_total = db.session.query(func.coalesce(func.sum(Expense.amount), 0)).filter(Expense.created_at >= start_dt, Expense.created_at <= end_dt).scalar()
    purchase_total = db.session.query(func.coalesce(func.sum(Purchase.total_cost), 0)).filter(Purchase.created_at >= start_dt, Purchase.created_at <= end_dt).scalar()
    return render_template('reports.html', sales=range_sales, revenue=revenue, expenses_total=expenses_total,
                           purchase_total=purchase_total, start=start_date.isoformat(), end=end_date.isoformat())


@app.route('/stock-movements')
@owner_required
def stock_movements():
    records = StockMovement.query.order_by(StockMovement.created_at.desc()).limit(300).all()
    return render_template('stock_movements.html', movements=records)


@app.errorhandler(403)
def forbidden(_error):
    return render_template('error.html', code=403, message='You do not have permission to access this page.'), 403


@app.errorhandler(404)
def not_found(_error):
    return render_template('error.html', code=404, message='The requested page could not be found.'), 404


if __name__ == '__main__':
    # For local development only. Use a production WSGI server when deployed.
    app.run(debug=os.getenv('FLASK_DEBUG', '0') == '1')
