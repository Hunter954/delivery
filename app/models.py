from datetime import datetime
from flask_login import UserMixin
from flask_sqlalchemy import SQLAlchemy


db = SQLAlchemy()


class TimestampMixin:
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


class User(UserMixin, TimestampMixin, db.Model):
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    phone = db.Column(db.String(30))
    password_hash = db.Column(db.String(255), nullable=False)
    is_platform_admin = db.Column(db.Boolean, default=False, nullable=False)

    stores = db.relationship('Store', backref='owner', lazy=True)


class Store(TimestampMixin, db.Model):
    __tablename__ = 'stores'

    id = db.Column(db.Integer, primary_key=True)
    owner_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    name = db.Column(db.String(120), nullable=False)
    slug = db.Column(db.String(80), unique=True, nullable=False, index=True)
    description = db.Column(db.Text)
    logo_url = db.Column(db.String(500))
    banner_url = db.Column(db.String(500))
    primary_color = db.Column(db.String(20), default='#EA1D2C', nullable=False)
    secondary_color = db.Column(db.String(20), default='#1A1A1A', nullable=False)
    accent_color = db.Column(db.String(20), default='#FEE7EA', nullable=False)
    pix_key = db.Column(db.String(255))
    pix_holder = db.Column(db.String(120))
    min_order_value = db.Column(db.Float, default=0)
    delivery_fee = db.Column(db.Float, default=0)
    estimated_time = db.Column(db.String(40), default='20-40 min')
    whatsapp = db.Column(db.String(30))
    address = db.Column(db.String(255))
    city = db.Column(db.String(100))
    state = db.Column(db.String(50))
    open_time = db.Column(db.String(10), default='18:00')
    close_time = db.Column(db.String(10), default='23:30')
    is_open = db.Column(db.Boolean, default=True, nullable=False)
    is_active = db.Column(db.Boolean, default=True, nullable=False)

    categories = db.relationship('Category', backref='store', lazy=True, cascade='all, delete-orphan')
    products = db.relationship('Product', backref='store', lazy=True, cascade='all, delete-orphan')
    orders = db.relationship('Order', backref='store', lazy=True, cascade='all, delete-orphan')


class Category(TimestampMixin, db.Model):
    __tablename__ = 'categories'

    id = db.Column(db.Integer, primary_key=True)
    store_id = db.Column(db.Integer, db.ForeignKey('stores.id'), nullable=False)
    name = db.Column(db.String(120), nullable=False)
    sort_order = db.Column(db.Integer, default=0)
    is_active = db.Column(db.Boolean, default=True, nullable=False)

    products = db.relationship('Product', backref='category', lazy=True)


class Product(TimestampMixin, db.Model):
    __tablename__ = 'products'

    id = db.Column(db.Integer, primary_key=True)
    store_id = db.Column(db.Integer, db.ForeignKey('stores.id'), nullable=False)
    category_id = db.Column(db.Integer, db.ForeignKey('categories.id'), nullable=False)
    name = db.Column(db.String(140), nullable=False)
    description = db.Column(db.Text)
    image_url = db.Column(db.String(500))
    price = db.Column(db.Float, nullable=False, default=0)
    compare_at_price = db.Column(db.Float)
    is_featured = db.Column(db.Boolean, default=False, nullable=False)
    is_active = db.Column(db.Boolean, default=True, nullable=False)


class Order(TimestampMixin, db.Model):
    __tablename__ = 'orders'

    id = db.Column(db.Integer, primary_key=True)
    store_id = db.Column(db.Integer, db.ForeignKey('stores.id'), nullable=False)
    customer_name = db.Column(db.String(120), nullable=False)
    customer_phone = db.Column(db.String(30), nullable=False)
    customer_address = db.Column(db.String(255))
    customer_notes = db.Column(db.Text)
    fulfillment_type = db.Column(db.String(20), default='delivery', nullable=False)
    payment_method = db.Column(db.String(30), default='pix', nullable=False)
    status = db.Column(db.String(30), default='new', nullable=False)
    subtotal = db.Column(db.Float, default=0, nullable=False)
    delivery_fee = db.Column(db.Float, default=0, nullable=False)
    total = db.Column(db.Float, default=0, nullable=False)

    items = db.relationship('OrderItem', backref='order', lazy=True, cascade='all, delete-orphan')


class OrderItem(db.Model):
    __tablename__ = 'order_items'

    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey('orders.id'), nullable=False)
    product_name = db.Column(db.String(140), nullable=False)
    quantity = db.Column(db.Integer, nullable=False, default=1)
    unit_price = db.Column(db.Float, nullable=False, default=0)
    total_price = db.Column(db.Float, nullable=False, default=0)
