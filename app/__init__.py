import os
from collections import defaultdict
from functools import wraps

from flask import Flask, abort, flash, redirect, render_template, request, session, url_for
from flask_login import LoginManager, current_user, login_required, login_user, logout_user
from slugify import slugify
from werkzeug.security import check_password_hash, generate_password_hash

from .models import Category, Order, OrderItem, Product, Store, User, db

login_manager = LoginManager()
login_manager.login_view = 'login'


def create_app():
    app = Flask(__name__, instance_relative_config=True)
    app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'dev-secret-key')
    database_url = os.getenv('DATABASE_URL', 'sqlite:///delivery_saas.db')
    if database_url.startswith('postgres://'):
        database_url = database_url.replace('postgres://', 'postgresql+psycopg://', 1)
    elif database_url.startswith('postgresql://'):
        database_url = database_url.replace('postgresql://', 'postgresql+psycopg://', 1)
    app.config['SQLALCHEMY_DATABASE_URI'] = database_url
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

    db.init_app(app)
    login_manager.init_app(app)

    with app.app_context():
        db.create_all()
        bootstrap_platform_admin()

    register_routes(app)
    register_template_helpers(app)
    return app


@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))


def bootstrap_platform_admin():
    admin = User.query.filter_by(email='admin@delivery.com').first()
    if not admin:
        admin = User(
            name='Admin Master',
            email='admin@delivery.com',
            password_hash=generate_password_hash('123456'),
            is_platform_admin=True,
        )
        db.session.add(admin)
        db.session.commit()


def register_template_helpers(app):
    @app.context_processor
    def inject_helpers():
        return {
            'cart_count': sum(item.get('quantity', 0) for item in session.get('cart', {}).values()),
        }



def owner_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        store = get_current_store_or_none()
        if not store or store.owner_id != current_user.id:
            abort(403)
        return fn(*args, **kwargs)
    return wrapper



def get_current_store_or_none():
    store_id = session.get('active_store_id')
    if not store_id or not current_user.is_authenticated:
        return None
    return Store.query.filter_by(id=store_id, owner_id=current_user.id).first()



def require_store_setup():
    store = get_current_store_or_none()
    if not store:
        flash('Crie ou selecione uma loja para continuar.', 'warning')
        return redirect(url_for('dashboard'))
    return store



