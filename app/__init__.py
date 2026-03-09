import base64
import io
import os
from collections import defaultdict
from functools import wraps

import qrcode
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

    default_sqlite_path = '/data/delivery_saas.db'
    try:
        os.makedirs('/data', exist_ok=True)
    except Exception:
        default_sqlite_path = os.path.join(app.instance_path, 'delivery_saas.db')
        os.makedirs(app.instance_path, exist_ok=True)

    database_url = os.getenv('DATABASE_URL', f'sqlite:///{default_sqlite_path}')
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
        recent_orders = session.get('recent_orders', {})
        current_slug = request.view_args.get('slug') if request.view_args else None
        return {
            'cart_count': sum(item.get('quantity', 0) for item in session.get('cart', {}).values()),
            'recent_orders_count': len(recent_orders.get(current_slug, [])) if current_slug else 0,
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
            existing_store = Store.query.filter_by(slug=new_slug).first()
            if existing_store and existing_store.id != store.id:
                flash('Este slug já está em uso.', 'danger')
                return redirect(url_for('store_settings'))
            store.slug = new_slug
            store.description = request.form.get('description', '').strip()
            store.logo_url = request.form.get('logo_url', '').strip()
            store.banner_url = request.form.get('banner_url', '').strip()
            store.primary_color = request.form.get('primary_color', store.primary_color)
            store.secondary_color = request.form.get('secondary_color', store.secondary_color)
            store.accent_color = request.form.get('accent_color', store.accent_color)
            store.estimated_time = request.form.get('estimated_time', store.estimated_time).strip()
            store.delivery_fee = float(request.form.get('delivery_fee') or 0)
            store.min_order_value = float(request.form.get('min_order_value') or 0)
            store.whatsapp = request.form.get('whatsapp', '').strip()
            store.address = request.form.get('address', '').strip()
            store.city = request.form.get('city', '').strip()
            store.state = request.form.get('state', '').strip()
            store.open_time = request.form.get('open_time', store.open_time).strip()
            store.close_time = request.form.get('close_time', store.close_time).strip()
            store.pix_holder = request.form.get('pix_holder', '').strip()
            store.pix_key = request.form.get('pix_key', '').strip()
            store.is_open = request.form.get('is_open') == 'on'
            store.is_active = request.form.get('is_active') == 'on'
            db.session.commit()
            flash('Configurações salvas com sucesso.', 'success')
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

    @app.route('/dashboard/products/<int:product_id>/edit', methods=['POST'])
    @login_required
    def edit_product(product_id):
        store = require_store_setup()
        if not isinstance(store, Store):
            return store
        product = Product.query.filter_by(id=product_id, store_id=store.id).first_or_404()
        product.category_id = int(request.form.get('category_id') or product.category_id)
        product.name = request.form.get('name', '').strip()
        product.description = request.form.get('description', '').strip()
        product.image_url = request.form.get('image_url', '').strip()
        product.price = float(request.form.get('price') or 0)
        product.compare_at_price = float(request.form.get('compare_at_price') or 0) or None
        product.is_featured = request.form.get('is_featured') == 'on'
        product.is_active = request.form.get('is_active') == 'on'
        if not product.name:
            flash('Informe o nome do produto.', 'danger')
            return redirect(url_for('products'))
        db.session.commit()
        flash('Produto atualizado com sucesso.', 'success')
        return redirect(url_for('products'))

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
        all_products = Product.query.filter_by(store_id=store.id, is_active=True).order_by(Product.is_featured.desc(), Product.created_at.desc()).all()
        q = request.args.get('q', '').strip().lower()
        for product in all_products:
            if q and q not in f'{product.name} {product.description or ""}'.lower():
                continue
            grouped_products[product.category_id].append(product)
        featured = Product.query.filter_by(store_id=store.id, is_active=True, is_featured=True).limit(8).all()
        return render_template('store/storefront.html', store=store, categories=categories, grouped_products=grouped_products, featured=featured, query=q)

    @app.route('/<slug>/produto/<int:product_id>')
    def product_detail(slug, product_id):
        store = Store.query.filter_by(slug=slug, is_active=True).first_or_404()
        product = Product.query.filter_by(id=product_id, store_id=store.id, is_active=True).first_or_404()
        suggested_drinks = Product.query.filter(
            Product.store_id == store.id,
            Product.is_active.is_(True),
            Product.id != product.id,
            db.or_(
                Product.name.ilike('%coca%'),
                Product.name.ilike('%refrigerante%'),
                Product.name.ilike('%suco%'),
                Product.name.ilike('%água%'),
                Product.name.ilike('%agua%'),
                Product.name.ilike('%guaraná%'),
                Product.name.ilike('%guarana%')
            )
        ).order_by(Product.is_featured.desc(), Product.created_at.desc()).limit(6).all()
        if not suggested_drinks:
            suggested_drinks = Product.query.filter(
                Product.store_id == store.id,
                Product.is_active.is_(True),
                Product.id != product.id
            ).order_by(Product.is_featured.desc(), Product.created_at.desc()).limit(6).all()

        more_items = Product.query.filter(
            Product.store_id == store.id,
            Product.is_active.is_(True),
            Product.id != product.id
        ).order_by(Product.is_featured.desc(), Product.created_at.desc()).limit(8).all()
        return render_template(
            'store/product_detail.html',
            store=store,
            product=product,
            suggested_drinks=suggested_drinks,
            more_items=more_items,
        )

    @app.route('/<slug>/cart/add/<int:product_id>', methods=['POST'])
    def add_to_cart(slug, product_id):
        store = Store.query.filter_by(slug=slug, is_active=True).first_or_404()
        product = Product.query.filter_by(id=product_id, store_id=store.id, is_active=True).first_or_404()
        cart = session.get('cart', {})

        quantity = max(1, int(request.form.get('quantity', 1) or 1))
        notes = request.form.get('notes', '').strip()
        addon_ids = [int(v) for v in request.form.getlist('addon_ids') if str(v).isdigit()]
        addon_products = []
        addon_total = 0
        if addon_ids:
            addon_products = Product.query.filter(
                Product.store_id == store.id,
                Product.is_active.is_(True),
                Product.id.in_(addon_ids)
            ).all()
            addon_total = sum(item.price for item in addon_products)

        addon_key = '-'.join(str(item.id) for item in addon_products)
        key = f'{store.id}:{product.id}:{notes}:{addon_key}'
        if key not in cart:
            cart[key] = {
                'store_id': store.id,
                'product_id': product.id,
                'name': product.name,
                'base_price': product.price,
                'price': product.price + addon_total,
                'image_url': product.image_url,
                'quantity': 0,
                'notes': notes,
                'addons': [{'id': item.id, 'name': item.name, 'price': item.price} for item in addon_products],
            }
        cart[key]['quantity'] += quantity
        cart[key]['price'] = product.price + addon_total
        session['cart'] = cart
        flash(f'{product.name} adicionado ao carrinho.', 'success')
        return redirect(url_for('view_cart', slug=slug))

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

        customer_info = session.get('customer_info', {})
        selected_type = request.form.get('fulfillment_type') or customer_info.get('fulfillment_type', 'delivery')
        delivery_fee = 0 if selected_type == 'pickup' else store.delivery_fee

        if request.method == 'POST':
            customer_name = request.form.get('customer_name', '').strip()
            customer_phone = request.form.get('customer_phone', '').strip()
            customer_notes = request.form.get('customer_notes', '').strip()
            fulfillment_type = request.form.get('fulfillment_type', 'delivery')
            payment_method = request.form.get('payment_method', 'pix')

            zipcode = request.form.get('customer_zipcode', '').strip()
            street = request.form.get('customer_street', '').strip()
            number = request.form.get('customer_number', '').strip()
            complement = request.form.get('customer_complement', '').strip()
            neighborhood = request.form.get('customer_neighborhood', '').strip()
            city = request.form.get('customer_city', '').strip()
            state = request.form.get('customer_state', '').strip()
            reference = request.form.get('customer_reference', '').strip()

            customer_address = format_address(street, number, neighborhood, city, state, zipcode, complement, reference)

            session['customer_info'] = {
                'customer_name': customer_name,
                'customer_phone': customer_phone,
                'customer_zipcode': zipcode,
                'customer_street': street,
                'customer_number': number,
                'customer_complement': complement,
                'customer_neighborhood': neighborhood,
                'customer_city': city,
                'customer_state': state,
                'customer_reference': reference,
                'fulfillment_type': fulfillment_type,
                'payment_method': payment_method,
                'customer_notes': customer_notes,
            }

            if not customer_name or not customer_phone:
                flash('Informe nome e telefone.', 'danger')
                return redirect(url_for('checkout', slug=slug))
            if fulfillment_type == 'delivery' and (not street or not number or not neighborhood):
                flash('Preencha CEP, rua, número e bairro para entrega.', 'danger')
                return redirect(url_for('checkout', slug=slug))

            final_delivery_fee = 0 if fulfillment_type == 'pickup' else store.delivery_fee
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
                item_label = item['name']
                extras = []
                if item.get('notes'):
                    extras.append(f"Obs: {item['notes']}")
                if item.get('addons'):
                    extras.append("Adicionais: " + ', '.join(addon['name'] for addon in item.get('addons', [])))
                if extras:
                    item_label = f"{item_label} ({' | '.join(extras)})"
                db.session.add(OrderItem(
                    order_id=order.id,
                    product_name=item_label,
                    quantity=item['quantity'],
                    unit_price=item['price'],
                    total_price=item['total'],
                ))
            db.session.commit()
            remember_recent_order(store.slug, order.id)
            clear_store_cart(store.id)
            return redirect(url_for('order_success', slug=slug, order_id=order.id))

        total = subtotal + delivery_fee
        return render_template('store/checkout.html', store=store, items=items, subtotal=subtotal, delivery_fee=delivery_fee, total=total, customer_info=customer_info)

    @app.route('/<slug>/pedido/<int:order_id>/sucesso')
    def order_success(slug, order_id):
        store = Store.query.filter_by(slug=slug, is_active=True).first_or_404()
        order = Order.query.filter_by(id=order_id, store_id=store.id).first_or_404()
        if order.id not in session.get('recent_orders', {}).get(slug, []):
            abort(403)
        pix_code = None
        pix_qr_base64 = None
        if order.payment_method == 'pix' and store.pix_key:
            pix_code = build_pix_payload(store, order)
            pix_qr_base64 = build_qr_base64(pix_code)
        return render_template('store/order_success.html', store=store, order=order, pix_code=pix_code, pix_qr_base64=pix_qr_base64)

    @app.route('/<slug>/meus-pedidos')
    def my_orders(slug):
        store = Store.query.filter_by(slug=slug, is_active=True).first_or_404()
        ids = session.get('recent_orders', {}).get(slug, [])
        orders = []
        if ids:
            orders = Order.query.filter(Order.store_id == store.id, Order.id.in_(ids)).order_by(Order.created_at.desc()).all()
        return render_template('store/my_orders.html', store=store, orders=orders)

    @app.route('/<slug>/pedido/<int:order_id>')
    def order_detail(slug, order_id):
        store = Store.query.filter_by(slug=slug, is_active=True).first_or_404()
        if order_id not in session.get('recent_orders', {}).get(slug, []):
            abort(403)
        order = Order.query.filter_by(id=order_id, store_id=store.id).first_or_404()
        return render_template('store/order_detail.html', store=store, order=order)


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


def remember_recent_order(slug, order_id):
    recent = session.get('recent_orders', {})
    store_orders = recent.get(slug, [])
    if order_id not in store_orders:
        store_orders.insert(0, order_id)
    recent[slug] = store_orders[:20]
    session['recent_orders'] = recent


def format_address(street, number, neighborhood, city, state, zipcode, complement='', reference=''):
    parts = []
    first_line = ', '.join([p for p in [street, number] if p])
    if first_line:
        parts.append(first_line)
    second_line = ' - '.join([p for p in [neighborhood, city, state] if p])
    if second_line:
        parts.append(second_line)
    if zipcode:
        parts.append(f'CEP {zipcode}')
    if complement:
        parts.append(f'Compl.: {complement}')
    if reference:
        parts.append(f'Ref.: {reference}')
    return ' | '.join(parts)


def build_qr_base64(payload):
    img = qrcode.make(payload)
    buffer = io.BytesIO()
    img.save(buffer, format='PNG')
    return base64.b64encode(buffer.getvalue()).decode('utf-8')


def build_pix_payload(store, order):
    pix_key = (store.pix_key or '').strip()
    if not pix_key:
        return ''
    merchant_name = normalize_pix_text(store.pix_holder or store.name, 25)
    merchant_city = normalize_pix_text(store.city or 'CIDADE', 15)
    amount = f'{order.total:.2f}'
    txid = f'PED{order.id}'[:25]

    merchant_account = emv('00', 'br.gov.bcb.pix') + emv('01', pix_key)
    additional = emv('05', txid)
    payload = (
        emv('00', '01') +
        emv('01', '12') +
        emv('26', merchant_account) +
        emv('52', '0000') +
        emv('53', '986') +
        emv('54', amount) +
        emv('58', 'BR') +
        emv('59', merchant_name) +
        emv('60', merchant_city) +
        emv('62', additional) +
        '6304'
    )
    return payload + crc16(payload)


def normalize_pix_text(value, max_len):
    value = (value or '').upper()
    translated = ''.join(ch for ch in value if ch.isalnum() or ch == ' ')
    translated = ' '.join(translated.split())
    return translated[:max_len] or 'LOJA'


def emv(identifier, value):
    value = str(value)
    return f'{identifier}{len(value):02d}{value}'


def crc16(payload):
    polynomial = 0x1021
    result = 0xFFFF
    for byte in payload.encode('utf-8'):
        result ^= byte << 8
        for _ in range(8):
            if result & 0x8000:
                result = (result << 1) ^ polynomial
            else:
                result <<= 1
            result &= 0xFFFF
    return f'{result:04X}'