def register_routes(app):
    @app.route('/')
    def home():
        featured_stores = Store.query.filter_by(is_active=True).order_by(Store.created_at.desc()).limit(6).all()
        return render_template('platform/home.html', stores=featured_stores)

    @app.route('/register', methods=['GET', 'POST'])
    def register():
        if request.method == 'POST':
            name = request.form.get('name', '').strip()
            email = request.form.get('email', '').strip().lower()
            phone = request.form.get('phone', '').strip()
            password = request.form.get('password', '')
            if not all([name, email, password]):
                flash('Preencha nome, email e senha.', 'danger')
                return redirect(url_for('register'))
            if User.query.filter_by(email=email).first():
                flash('Este email já está cadastrado.', 'danger')
                return redirect(url_for('register'))
            user = User(name=name, email=email, phone=phone, password_hash=generate_password_hash(password))
            db.session.add(user)
            db.session.commit()
            login_user(user)
            flash('Conta criada com sucesso. Agora crie sua loja.', 'success')
            return redirect(url_for('dashboard'))
        return render_template('platform/register.html')

    @app.route('/login', methods=['GET', 'POST'])
    def login():
        if request.method == 'POST':
            email = request.form.get('email', '').strip().lower()
            password = request.form.get('password', '')
            user = User.query.filter_by(email=email).first()
            if not user or not check_password_hash(user.password_hash, password):
                flash('Email ou senha inválidos.', 'danger')
                return redirect(url_for('login'))
            login_user(user)
            if user.stores and not session.get('active_store_id'):
                session['active_store_id'] = user.stores[0].id
            flash('Login realizado com sucesso.', 'success')
            return redirect(url_for('dashboard'))
        return render_template('platform/login.html')

    @app.route('/logout')
    @login_required
    def logout():
        session.pop('active_store_id', None)
        logout_user()
        flash('Você saiu da plataforma.', 'info')
        return redirect(url_for('home'))

    @app.route('/dashboard')
    @login_required
    def dashboard():
        active_store = get_current_store_or_none()
        if not active_store and current_user.stores:
            active_store = current_user.stores[0]
            session['active_store_id'] = active_store.id
        stats = None
        if active_store:
            orders = Order.query.filter_by(store_id=active_store.id).all()
            stats = {
                'products': Product.query.filter_by(store_id=active_store.id).count(),
                'categories': Category.query.filter_by(store_id=active_store.id).count(),
                'orders': len(orders),
                'revenue': sum(order.total for order in orders),
            }
        return render_template('platform/dashboard.html', active_store=active_store, stats=stats)

    @app.route('/stores/create', methods=['GET', 'POST'])
    @login_required
    def create_store():
        if request.method == 'POST':
            name = request.form.get('name', '').strip()
            slug = slugify(request.form.get('slug', '').strip() or name)
            city = request.form.get('city', '').strip()
            state = request.form.get('state', '').strip()
            if not name or not slug:
                flash('Informe nome e slug da loja.', 'danger')
                return redirect(url_for('create_store'))
            if Store.query.filter_by(slug=slug).first():
                flash('Este link já está em uso. Escolha outro slug.', 'danger')
                return redirect(url_for('create_store'))
            store = Store(
                owner_id=current_user.id,
                name=name,
                slug=slug,
                city=city,
                state=state,
                description=request.form.get('description', ''),
                whatsapp=request.form.get('whatsapp', ''),
            )
            db.session.add(store)
            db.session.commit()
            session['active_store_id'] = store.id
            ensure_default_categories(store)
            flash('Loja criada com sucesso.', 'success')
            return redirect(url_for('store_settings'))
        return render_template('platform/create_store.html')

    @app.route('/stores/switch/<int:store_id>')
    @login_required
    def switch_store(store_id):
        store = Store.query.filter_by(id=store_id, owner_id=current_user.id).first_or_404()
        session['active_store_id'] = store.id
        flash(f'Loja ativa: {store.name}', 'info')
        return redirect(url_for('dashboard'))

    @app.route('/dashboard/store/settings', methods=['GET', 'POST'])
    @login_required
    def store_settings():
        store = require_store_setup()
        if not isinstance(store, Store):
            return store
        if request.method == 'POST':
            store.name = request.form.get('name', store.name).strip()
            new_slug = slugify(request.form.get('slug', store.slug).strip() or store.slug)
            exists = Store.query.filter(Store.slug == new_slug, Store.id != store.id).first()
            if exists:
                flash('Este slug já está em uso.', 'danger')
                return redirect(url_for('store_settings'))
            store.slug = new_slug
            store.description = request.form.get('description', '')
            store.logo_url = request.form.get('logo_url', '')
            store.banner_url = request.form.get('banner_url', '')
            store.primary_color = request.form.get('primary_color', '#EA1D2C')
            store.secondary_color = request.form.get('secondary_color', '#1A1A1A')
            store.accent_color = request.form.get('accent_color', '#FEE7EA')
            store.pix_key = request.form.get('pix_key', '')
            store.pix_holder = request.form.get('pix_holder', '')
            store.min_order_value = float(request.form.get('min_order_value') or 0)
            store.delivery_fee = float(request.form.get('delivery_fee') or 0)
            store.estimated_time = request.form.get('estimated_time', '20-40 min')
            store.whatsapp = request.form.get('whatsapp', '')
            store.address = request.form.get('address', '')
            store.city = request.form.get('city', '')
            store.state = request.form.get('state', '')
            store.open_time = request.form.get('open_time', '18:00')
            store.close_time = request.form.get('close_time', '23:30')
            store.is_open = request.form.get('is_open') == 'on'
            store.is_active = request.form.get('is_active') == 'on'
            db.session.commit()
            flash('Configurações salvas.', 'success')
            return redirect(url_for('store_settings'))
        return render_template('platform/store_settings.html', store=store)

    @app.route('/dashboard/categories', methods=['GET', 'POST'])
    @login_required
    def categories():
        store = require_store_setup()
        if not isinstance(store, Store):
            return store
        if request.method == 'POST':
            name = request.form.get('name', '').strip()
            if name:
                category = Category(store_id=store.id, name=name, sort_order=Category.query.filter_by(store_id=store.id).count() + 1)
                db.session.add(category)
                db.session.commit()
                flash('Categoria criada.', 'success')
            return redirect(url_for('categories'))
        items = Category.query.filter_by(store_id=store.id).order_by(Category.sort_order.asc(), Category.name.asc()).all()
        return render_template('platform/categories.html', store=store, categories=items)

    @app.route('/dashboard/categories/<int:category_id>/delete')
    @login_required
    def delete_category(category_id):
        store = require_store_setup()
        if not isinstance(store, Store):
            return store
        category = Category.query.filter_by(id=category_id, store_id=store.id).first_or_404()
        db.session.delete(category)
        db.session.commit()
        flash('Categoria removida.', 'info')
        return redirect(url_for('categories'))

    @app.route('/dashboard/products', methods=['GET', 'POST'])
    @login_required
    def products():
        store = require_store_setup()
        if not isinstance(store, Store):
            return store
        categories = Category.query.filter_by(store_id=store.id).order_by(Category.sort_order.asc()).all()
        if request.method == 'POST':
            product = Product(
                store_id=store.id,
                category_id=int(request.form.get('category_id')),
                name=request.form.get('name', '').strip(),
                description=request.form.get('description', '').strip(),
                image_url=request.form.get('image_url', '').strip(),
                price=float(request.form.get('price') or 0),
                compare_at_price=float(request.form.get('compare_at_price') or 0) or None,
                is_featured=request.form.get('is_featured') == 'on',
                is_active=request.form.get('is_active') == 'on',
            )
            if not product.name:
                flash('Informe o nome do produto.', 'danger')
                return redirect(url_for('products'))
            db.session.add(product)
            db.session.commit()
            flash('Produto cadastrado.', 'success')
            return redirect(url_for('products'))
        items = Product.query.filter_by(store_id=store.id).order_by(Product.created_at.desc()).all()
        return render_template('platform/products.html', store=store, products=items, categories=categories)

    @app.route('/dashboard/products/<int:product_id>/toggle')
    @login_required
    def toggle_product(product_id):
        store = require_store_setup()
        if not isinstance(store, Store):
            return store
        product = Product.query.filter_by(id=product_id, store_id=store.id).first_or_404()
        product.is_active = not product.is_active
        db.session.commit()
        flash('Produto atualizado.', 'info')
        return redirect(url_for('products'))

    @app.route('/dashboard/orders')
    @login_required
    def orders():
        store = require_store_setup()
        if not isinstance(store, Store):
            return store
        items = Order.query.filter_by(store_id=store.id).order_by(Order.created_at.desc()).all()
        return render_template('platform/orders.html', store=store, orders=items)

    @app.route('/dashboard/orders/<int:order_id>/status', methods=['POST'])
    @login_required
    def update_order_status(order_id):
        store = require_store_setup()
        if not isinstance(store, Store):
            return store
        order = Order.query.filter_by(id=order_id, store_id=store.id).first_or_404()
        order.status = request.form.get('status', order.status)
        db.session.commit()
        flash('Status atualizado.', 'success')
        return redirect(url_for('orders'))

    @app.route('/admin')
    @login_required
    def platform_admin():
        if not current_user.is_platform_admin:
            abort(403)
        stores = Store.query.order_by(Store.created_at.desc()).all()
        users = User.query.order_by(User.created_at.desc()).all()
        orders = Order.query.order_by(Order.created_at.desc()).all()
        return render_template('platform/admin.html', stores=stores, users=users, orders=orders)

    @app.route('/<slug>')
    def public_store(slug):
        store = Store.query.filter_by(slug=slug, is_active=True).first_or_404()
        categories = Category.query.filter_by(store_id=store.id, is_active=True).order_by(Category.sort_order.asc()).all()
        grouped_products = defaultdict(list)
        for product in Product.query.filter_by(store_id=store.id, is_active=True).order_by(Product.is_featured.desc(), Product.created_at.desc()).all():
            grouped_products[product.category_id].append(product)
        featured = Product.query.filter_by(store_id=store.id, is_active=True, is_featured=True).limit(8).all()
        return render_template('store/storefront.html', store=store, categories=categories, grouped_products=grouped_products, featured=featured)

    @app.route('/<slug>/cart/add/<int:product_id>', methods=['POST'])
    def add_to_cart(slug, product_id):
        store = Store.query.filter_by(slug=slug, is_active=True).first_or_404()
        product = Product.query.filter_by(id=product_id, store_id=store.id, is_active=True).first_or_404()
        cart = session.get('cart', {})
        key = f'{store.id}:{product.id}'
        if key not in cart:
            cart[key] = {
                'store_id': store.id,
                'product_id': product.id,
                'name': product.name,
                'price': product.price,
                'image_url': product.image_url,
                'quantity': 0,
            }
        cart[key]['quantity'] += int(request.form.get('quantity', 1) or 1)
        session['cart'] = cart
        flash(f'{product.name} adicionado ao carrinho.', 'success')
        return redirect(url_for('public_store', slug=slug))

    @app.route('/<slug>/cart')
    def view_cart(slug):
        store = Store.query.filter_by(slug=slug, is_active=True).first_or_404()
        items, subtotal = get_store_cart(store.id)
        delivery_fee = store.delivery_fee if subtotal > 0 else 0
        total = subtotal + delivery_fee
        return render_template('store/cart.html', store=store, items=items, subtotal=subtotal, delivery_fee=delivery_fee, total=total)

    @app.route('/<slug>/cart/update', methods=['POST'])
    def update_cart(slug):
        store = Store.query.filter_by(slug=slug, is_active=True).first_or_404()
        cart = session.get('cart', {})
        for key in list(cart.keys()):
            if cart[key]['store_id'] != store.id:
                continue
            qty = int(request.form.get(f'qty_{key}', cart[key]['quantity']) or 0)
            if qty <= 0:
                cart.pop(key, None)
            else:
                cart[key]['quantity'] = qty
        session['cart'] = cart
        flash('Carrinho atualizado.', 'info')
        return redirect(url_for('view_cart', slug=slug))

    @app.route('/<slug>/checkout', methods=['GET', 'POST'])
    def checkout(slug):
        store = Store.query.filter_by(slug=slug, is_active=True).first_or_404()
        items, subtotal = get_store_cart(store.id)
        if not items:
            flash('Seu carrinho está vazio.', 'warning')
            return redirect(url_for('public_store', slug=slug))
        delivery_fee = store.delivery_fee
        if request.method == 'POST':
            customer_name = request.form.get('customer_name', '').strip()
            customer_phone = request.form.get('customer_phone', '').strip()
            customer_address = request.form.get('customer_address', '').strip()
            customer_notes = request.form.get('customer_notes', '').strip()
            fulfillment_type = request.form.get('fulfillment_type', 'delivery')
            payment_method = request.form.get('payment_method', 'pix')
            if not customer_name or not customer_phone:
                flash('Informe nome e telefone.', 'danger')
                return redirect(url_for('checkout', slug=slug))
            if fulfillment_type == 'delivery' and not customer_address:
                flash('Informe o endereço para entrega.', 'danger')
                return redirect(url_for('checkout', slug=slug))
            final_delivery_fee = 0 if fulfillment_type == 'pickup' else delivery_fee
            total = subtotal + final_delivery_fee
            order = Order(
                store_id=store.id,
                customer_name=customer_name,
                customer_phone=customer_phone,
                customer_address=customer_address,
                customer_notes=customer_notes,
                fulfillment_type=fulfillment_type,
                payment_method=payment_method,
                subtotal=subtotal,
                delivery_fee=final_delivery_fee,
                total=total,
            )
            db.session.add(order)
            db.session.flush()
            for item in items:
                db.session.add(OrderItem(
                    order_id=order.id,
                    product_name=item['name'],
                    quantity=item['quantity'],
                    unit_price=item['price'],
                    total_price=item['total'],
                ))
            db.session.commit()
            clear_store_cart(store.id)
            return render_template('store/order_success.html', store=store, order=order)
        total = subtotal + delivery_fee
        return render_template('store/checkout.html', store=store, items=items, subtotal=subtotal, delivery_fee=delivery_fee, total=total)


def ensure_default_categories(store):
    defaults = ['Combos', 'Lanches', 'Bebidas', 'Sobremesas']
    if Category.query.filter_by(store_id=store.id).count() == 0:
        for i, name in enumerate(defaults, start=1):
            db.session.add(Category(store_id=store.id, name=name, sort_order=i))
        db.session.commit()



def get_store_cart(store_id):
    cart = session.get('cart', {})
    items = []
    subtotal = 0
    for item in cart.values():
        if item['store_id'] != store_id:
            continue
        total = item['price'] * item['quantity']
        subtotal += total
        items.append({**item, 'key': f"{item['store_id']}:{item['product_id']}", 'total': total})
    return items, subtotal



def clear_store_cart(store_id):
    cart = session.get('cart', {})
    remaining = {k: v for k, v in cart.items() if v['store_id'] != store_id}
    session['cart'] = remaining
