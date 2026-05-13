import os
import io
import csv
import json
import base64
import urllib.parse
from datetime import datetime
from functools import wraps
from flask import Flask, render_template_string, request, jsonify, redirect, url_for, session, Response
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import inspect, text
from werkzeug.security import generate_password_hash, check_password_hash
import requests as http_requests

# ============================
# GROQ API KEY - ضع مفتاحك هنا
# ============================


# --- App Configuration ---
app = Flask(__name__)
app.secret_key = "enjazk_academic_pro_v19_secure_2024"

basedir = os.path.abspath(os.path.dirname(__file__))
db_path = os.path.join(basedir, 'enjazk_academic.db')

app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + db_path
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['WTF_CSRF_ENABLED'] = False

db = SQLAlchemy(app)

@app.after_request
def after_request(response):
    response.headers.add('Access-Control-Allow-Origin', '*')
    response.headers.add('Access-Control-Allow-Headers', 'Content-Type,Authorization')
    response.headers.add('Access-Control-Allow-Methods', 'GET,POST,OPTIONS')
    return response

ADMIN_USERNAME = "admin"
ADMIN_PASSWORD_HASH = generate_password_hash("admin123")

class Product(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200))
    price = db.Column(db.Float)
    old_price = db.Column(db.Float)
    image_data = db.Column(db.Text)
    description = db.Column(db.Text)
    category = db.Column(db.String(100), default="ابحاث")
    is_active = db.Column(db.Boolean, default=True)

class Order(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    customer_name = db.Column(db.String(200))
    customer_phone = db.Column(db.String(20))
    customer_notes = db.Column(db.Text)
    product_name = db.Column(db.String(200))
    product_price = db.Column(db.Float)
    cart_items = db.Column(db.Text)
    cart_total = db.Column(db.Float, default=0)
    status = db.Column(db.String(50), default="جديد")
    order_date = db.Column(db.DateTime, default=datetime.utcnow)
    admin_notes = db.Column(db.Text, default="")

class StoreSettings(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    footer_text = db.Column(db.String(500), default="انجازك للخدمات الطلابية")
    whatsapp = db.Column(db.String(500), default="https://wa.me/966500000000")
    whatsapp_number = db.Column(db.String(20), default="966500000000")
    instagram = db.Column(db.String(500), default="#")
    tiktok = db.Column(db.String(500), default="#")
    phone = db.Column(db.String(20), default="0500000000")
    email = db.Column(db.String(100), default="academic@enjazk.com")
    chat_welcome_msg = db.Column(db.String(500), default="مرحبا بك!")
    moving_text = db.Column(db.String(1000), default="جودة اكاديمية استثنائية | كتابة واصياغة احترافية | سرعة في الانجاز")
    notify_whatsapp = db.Column(db.Boolean, default=False)

def maintenance_db():
    with app.app_context():
        db.create_all()
        inspector = inspect(db.engine)
        updates = {
            'store_settings': {
                'moving_text': 'TEXT', 'whatsapp': 'TEXT', 'instagram': 'TEXT',
                'tiktok': 'TEXT', 'phone': 'TEXT', 'email': 'TEXT',
                'footer_text': 'TEXT', 'chat_welcome_msg': 'TEXT',
                'whatsapp_number': 'TEXT', 'notify_whatsapp': 'BOOLEAN'
            },
            'product': {
                'old_price': 'FLOAT', 'category': 'VARCHAR(100)',
                'description': 'TEXT', 'is_active': 'BOOLEAN'
            },
            'order': {
                'cart_items': 'TEXT', 'cart_total': 'FLOAT', 'admin_notes': 'TEXT'
            }
        }
        for table, cols in updates.items():
            try:
                existing = [c['name'] for c in inspector.get_columns(table)]
                for c_name, c_type in cols.items():
                    if c_name not in existing:
                        try:
                            db.session.execute(text("ALTER TABLE {} ADD COLUMN {} {}".format(table, c_name, c_type)))
                            db.session.commit()
                        except:
                            db.session.rollback()
            except:
                pass
        if not StoreSettings.query.first():
            db.session.add(StoreSettings())
            db.session.commit()

maintenance_db()

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('admin_logged_in'):
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated

@app.route('/')
def index():
    products = Product.query.filter_by(is_active=True).all()
    settings = StoreSettings.query.first()
    categories = list(set(p.category for p in products if p.category))
    return render_template_string(STORE_HTML, products=products, settings=settings, categories=categories)

@app.route('/api/order', methods=['POST', 'OPTIONS'])
def place_order():
    if request.method == 'OPTIONS':
        return jsonify({"status": "ok"}), 200
    try:
        if request.is_json:
            data = request.get_json(force=True, silent=True) or {}
        else:
            data = request.form.to_dict()

        if not data.get('name') or not data.get('phone'):
            return jsonify({"status": "error", "message": "الاسم ورقم الجوال مطلوبان"}), 400

        if not str(data.get('notes', '')).strip():
            return jsonify({"status": "error", "message": "يرجى كتابة ملاحظات الطلب - هذا الحقل مطلوب"}), 400

        cart = data.get('cart', [])
        if isinstance(cart, str):
            try:
                cart = json.loads(cart)
            except:
                cart = []

        cart_total = sum(float(item.get('price', 0)) * int(item.get('qty', 1)) for item in cart)
        cart_json = json.dumps(cart, ensure_ascii=False)
        first_name = cart[0]['name'] if cart else data.get('product_name', '')
        first_price = float(cart[0]['price']) if cart else 0.0

        new_o = Order(
            customer_name=data.get('name'),
            customer_phone=data.get('phone'),
            product_name=first_name,
            product_price=first_price,
            cart_items=cart_json,
            cart_total=cart_total,
            customer_notes=data.get('notes', ''),
            status="جديد"
        )
        db.session.add(new_o)
        db.session.commit()

        settings = StoreSettings.query.first()
        wa_link = None
        customer_wa_link = None

        if settings and settings.whatsapp_number:
            items_txt = "\n".join([
                "- {} x{} = {} ر.س".format(i['name'], i.get('qty', 1), float(i['price']) * int(i.get('qty', 1)))
                for i in cart
            ])
            msg = "طلب جديد #{}\n الاسم: {}\n الجوال: {}\n\n المنتجات:\n{}\n\n الاجمالي: {} ر.س\n الملاحظات: {}".format(
                new_o.id, data.get('name'), data.get('phone'),
                items_txt, cart_total, data.get('notes', 'لا يوجد')
            )
            wa_link = "https://wa.me/{}?text={}".format(settings.whatsapp_number, urllib.parse.quote(msg))

        # رسالة تاكيد للعميل
        customer_phone_clean = ''.join(filter(str.isdigit, data.get('phone', '')))
        if customer_phone_clean.startswith('0'):
            customer_phone_clean = '966' + customer_phone_clean[1:]
        elif not customer_phone_clean.startswith('966'):
            customer_phone_clean = '966' + customer_phone_clean
        if customer_phone_clean:
            items_txt_c = "\n".join(["• {} x{}".format(i['name'], i.get('qty', 1)) for i in cart])
            confirm_msg = "تم استلام طلبك بنجاح!\n\nمرحبا {}\nرقم طلبك: #{}\n\nالخدمات:\n{}\n\nالاجمالي: {} ر.س\n\nسيتم التواصل معك قريبا لتاكيد الطلب.\nشكرا لثقتك بانجازك".format(
                data.get('name'), new_o.id, items_txt_c, cart_total
            )
            customer_wa_link = "https://wa.me/{}?text={}".format(customer_phone_clean, urllib.parse.quote(confirm_msg))

        return jsonify({"status": "success", "wa_notify_link": wa_link, "customer_wa_link": customer_wa_link, "order_id": new_o.id})

    except Exception as e:
        db.session.rollback()
        return jsonify({"status": "error", "message": "خطا في الخادم: " + str(e)}), 500

@app.route('/login', methods=['GET', 'POST'])
def login():
    error = None
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        if username == ADMIN_USERNAME and check_password_hash(ADMIN_PASSWORD_HASH, password):
            session['admin_logged_in'] = True
            session.permanent = False
            return redirect(url_for('admin'))
        else:
            error = "اسم المستخدم او كلمة المرور غير صحيحة"
    return render_template_string(LOGIN_HTML, error=error)

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/cp', methods=['GET', 'POST'])
@login_required
def admin():
    if request.method == 'POST' and 'name' in request.form:
        file = request.files.get('product_file')
        img_b64 = ""
        if file and file.filename:
            img_b64 = "data:image/png;base64," + base64.b64encode(file.read()).decode('utf-8')
        new_p = Product(
            name=request.form.get('name'),
            price=float(request.form.get('price', 0) or 0),
            old_price=float(request.form.get('old_price')) if request.form.get('old_price') else None,
            description=request.form.get('description', ''),
            category=request.form.get('category', 'عام'),
            image_data=img_b64,
            is_active=True
        )
        db.session.add(new_p)
        db.session.commit()
        return redirect(url_for('admin') + '#services')

    search_q = request.args.get('q', '')
    new_orders = Order.query.filter_by(status="جديد").order_by(Order.order_date.desc()).all()
    processing_orders = Order.query.filter_by(status="تحت الإجراء").order_by(Order.order_date.desc()).all()
    completed_orders = Order.query.filter_by(status="مكتمل").order_by(Order.order_date.desc()).all()

    if search_q:
        completed_orders = [o for o in completed_orders if search_q in (o.customer_name or '') or search_q in (o.product_name or '')]

    products = Product.query.order_by(Product.id.desc()).all()
    settings = StoreSettings.query.first()
    total_sales = sum((o.cart_total or o.product_price or 0) for o in Order.query.filter_by(status="مكتمل").all())

    def parse_cart(o):
        if o.cart_items:
            try:
                return json.loads(o.cart_items)
            except:
                return []
        return []

    for o in new_orders + processing_orders + completed_orders:
        o.parsed_cart = parse_cart(o)

    return render_template_string(
        ADMIN_HTML,
        products=products,
        new_orders=new_orders,
        processing_orders=processing_orders,
        completed_orders=completed_orders,
        settings=settings,
        total_sales=total_sales,
        total_new=len(new_orders),
        total_processing=len(processing_orders),
        search_q=search_q
    )

@app.route('/admin/set_order_status/<int:oid>/<path:status>')
@login_required
def set_order_status(oid, status):
    o = Order.query.get(oid)
    allowed = ["جديد", "تحت الإجراء", "مكتمل"]
    if o and status in allowed:
        o.status = status
        db.session.commit()
        if status == "مكتمل":
            phone_clean = "".join(filter(str.isdigit, o.customer_phone or ""))
            if phone_clean.startswith("0"):
                phone_clean = "966" + phone_clean[1:]
            elif not phone_clean.startswith("966"):
                phone_clean = "966" + phone_clean
            if phone_clean:
                review_msg = "مرحبا " + (o.customer_name or "") + "\n\nنشكرك على ثقتك بانجازك\nتم اكتمال طلبك رقم #" + str(o.id) + " بنجاح\n\nنسعد بتقييمك لتجربتك معنا:\n5 - ممتاز\n4 - جيد جدا\n3 - جيد\n2 - مقبول\n1 - يحتاج تحسين\n\nشكرا لك ونتطلع لخدمتك مجددا"
                wa_review = "https://wa.me/" + phone_clean + "?text=" + urllib.parse.quote(review_msg)
                return redirect(wa_review)
    return redirect(url_for('admin'))


@app.route('/admin/complete_order/<int:oid>')
@login_required
def complete_order(oid):
    o = Order.query.get(oid)
    if o:
        o.status = "مكتمل"
        db.session.commit()
    return redirect(url_for('admin'))

@app.route('/admin/delete_order/<int:oid>')
@login_required
def delete_order(oid):
    o = Order.query.get(oid)
    if o:
        db.session.delete(o)
        db.session.commit()
    return redirect(url_for('admin'))

@app.route('/admin/delete_product/<int:pid>')
@login_required
def delete_product(pid):
    p = Product.query.get(pid)
    if p:
        db.session.delete(p)
        db.session.commit()
    return redirect(url_for('admin') + '#services')

@app.route('/admin/toggle_product/<int:pid>')
@login_required
def toggle_product(pid):
    p = Product.query.get(pid)
    if p:
        p.is_active = not p.is_active
        db.session.commit()
    return redirect(url_for('admin') + '#services')

@app.route('/admin/edit_product/<int:pid>', methods=['POST'])
@login_required
def edit_product(pid):
    p = Product.query.get(pid)
    if p:
        p.name = request.form.get('name', p.name)
        p.price = float(request.form.get('price', p.price) or p.price)
        p.old_price = float(request.form.get('old_price')) if request.form.get('old_price') else None
        p.description = request.form.get('description', p.description)
        p.category = request.form.get('category', p.category)
        file = request.files.get('product_file')
        if file and file.filename:
            p.image_data = "data:image/png;base64," + base64.b64encode(file.read()).decode('utf-8')
        db.session.commit()
    return redirect(url_for('admin') + '#services')

@app.route('/admin/update_settings', methods=['POST'])
@login_required
def update_settings():
    s = StoreSettings.query.first()
    if s:
        s.whatsapp = request.form.get('whatsapp', s.whatsapp)
        s.whatsapp_number = request.form.get('whatsapp_number', s.whatsapp_number)
        s.instagram = request.form.get('instagram', s.instagram)
        s.tiktok = request.form.get('tiktok', s.tiktok)
        s.phone = request.form.get('phone', s.phone)
        s.email = request.form.get('email', s.email)
        s.moving_text = request.form.get('moving_text', s.moving_text)
        s.footer_text = request.form.get('footer_text', s.footer_text)
        db.session.commit()
    return redirect(url_for('admin') + '#settings')

@app.route('/admin/export_orders')
@login_required
def export_orders():
    orders = Order.query.order_by(Order.order_date.desc()).all()
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['رقم الطلب', 'الاسم', 'الجوال', 'الخدمة', 'السلة', 'الاجمالي', 'الحالة', 'التاريخ', 'ملاحظات'])
    for o in orders:
        writer.writerow([
            o.id, o.customer_name, o.customer_phone,
            o.product_name, o.cart_items or '', o.cart_total or o.product_price or 0,
            o.status, o.order_date.strftime('%Y-%m-%d %H:%M'), o.customer_notes or ''
        ])
    output.seek(0)
    return Response(
        "\ufeff" + output.getvalue(),
        mimetype='text/csv; charset=utf-8-sig',
        headers={"Content-Disposition": "attachment;filename=orders_enjazk.csv"}
    )

# ============================
# CLAUDE AI ROUTES
# ============================

@app.route('/api/chat', methods=['POST'])
def chat():
    """شات مساعد للعملاء"""
    try:
        data = request.get_json(force=True, silent=True) or {}
        user_msg = data.get('message', '').strip()
        if not user_msg:
            return jsonify({"status": "error", "message": "الرسالة فارغة"}), 400

        products = Product.query.filter_by(is_active=True).all()
        products_list = "\n".join([
            "- {} | السعر: {} ر.س | التصنيف: {} | الوصف: {}".format(
                p.name, p.price, p.category, (p.description or '')[:100]
            ) for p in products
        ])

        settings = StoreSettings.query.first()
        system_prompt = """انت مساعد ذكي لمتجر انجازك للخدمات الاكاديمية.
مهمتك مساعدة العملاء في معرفة الخدمات والاسعار والاجابة على استفساراتهم.
كن ودوداً ومختصراً. رد دائماً بالعربية.
لا تتحدث عن مواضيع خارج نطاق الخدمات الاكاديمية.

الخدمات المتاحة:
{}

معلومات التواصل:
- واتساب: {}
- هاتف: {}""".format(products_list, settings.whatsapp if settings else '', settings.phone if settings else '')

        import urllib.request as ureq
        payload = json.dumps({
            'model': 'llama-3.1-8b-instant',
            'max_tokens': 500,
            'messages': [
                {'role': 'system', 'content': system_prompt},
                {'role': 'user', 'content': user_msg}
            ]
        }, ensure_ascii=False).encode('utf-8')
        req = ureq.Request(
            'https://api.groq.com/openai/v1/chat/completions',
            data=payload,
            headers={
                'Authorization': 'Bearer ' + GROQ_API_KEY,
                'Content-Type': 'application/json'
            }
        )
        with ureq.urlopen(req, timeout=15) as resp:
            result = json.loads(resp.read().decode('utf-8'))
        reply = result['choices'][0]['message']['content']
        return jsonify({"status": "success", "reply": reply})

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route('/api/ai/analyze_order', methods=['POST'])
@login_required
def analyze_order():
    """تحليل الطلب واقتراح رد للمشرف"""
    try:
        data = request.get_json(force=True, silent=True) or {}
        order_id = data.get('order_id')
        o = Order.query.get(order_id)
        if not o:
            return jsonify({"status": "error", "message": "الطلب غير موجود"}), 404

        prompt = """حلل هذا الطلب الاكاديمي واقترح:
1. رد مناسب للعميل
2. الوقت المتوقع للانجاز
3. اي ملاحظات مهمة

تفاصيل الطلب:
- الاسم: {}
- الخدمة: {}
- الملاحظات: {}
- الاجمالي: {} ر.س

اجب بشكل مختصر ومنظم بالعربية.""".format(
            o.customer_name, o.product_name,
            o.customer_notes or 'لا يوجد', o.cart_total or 0
        )

        import urllib.request as ureq
        payload2 = json.dumps({
            'model': 'llama-3.1-8b-instant',
            'max_tokens': 600,
            'messages': [{'role': 'user', 'content': prompt}]
        }, ensure_ascii=False).encode('utf-8')
        req2 = ureq.Request(
            'https://api.groq.com/openai/v1/chat/completions',
            data=payload2,
            headers={
                'Authorization': 'Bearer ' + GROQ_API_KEY,
                'Content-Type': 'application/json'
            }
        )
        with ureq.urlopen(req2, timeout=15) as resp2:
            result2 = json.loads(resp2.read().decode('utf-8'))
        analysis = result2['choices'][0]['message']['content']
        return jsonify({"status": "success", "analysis": analysis})

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route('/api/ai/suggest_price', methods=['POST'])
@login_required
def suggest_price():
    """اقتراح سعر للخدمة"""
    try:
        data = request.get_json(force=True, silent=True) or {}
        name = data.get('name', '')
        description = data.get('description', '')
        category = data.get('category', '')

        products = Product.query.all()
        existing = "\n".join([
            "- {} | {} ر.س | {}".format(p.name, p.price, p.category)
            for p in products
        ])

        prompt = """بناء على هذه الخدمات الموجودة في المتجر:
{}

اقترح سعراً مناسباً بالريال السعودي لهذه الخدمة الجديدة:
- الاسم: {}
- التصنيف: {}
- الوصف: {}

اجب برقم السعر المقترح فقط مع تبرير قصير جداً بالعربية.""".format(
            existing, name, category, description
        )

        import urllib.request as ureq
        payload3 = json.dumps({
            'model': 'llama-3.1-8b-instant',
            'max_tokens': 200,
            'messages': [{'role': 'user', 'content': prompt}]
        }, ensure_ascii=False).encode('utf-8')
        req3 = ureq.Request(
            'https://api.groq.com/openai/v1/chat/completions',
            data=payload3,
            headers={
                'Authorization': 'Bearer ' + GROQ_API_KEY,
                'Content-Type': 'application/json'
            }
        )
        with ureq.urlopen(req3, timeout=15) as resp3:
            result3 = json.loads(resp3.read().decode('utf-8'))
        suggestion = result3['choices'][0]['message']['content']
        return jsonify({"status": "success", "suggestion": suggestion})

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

# ===================== LOGIN HTML =====================
LOGIN_HTML = """<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>تسجيل الدخول | انجازك</title>
<script src="https://cdn.tailwindcss.com"></script>
<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans+Arabic:wght@400;600;700&display=swap" rel="stylesheet">
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
<style>body{font-family:'IBM Plex Sans Arabic',sans-serif;}</style>
</head>
<body class="min-h-screen bg-gradient-to-br from-slate-900 to-slate-800 flex items-center justify-center p-4">
<div class="w-full max-w-md">
  <div class="text-center mb-10">
    <div class="w-20 h-20 bg-amber-600 rounded-3xl flex items-center justify-center text-white mx-auto mb-4 shadow-2xl">
      <i class="fas fa-graduation-cap text-3xl"></i>
    </div>
    <h1 class="text-3xl font-black text-white">انجازك</h1>
    <p class="text-slate-400 text-sm mt-1">لوحة ادارة المتجر</p>
  </div>
  <div class="bg-white/5 backdrop-blur border border-white/10 rounded-3xl p-8 shadow-2xl">
    {% if error %}
    <div class="bg-red-500/10 border border-red-500/30 text-red-400 rounded-2xl p-4 mb-6 text-sm flex items-center gap-3">
      <i class="fas fa-exclamation-circle"></i> {{ error }}
    </div>
    {% endif %}
    <form method="POST" class="space-y-5">
      <div>
        <label class="block text-xs font-bold text-slate-400 mb-2">اسم المستخدم</label>
        <div class="relative">
          <i class="fas fa-user absolute right-4 top-1/2 -translate-y-1/2 text-slate-500"></i>
          <input name="username" type="text" autocomplete="username" placeholder="admin" required
            class="w-full bg-white/5 border border-white/10 text-white rounded-2xl py-4 pr-12 pl-4 text-sm outline-none focus:border-amber-500 transition-all">
        </div>
      </div>
      <div>
        <label class="block text-xs font-bold text-slate-400 mb-2">كلمة المرور</label>
        <div class="relative">
          <i class="fas fa-lock absolute right-4 top-1/2 -translate-y-1/2 text-slate-500"></i>
          <input name="password" id="pf" type="password" autocomplete="current-password" placeholder="admin123" required
            class="w-full bg-white/5 border border-white/10 text-white rounded-2xl py-4 pr-12 pl-12 text-sm outline-none focus:border-amber-500 transition-all">
          <button type="button" onclick="var f=document.getElementById('pf');f.type=f.type=='password'?'text':'password';" class="absolute left-4 top-1/2 -translate-y-1/2 text-slate-500 hover:text-white">
            <i class="fas fa-eye"></i>
          </button>
        </div>
      </div>
      <button type="submit" class="w-full bg-amber-600 hover:bg-amber-500 text-white font-black py-4 rounded-2xl transition-all flex items-center justify-center gap-2">
        <i class="fas fa-sign-in-alt"></i> دخول للوحة الادارة
      </button>
    </form>
  </div>
  <p class="text-center text-slate-600 text-xs mt-6">كلمة المرور الافتراضية: admin123</p>
</div>
</body></html>"""

# ===================== STORE HTML =====================
STORE_HTML = """<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0,maximum-scale=1.0,user-scalable=no">
<title>متجر انجازك الاكاديمي</title>
<script src="https://cdn.tailwindcss.com"></script>
<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans+Arabic:wght@300;400;500;600;700&display=swap" rel="stylesheet">
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
<style>
:root{--primary:#0f172a;--accent:#b45309;}
body{font-family:'IBM Plex Sans Arabic',sans-serif;background:#f8fafc;color:var(--primary);}
.hero-gradient{background:linear-gradient(135deg,#0f172a 0%,#1e293b 100%);}
.moving-banner{background:#b45309;color:#fff;padding:6px 0;overflow:hidden;}
.marquee{display:inline-block;white-space:nowrap;animation:marquee 30s linear infinite;font-size:.8rem;font-weight:500;}
@keyframes marquee{0%{transform:translateX(100%)}100%{transform:translateX(-100%)}}
.glass-card{background:rgba(255,255,255,.95);border:1px solid rgba(255,255,255,.4);box-shadow:0 10px 30px -10px rgba(0,0,0,.06);transition:all .3s ease;}
.glass-card:hover{transform:translateY(-4px);box-shadow:0 20px 40px -15px rgba(180,83,9,.15);}
.btn-primary{background:var(--primary);color:white;transition:all .25s;}
.btn-primary:hover{background:#1e293b;}
.cat-btn{transition:all .2s;border:2px solid #e2e8f0;}
.cat-btn.active,.cat-btn:hover{border-color:var(--accent);background:rgba(180,83,9,.08);color:var(--accent);}
#toast{position:fixed;bottom:24px;left:50%;transform:translateX(-50%) translateY(80px);transition:transform .4s cubic-bezier(.34,1.56,.64,1);opacity:0;z-index:9999;min-width:280px;}
#toast.show{transform:translateX(-50%) translateY(0);opacity:1;}
#cartSidebar{transition:transform .35s cubic-bezier(.4,0,.2,1);}
#cartSidebar.open{transform:translateX(0) !important;}
.qty-btn{width:30px;height:30px;border-radius:8px;display:flex;align-items:center;justify-content:center;font-weight:700;cursor:pointer;transition:all .15s;}
.qty-btn:hover{background:#e2e8f0;}
.required-field{border-color:#f59e0b !important;background:#fffbeb !important;}
.notes-required{border:2px solid #fcd34d;background:#fffbeb;}
</style>
</head>
<body class="flex flex-col min-h-screen">

<div class="moving-banner"><div class="marquee">{{ settings.moving_text }}</div></div>

<header class="sticky top-0 z-50 bg-white/90 backdrop-blur-md border-b border-slate-100 shadow-sm">
  <div class="max-w-6xl mx-auto px-4 h-16 flex items-center justify-between">
    <div class="flex items-center gap-3">
      <div class="w-10 h-10 bg-slate-900 rounded-xl flex items-center justify-center text-amber-500">
        <i class="fas fa-graduation-cap text-lg"></i>
      </div>
      <div>
        <h1 class="text-xl font-bold leading-tight">انجازك</h1>
        <span class="text-[9px] text-amber-700 font-bold uppercase tracking-widest">للخدمات الاكاديمية</span>
      </div>
    </div>
    <div class="flex items-center gap-3">
      <button onclick="openCart()" class="relative flex items-center gap-2 bg-slate-900 text-white px-4 py-2 rounded-full text-sm font-bold hover:bg-slate-700 transition-all">
        <i class="fas fa-shopping-cart"></i>
        <span class="hidden sm:inline">السلة</span>
        <span id="cartBadge" style="display:none" class="absolute -top-1 -left-1 w-5 h-5 bg-amber-500 text-white rounded-full text-[10px] font-black flex items-center justify-center">0</span>
      </button>
      <a href="{{ settings.whatsapp }}" target="_blank" class="flex items-center gap-2 bg-green-500 text-white px-4 py-2 rounded-full text-sm font-bold hover:bg-green-600 transition-all">
        <i class="fab fa-whatsapp text-lg"></i>
        <span class="hidden sm:inline">تواصل معنا</span>
      </a>
    </div>
  </div>
</header>

<section class="hero-gradient text-white py-14 sm:py-20 px-4 text-center">
  <div class="max-w-3xl mx-auto">
    <h2 class="text-3xl sm:text-5xl font-black mb-4 leading-tight">شريكك الموثوق للتميز في بحوثك ودراستك</h2>
    <p class="text-slate-300 text-sm sm:text-lg mb-8">نقدم لك نخبة من الخدمات التعليمية باعلى معايير الجودة</p>
    <div class="flex flex-wrap justify-center gap-3">
      <div class="flex items-center gap-2 text-xs bg-white/10 px-4 py-2 rounded-full border border-white/10"><i class="fas fa-check-circle text-amber-400"></i> خبير متخصص لكل مجال</div>
      <div class="flex items-center gap-2 text-xs bg-white/10 px-4 py-2 rounded-full border border-white/10"><i class="fas fa-clock text-amber-400"></i> التزام بالمواعيد</div>
      <div class="flex items-center gap-2 text-xs bg-white/10 px-4 py-2 rounded-full border border-white/10"><i class="fas fa-shield-alt text-amber-400"></i> سرية تامة</div>
    </div>
  </div>
</section>

<main class="max-w-6xl mx-auto px-4 py-12 flex-grow">
  <div class="mb-8 flex flex-col sm:flex-row gap-4 items-center justify-between">
    <h3 class="text-2xl font-bold border-r-4 border-amber-600 pr-3">خدماتنا المتميزة</h3>
    <div class="relative w-full sm:w-72">
      <i class="fas fa-search absolute right-4 top-1/2 -translate-y-1/2 text-slate-400 text-sm"></i>
      <input id="searchInput" oninput="filterProducts()" placeholder="ابحث عن خدمة..."
        class="w-full bg-white border border-slate-200 rounded-2xl py-3 pr-11 pl-4 text-sm outline-none focus:border-amber-500 shadow-sm transition-all">
    </div>
  </div>

  {% if categories %}
  <div class="flex flex-wrap gap-2 mb-8">
    <button onclick="filterByCategory('all')" class="cat-btn active px-4 py-2 rounded-full text-xs font-bold bg-white" id="cat-all">الكل</button>
    {% for cat in categories %}
    <button onclick="filterByCategory('{{ cat }}')" class="cat-btn px-4 py-2 rounded-full text-xs font-bold bg-white">{{ cat }}</button>
    {% endfor %}
  </div>
  {% endif %}

  <div id="productsGrid" class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-6">
    {% for p in products %}
    <div class="glass-card rounded-3xl overflow-hidden flex flex-col group product-card"
      data-name="{{ p.name|lower }}" data-desc="{{ (p.description or '')|lower }}" data-category="{{ p.category }}">
      <div class="relative aspect-[4/3] overflow-hidden">
        <img src="{{ p.image_data if p.image_data else 'https://placehold.co/600x450/0f172a/white?text=Enjazk' }}"
          class="w-full h-full object-cover transition-transform duration-500 group-hover:scale-110" loading="lazy"
          onerror="this.src='https://placehold.co/600x450/0f172a/white?text=Enjazk'">
        {% if p.old_price %}
        <div class="absolute top-3 left-3 bg-red-500 text-white text-[10px] font-black px-2 py-1 rounded-full">
          خصم {{ ((p.old_price - p.price) / p.old_price * 100)|int }}%
        </div>
        {% endif %}
        <div class="absolute top-3 right-3 bg-white/90 backdrop-blur text-amber-700 text-[10px] font-bold px-2 py-1 rounded-full">{{ p.category }}</div>
      </div>
      <div class="p-6 flex flex-col flex-grow">
        <h4 class="text-lg font-bold mb-2 text-slate-800">{{ p.name }}</h4>
        <p class="text-slate-500 text-xs leading-relaxed mb-5 flex-grow">{{ p.description }}</p>
        <div class="flex items-center justify-between gap-3 mt-auto">
          <div>
            {% if p.old_price %}<span class="text-[10px] text-slate-400 line-through block">{{ p.old_price }} ر.س</span>{% endif %}
            <span class="text-2xl font-black text-slate-900">{{ p.price }} <small class="text-xs font-normal">ر.س</small></span>
          </div>
          <div class="flex gap-2">
            <button onclick="addToCart('{{ p.name|e }}', {{ p.price }})"
              class="border-2 border-amber-600 text-amber-700 hover:bg-amber-600 hover:text-white px-3 py-2 rounded-xl text-xs font-bold transition-all">
              <i class="fas fa-cart-plus"></i>
            </button>
            <button onclick="openSingleOrder('{{ p.name|e }}', {{ p.price }})"
              class="btn-primary px-4 py-2 rounded-xl text-xs font-bold shadow-sm">
              اطلب الان
            </button>
          </div>
        </div>
      </div>
    </div>
    {% endfor %}
  </div>

  <div id="emptyState" class="hidden text-center py-20 text-slate-300">
    <i class="fas fa-search text-5xl mb-4 block"></i>
    <p class="text-lg font-bold">لا توجد نتائج مطابقة</p>
  </div>
</main>

<footer class="bg-slate-950 text-white pt-14 pb-8 px-4">
  <div class="max-w-6xl mx-auto grid grid-cols-1 md:grid-cols-3 gap-10 mb-10 border-b border-white/5 pb-10">
    <div class="space-y-4">
      <div class="flex items-center gap-3">
        <div class="w-8 h-8 bg-amber-600 rounded-lg flex items-center justify-center"><i class="fas fa-graduation-cap"></i></div>
        <span class="font-bold">انجازك الاكاديمي</span>
      </div>
      <p class="text-slate-400 text-sm">{{ settings.footer_text }}</p>
    </div>
    <div class="space-y-4">
      <h5 class="text-amber-500 font-bold text-xs uppercase tracking-widest">قنوات التواصل</h5>
      <ul class="space-y-3 text-sm text-slate-300">
        <li><a href="tel:{{ settings.phone }}" class="hover:text-white flex items-center gap-3"><i class="fas fa-phone-alt text-amber-600"></i> {{ settings.phone }}</a></li>
        <li><a href="mailto:{{ settings.email }}" class="hover:text-white flex items-center gap-3"><i class="fas fa-envelope text-amber-600"></i> {{ settings.email }}</a></li>
      </ul>
    </div>
    <div class="space-y-4">
      <h5 class="text-amber-500 font-bold text-xs uppercase tracking-widest">تابعنا</h5>
      <div class="flex gap-3">
        <a href="{{ settings.instagram }}" class="w-10 h-10 bg-white/5 rounded-xl flex items-center justify-center hover:bg-amber-600 transition-all border border-white/10"><i class="fab fa-instagram"></i></a>
        <a href="{{ settings.tiktok }}" class="w-10 h-10 bg-white/5 rounded-xl flex items-center justify-center hover:bg-amber-600 transition-all border border-white/10"><i class="fab fa-tiktok"></i></a>
        <a href="{{ settings.whatsapp }}" class="w-10 h-10 bg-white/5 rounded-xl flex items-center justify-center hover:bg-amber-600 transition-all border border-white/10"><i class="fab fa-whatsapp"></i></a>
      </div>
    </div>
  </div>
  <div class="text-center text-slate-600 text-[10px]">&copy; 2025 انجازك للخدمات الاكاديمية. جميع الحقوق محفوظة.</div>
</footer>

<!-- CART SIDEBAR -->
<div id="cartOverlay" onclick="closeCart()" style="display:none" class="fixed inset-0 bg-slate-900/50 backdrop-blur-sm z-[90]"></div>
<div id="cartSidebar" class="fixed top-0 left-0 h-full w-full max-w-sm bg-white z-[100] shadow-2xl flex flex-col" style="transform:translateX(-100%)">
  <div class="flex items-center justify-between p-6 border-b border-slate-100">
    <h2 class="text-xl font-black flex items-center gap-2"><i class="fas fa-shopping-cart text-amber-600"></i> سلة الطلبات</h2>
    <button onclick="closeCart()" class="w-10 h-10 rounded-full bg-slate-100 flex items-center justify-center text-slate-500 hover:bg-slate-200 transition-all"><i class="fas fa-times"></i></button>
  </div>
  <div id="cartItemsContainer" class="flex-grow overflow-y-auto p-6 space-y-4">
    <div id="emptyCartMsg" class="text-center py-16 text-slate-300">
      <i class="fas fa-shopping-bag text-5xl mb-4 block"></i>
      <p class="text-sm font-bold">السلة فارغة</p>
      <p class="text-xs mt-1">اضف خدمات لتبدا طلبك</p>
    </div>
  </div>
  <div class="border-t border-slate-100 p-6 space-y-4">
    <div class="flex justify-between text-lg font-black">
      <span>الاجمالي:</span>
      <span id="cartTotal" class="text-amber-600">0 ر.س</span>
    </div>
    <button onclick="openCheckout()" id="checkoutBtn" disabled
      class="w-full bg-slate-900 text-white py-4 rounded-2xl font-black text-sm disabled:opacity-40 disabled:cursor-not-allowed hover:bg-slate-700 transition-all flex items-center justify-center gap-2">
      <i class="fas fa-lock text-xs"></i> اتمام الطلب
    </button>
  </div>
</div>

<!-- CHECKOUT MODAL -->
<div id="checkoutModal" style="display:none" class="fixed inset-0 bg-slate-900/60 backdrop-blur-md flex items-center justify-center p-4 z-[110]">
  <div class="bg-white rounded-[2rem] w-full max-w-lg p-8 shadow-2xl relative max-h-[92vh] overflow-y-auto">
    <button onclick="closeCheckout()" class="absolute top-5 left-5 w-9 h-9 rounded-full bg-slate-100 flex items-center justify-center text-slate-500 hover:bg-slate-200">
      <i class="fas fa-times"></i>
    </button>
    <div class="mb-6">
      <p class="text-amber-600 text-xs font-bold uppercase tracking-widest mb-1">ملخص الطلب</p>
      <h3 class="text-2xl font-black text-slate-900 mb-4">اتمام الطلب</h3>
      <div id="checkoutSummary" class="bg-slate-50 rounded-2xl p-4 space-y-2 text-sm text-slate-600 mb-3"></div>
      <div class="flex justify-between font-black text-base border-t border-slate-200 pt-3">
        <span>الاجمالي</span><span id="checkoutTotal" class="text-amber-600"></span>
      </div>
    </div>
    <div class="space-y-4">
      <div class="relative">
        <i class="fas fa-user absolute right-4 top-4 text-slate-300"></i>
        <input id="coName" placeholder="اسمك الكريم *" class="w-full pr-12 pl-4 py-4 bg-slate-50 rounded-2xl border-2 border-slate-200 focus:border-amber-500 focus:bg-white outline-none transition-all text-sm">
      </div>
      <div class="relative">
        <i class="fas fa-phone absolute right-4 top-4 text-slate-300"></i>
        <input id="coPhone" type="tel" placeholder="رقم الجوال *" class="w-full pr-12 pl-4 py-4 bg-slate-50 rounded-2xl border-2 border-slate-200 focus:border-amber-500 focus:bg-white outline-none transition-all text-sm">
      </div>
      <div>
        <textarea id="coNotes" placeholder="ملاحظات الطلب (مطلوب) - اذكر المستوى الدراسي، التخصص، الموعد النهائي وأي تفاصيل مهمة... *"
          class="notes-required w-full p-4 rounded-2xl focus:border-amber-500 focus:bg-white outline-none transition-all text-sm h-28 resize-none"></textarea>
        <p class="text-[11px] text-amber-600 font-bold mt-1 flex items-center gap-1">
          <i class="fas fa-exclamation-circle"></i> هذا الحقل مطلوب - يساعدنا في خدمتك بشكل افضل
        </p>
      </div>
      <button onclick="submitCartOrder()" id="submitCartBtn"
        class="w-full bg-slate-900 hover:bg-slate-700 text-white py-4 rounded-2xl font-black shadow-xl flex items-center justify-center gap-3 transition-all">
        تاكيد وارسال الطلب <i class="fas fa-paper-plane"></i>
      </button>
    </div>
  </div>
</div>

<!-- SINGLE PRODUCT ORDER MODAL -->
<div id="orderModal" style="display:none" class="fixed inset-0 bg-slate-900/60 backdrop-blur-md flex items-center justify-center p-4 z-[110]">
  <div class="bg-white rounded-[2rem] w-full max-w-lg p-8 shadow-2xl relative">
    <button onclick="closeOrderModal()" class="absolute top-5 left-5 w-9 h-9 rounded-full bg-slate-100 flex items-center justify-center text-slate-500 hover:bg-slate-200">
      <i class="fas fa-times"></i>
    </button>
    <div class="mb-6 text-center">
      <p class="text-amber-600 text-xs font-bold uppercase tracking-widest mb-1">طلب خدمة</p>
      <h3 id="orderModalTitle" class="text-xl font-black text-slate-900"></h3>
    </div>
    <div class="space-y-4">
      <div class="relative">
        <i class="fas fa-user absolute right-4 top-4 text-slate-300"></i>
        <input id="sName" placeholder="اسمك الكريم *" class="w-full pr-12 pl-4 py-4 bg-slate-50 rounded-2xl border-2 border-slate-200 focus:border-amber-500 focus:bg-white outline-none transition-all text-sm">
      </div>
      <div class="relative">
        <i class="fas fa-phone absolute right-4 top-4 text-slate-300"></i>
        <input id="sPhone" type="tel" placeholder="رقم الجوال *" class="w-full pr-12 pl-4 py-4 bg-slate-50 rounded-2xl border-2 border-slate-200 focus:border-amber-500 focus:bg-white outline-none transition-all text-sm">
      </div>
      <div>
        <textarea id="sNotes" placeholder="ملاحظات الطلب (مطلوب) - اذكر المستوى الدراسي، التخصص، الموعد النهائي وأي تفاصيل مهمة... *"
          class="notes-required w-full p-4 rounded-2xl focus:border-amber-500 focus:bg-white outline-none transition-all text-sm h-28 resize-none"></textarea>
        <p class="text-[11px] text-amber-600 font-bold mt-1 flex items-center gap-1">
          <i class="fas fa-exclamation-circle"></i> هذا الحقل مطلوب - يساعدنا في خدمتك بشكل افضل
        </p>
      </div>
      <button onclick="submitSingleOrder()" id="submitSingleBtn"
        class="w-full bg-slate-900 hover:bg-slate-700 text-white py-4 rounded-2xl font-black shadow-xl flex items-center justify-center gap-3 transition-all">
        ارسال الطلب الان <i class="fas fa-paper-plane"></i>
      </button>
    </div>
  </div>
</div>

<!-- TOAST -->
<div id="toast" class="bg-green-500 text-white px-6 py-4 rounded-2xl shadow-2xl flex items-center gap-3 text-sm font-bold">
  <i class="fas fa-check-circle text-lg"></i><span id="toastMsg"></span>
</div>

<script>
var cart = [];
var singleProductName = '';
var singleProductPrice = 0;

// ---- CART ----
function addToCart(name, price) {
  var found = false;
  for (var i = 0; i < cart.length; i++) {
    if (cart[i].name === name) { cart[i].qty++; found = true; break; }
  }
  if (!found) cart.push({name: name, price: price, qty: 1});
  renderCart();
  openCart();
  showToast('تمت اضافة "' + name + '" للسلة', true);
}

function removeFromCart(idx) {
  cart.splice(idx, 1);
  renderCart();
}

function changeQty(idx, d) {
  cart[idx].qty = Math.max(1, cart[idx].qty + d);
  renderCart();
}

function renderCart() {
  var container = document.getElementById('cartItemsContainer');
  var empty = document.getElementById('emptyCartMsg');
  var badge = document.getElementById('cartBadge');
  var btn = document.getElementById('checkoutBtn');
  var total = 0, count = 0;
  for (var i = 0; i < cart.length; i++) { total += cart[i].price * cart[i].qty; count += cart[i].qty; }

  document.getElementById('cartTotal').innerText = total.toFixed(0) + ' ر.س';
  if (count > 0) { badge.style.display = 'flex'; badge.innerText = count; } else { badge.style.display = 'none'; }
  btn.disabled = cart.length === 0;

  var existing = container.querySelectorAll('.cart-item');
  for (var j = 0; j < existing.length; j++) existing[j].remove();

  if (cart.length === 0) { empty.style.display = 'block'; return; }
  empty.style.display = 'none';

  for (var k = 0; k < cart.length; k++) {
    (function(item, idx) {
      var d = document.createElement('div');
      d.className = 'cart-item flex items-center gap-3 bg-slate-50 rounded-2xl p-3';
      d.innerHTML =
        '<div class="flex-grow min-w-0">' +
          '<p class="font-bold text-sm text-slate-800 truncate">' + item.name + '</p>' +
          '<p class="text-amber-600 font-black text-sm">' + (item.price * item.qty).toFixed(0) + ' ر.س</p>' +
        '</div>' +
        '<div class="flex items-center gap-1 bg-white border border-slate-200 rounded-xl px-1">' +
          '<button class="qty-btn text-slate-500 hover:text-slate-900" onclick="changeQty(' + idx + ',-1)">−</button>' +
          '<span class="w-7 text-center font-bold text-sm">' + item.qty + '</span>' +
          '<button class="qty-btn text-slate-500 hover:text-slate-900" onclick="changeQty(' + idx + ',1)">+</button>' +
        '</div>' +
        '<button onclick="removeFromCart(' + idx + ')" class="w-8 h-8 rounded-xl bg-red-50 text-red-400 hover:bg-red-500 hover:text-white transition-all flex items-center justify-center">' +
          '<i class="fas fa-trash text-xs"></i></button>';
      container.appendChild(d);
    })(cart[k], k);
  }
}

function openCart() {
  document.getElementById('cartSidebar').classList.add('open');
  document.getElementById('cartOverlay').style.display = 'block';
  document.body.style.overflow = 'hidden';
}
function closeCart() {
  document.getElementById('cartSidebar').classList.remove('open');
  document.getElementById('cartOverlay').style.display = 'none';
  document.body.style.overflow = '';
}

function openCheckout() {
  closeCart();
  var html = '';
  var total = 0;
  for (var i = 0; i < cart.length; i++) {
    var s = cart[i].price * cart[i].qty; total += s;
    html += '<div class="flex justify-between"><span>' + cart[i].name + ' &times;' + cart[i].qty + '</span><span class="font-bold">' + s.toFixed(0) + ' ر.س</span></div>';
  }
  document.getElementById('checkoutSummary').innerHTML = html;
  document.getElementById('checkoutTotal').innerText = total.toFixed(0) + ' ر.س';
  document.getElementById('checkoutModal').style.display = 'flex';
  document.body.style.overflow = 'hidden';
}
function closeCheckout() {
  document.getElementById('checkoutModal').style.display = 'none';
  document.body.style.overflow = '';
}

async function submitCartOrder() {
  var name = document.getElementById('coName').value.trim();
  var phone = document.getElementById('coPhone').value.trim();
  var notes = document.getElementById('coNotes').value.trim();
  var btn = document.getElementById('submitCartBtn');

  if (!name) { pulse('coName'); showToast('يرجى ادخال اسمك', false); return; }
  if (!phone || !/^[0-9+]{7,15}$/.test(phone)) { pulse('coPhone'); showToast('رقم الجوال غير صحيح', false); return; }
  if (!notes) { pulse('coNotes'); showToast('حقل الملاحظات مطلوب - اذكر تفاصيل طلبك', false); return; }

  btn.disabled = true;
  btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> جاري الارسال...';

  try {
    var r = await fetch('/api/order', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({name: name, phone: phone, notes: notes, cart: cart})
    });
    var d = await r.json();
    if (r.ok && d.status === 'success') {
      showToast('تم استلام طلبك رقم #' + d.order_id + ' سنتواصل معك قريبا', true);
      closeCheckout();
      cart = []; renderCart();
      document.getElementById('coName').value = '';
      document.getElementById('coPhone').value = '';
      document.getElementById('coNotes').value = '';
      if (d.customer_wa_link) {
        setTimeout(function(){ window.open(d.customer_wa_link, '_blank'); }, 1000);
      }
    } else {
      showToast(d.message || 'حدث خطا، يرجى المحاولة', false);
    }
  } catch(e) {
    showToast('تعذر الاتصال: ' + e.message, false);
  }
  btn.disabled = false;
  btn.innerHTML = 'تاكيد وارسال الطلب <i class="fas fa-paper-plane"></i>';
}

// ---- SINGLE ORDER ----
function openSingleOrder(name, price) {
  singleProductName = name;
  singleProductPrice = price;
  document.getElementById('orderModalTitle').innerText = name;
  document.getElementById('orderModal').style.display = 'flex';
  document.body.style.overflow = 'hidden';
}
function closeOrderModal() {
  document.getElementById('orderModal').style.display = 'none';
  document.body.style.overflow = '';
}

async function submitSingleOrder() {
  var name = document.getElementById('sName').value.trim();
  var phone = document.getElementById('sPhone').value.trim();
  var notes = document.getElementById('sNotes').value.trim();
  var btn = document.getElementById('submitSingleBtn');

  if (!name) { pulse('sName'); showToast('يرجى ادخال اسمك', false); return; }
  if (!phone || !/^[0-9+]{7,15}$/.test(phone)) { pulse('sPhone'); showToast('رقم الجوال غير صحيح', false); return; }
  if (!notes) { pulse('sNotes'); showToast('حقل الملاحظات مطلوب - اذكر تفاصيل طلبك', false); return; }

  btn.disabled = true;
  btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> جاري الارسال...';

  try {
    var r = await fetch('/api/order', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({
        name: name, phone: phone, notes: notes,
        product_name: singleProductName,
        cart: [{name: singleProductName, price: singleProductPrice, qty: 1}]
      })
    });
    var d = await r.json();
    if (r.ok && d.status === 'success') {
      showToast('تم استلام طلبك رقم #' + d.order_id + ' سنتواصل معك قريبا', true);
      closeOrderModal();
      document.getElementById('sName').value = '';
      document.getElementById('sPhone').value = '';
      document.getElementById('sNotes').value = '';
      if (d.customer_wa_link) {
        setTimeout(function(){ window.open(d.customer_wa_link, '_blank'); }, 1000);
      }
    } else {
      showToast(d.message || 'حدث خطا، يرجى المحاولة', false);
    }
  } catch(e) {
    showToast('تعذر الاتصال: ' + e.message, false);
  }
  btn.disabled = false;
  btn.innerHTML = 'ارسال الطلب الان <i class="fas fa-paper-plane"></i>';
}

// ---- HELPERS ----
function pulse(id) {
  var el = document.getElementById(id);
  el.classList.add('required-field');
  el.focus();
  setTimeout(function(){ el.classList.remove('required-field'); }, 2500);
}

function showToast(msg, ok) {
  var t = document.getElementById('toast');
  document.getElementById('toastMsg').innerText = msg;
  t.className = (ok !== false ? 'bg-green-500' : 'bg-red-500') + ' text-white px-6 py-4 rounded-2xl shadow-2xl flex items-center gap-3 text-sm font-bold';
  t.classList.add('show');
  setTimeout(function(){ t.classList.remove('show'); }, 4500);
}

var activeCategory = 'all';
function filterProducts() {
  var q = document.getElementById('searchInput').value.toLowerCase();
  var cards = document.querySelectorAll('.product-card');
  var v = 0;
  cards.forEach(function(c) {
    var ok = (!q || c.dataset.name.includes(q) || c.dataset.desc.includes(q)) &&
             (activeCategory === 'all' || c.dataset.category === activeCategory);
    c.style.display = ok ? '' : 'none';
    if (ok) v++;
  });
  document.getElementById('emptyState').classList.toggle('hidden', v > 0);
}
function filterByCategory(cat) {
  activeCategory = cat;
  document.querySelectorAll('.cat-btn').forEach(function(b) {
    b.classList.toggle('active', b.textContent.trim() === (cat === 'all' ? 'الكل' : cat));
  });
  filterProducts();
}

document.addEventListener('keydown', function(e) {
  if (e.key === 'Escape') { closeCheckout(); closeOrderModal(); closeCart(); closeChatWidget(); }
});
</script>

<!-- AI CHAT WIDGET -->
{% raw %}<style>
.chat-widget{position:fixed;bottom:24px;right:24px;z-index:200;font-family:'IBM Plex Sans Arabic',sans-serif;}
.chat-btn{width:60px;height:60px;border-radius:50%;background:#0f172a;color:white;border:none;cursor:pointer;font-size:24px;box-shadow:0 8px 25px rgba(0,0,0,.25);transition:all .3s;display:flex;align-items:center;justify-content:center;}
.chat-btn:hover{transform:scale(1.08);background:#1e293b;}
.chat-box{display:none;position:absolute;bottom:75px;right:0;width:320px;background:white;border-radius:24px;box-shadow:0 20px 60px rgba(0,0,0,.15);overflow:hidden;border:1px solid #e2e8f0;}
.chat-header{background:#0f172a;color:white;padding:16px 20px;display:flex;align-items:center;gap:10px;}
#chatHeader .dot{width:8px;height:8px;background:#22c55e;border-radius:50%;animation:pulse 2s infinite;}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:.4}}
.chat-messages{height:260px;overflow-y:auto;padding:16px;space-y:8px;display:flex;flex-direction:column;gap:8px;}
.chat-messages::-webkit-scrollbar{width:4px}.chat-messages::-webkit-scrollbar-thumb{background:#e2e8f0;border-radius:10px}
.msg-user{background:#0f172a;color:white;padding:10px 14px;border-radius:18px 18px 4px 18px;font-size:13px;align-self:flex-end;max-width:80%;}
.msg-bot{background:#f1f5f9;color:#1e293b;padding:10px 14px;border-radius:18px 18px 18px 4px;font-size:13px;align-self:flex-start;max-width:85%;line-height:1.5;}
.msg-typing{background:#f1f5f9;padding:10px 16px;border-radius:18px 18px 18px 4px;align-self:flex-start;}
.typing-dots span{display:inline-block;width:6px;height:6px;background:#94a3b8;border-radius:50%;margin:0 2px;animation:bounce .8s infinite;}
.typing-dots span:nth-child(2){animation-delay:.15s}.typing-dots span:nth-child(3){animation-delay:.3s}
@keyframes bounce{0%,80%,100%{transform:translateY(0)}40%{transform:translateY(-6px)}}
.chat-input-area{border-top:1px solid #f1f5f9;padding:12px;display:flex;gap:8px;}
.chat-input{flex:1;border:1.5px solid #e2e8f0;border-radius:12px;padding:10px 14px;font-size:13px;outline:none;font-family:inherit;}
.chat-input:focus{border-color:#b45309;}
.chat-send-btn{background:#0f172a;color:white;border:none;border-radius:12px;width:40px;height:40px;cursor:pointer;display:flex;align-items:center;justify-content:center;transition:all .2s;}
.chat-send-btn:hover{background:#b45309;}
@media(max-width:380px){.chat-box-inner{width:290px;right:-10px;}}
</style>{% endraw %}

<div id="chatWidget" class="chat-widget">
  <div id="chatBox" class="chat-box">
    <div id="chatHeader" class="chat-header">
      <div class="dot"></div>
      <div>
        <p style="font-weight:700;font-size:14px;margin:0;">مساعد انجازك</p>
        <p style="font-size:11px;opacity:.7;margin:0;">متاح الان للمساعدة</p>
      </div>
    </div>
    <div id="chatMessages" class="chat-messages">
      <div class="msg-bot">مرحباً! انا مساعد انجازك الذكي 🎓<br>كيف يمكنني مساعدتك اليوم؟</div>
    </div>
    <div id="chatInputArea" class="chat-input-area">
      <input id="chatInput" class="chat-input" placeholder="اكتب سؤالك..." onkeydown="if(event.key==='Enter') sendChatMsg()">
      <button id="chatSendBtn" class="chat-send-btn" onclick="sendChatMsg()"><i class="fas fa-paper-plane" style="font-size:14px;"></i></button>
    </div>
  </div>
  <button id="chatBtn" class="chat-btn" onclick="toggleChat()" title="تحدث مع المساعد">
    <i class="fas fa-robot" id="chatBtnIcon"></i>
  </button>
</div>

<script>
var chatOpen = false;
function toggleChat() {
  chatOpen = !chatOpen;
  document.getElementById('chatBox').style.display = chatOpen ? 'block' : 'none';
  document.getElementById('chatBtnIcon').className = chatOpen ? 'fas fa-times' : 'fas fa-robot';
  if (chatOpen) document.getElementById('chatInput').focus();
}
function closeChatWidget() {
  chatOpen = false;
  document.getElementById('chatBox').style.display = 'none';
  document.getElementById('chatBtnIcon').className = 'fas fa-robot';
}
async function sendChatMsg() {
  var input = document.getElementById('chatInput');
  var msg = input.value.trim();
  if (!msg) return;
  input.value = '';
  var msgs = document.getElementById('chatMessages');
  msgs.innerHTML += '<div class="msg-user">' + msg + '</div>';
  msgs.innerHTML += '<div class="msg-typing" id="typingIndicator"><div class="typing-dots"><span></span><span></span><span></span></div></div>';
  msgs.scrollTop = msgs.scrollHeight;
  try {
    var r = await fetch('/api/chat', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({message: msg})
    });
    var d = await r.json();
    var typing = document.getElementById('typingIndicator');
    if (typing) typing.remove();
    if (d.status === 'success') {
      msgs.innerHTML += '<div class="msg-bot">' + d.reply.replace(/\n/g, '<br>') + '</div>';
    } else {
      msgs.innerHTML += '<div class="msg-bot">عذراً، حدث خطا. حاول مجدداً.</div>';
    }
  } catch(e) {
    var typing = document.getElementById('typingIndicator');
    if (typing) typing.remove();
    msgs.innerHTML += '<div class="msg-bot">تعذر الاتصال. حاول لاحقاً.</div>';
  }
  msgs.scrollTop = msgs.scrollHeight;
}
</script>
</body></html>"""

# ===================== ADMIN HTML =====================
ADMIN_HTML = """<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>لوحة الادارة | انجازك</title>
<script src="https://cdn.tailwindcss.com"></script>
<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans+Arabic:wght@400;600;700&display=swap" rel="stylesheet">
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
<style>
body{font-family:'IBM Plex Sans Arabic',sans-serif;background:#f1f5f9;}
.cs{box-shadow:0 4px 6px -1px rgb(0 0 0/.08);}
.scr::-webkit-scrollbar{width:4px;height:4px}.scr::-webkit-scrollbar-thumb{background:#cbd5e1;border-radius:10px}
.tab-btn{transition:all .2s;border-bottom:3px solid transparent;white-space:nowrap;padding-bottom:10px;font-size:12px;}
.tab-btn.active{border-color:#b45309;color:#b45309;font-weight:700;}
.oc{transition:all .2s;}
.oc:hover{transform:translateY(-1px);box-shadow:0 6px 16px -4px rgba(0,0,0,.1);}
</style>
</head>
<body class="min-h-screen pb-20">

<nav class="bg-white border-b border-slate-200 px-4 py-3 sticky top-0 z-40 shadow-sm">
  <div class="max-w-7xl mx-auto flex justify-between items-center">
    <div class="flex items-center gap-3">
      <div class="w-10 h-10 bg-amber-600 rounded-lg flex items-center justify-center text-white">
        <i class="fas fa-lock text-sm"></i>
      </div>
      <div>
        <h1 class="text-base font-bold text-slate-800">انجازك | لوحة الادارة</h1>
        <p class="text-[10px] text-slate-400">تحكم كامل في المتجر والطلبات</p>
      </div>
    </div>
    <div class="flex gap-2">
      <a href="/" class="text-xs bg-slate-100 px-3 py-2 rounded-lg font-bold text-slate-600 hover:bg-slate-200 transition-all"><i class="fas fa-store ml-1"></i>المتجر</a>
      <a href="/logout" class="text-xs bg-red-50 px-3 py-2 rounded-lg font-bold text-red-500 hover:bg-red-100 transition-all"><i class="fas fa-sign-out-alt ml-1"></i>خروج</a>
    </div>
  </div>
</nav>

<div class="max-w-7xl mx-auto px-4 py-8 space-y-8">

  <!-- Stats -->
  <div class="grid grid-cols-2 lg:grid-cols-4 gap-4">
    <div class="bg-white p-5 rounded-2xl cs border-r-4 border-amber-500">
      <p class="text-slate-400 text-[11px] font-bold mb-1">اجمالي المبيعات</p>
      <p class="text-2xl font-black">{{ "%.0f"|format(total_sales) }} ر.س</p>
    </div>
    <div class="bg-white p-5 rounded-2xl cs border-r-4 border-blue-500">
      <p class="text-slate-400 text-[11px] font-bold mb-1">طلبات جديدة</p>
      <p class="text-2xl font-black text-blue-600">{{ total_new }}</p>
    </div>
    <div class="bg-white p-5 rounded-2xl cs border-r-4 border-amber-400">
      <p class="text-slate-400 text-[11px] font-bold mb-1">تحت الاجراء</p>
      <p class="text-2xl font-black text-amber-600">{{ total_processing }}</p>
    </div>
    <div class="bg-white p-5 rounded-2xl cs border-r-4 border-green-500">
      <p class="text-slate-400 text-[11px] font-bold mb-1">مكتملة</p>
      <p class="text-2xl font-black text-green-600">{{ completed_orders|length }}</p>
    </div>
  </div>

  <div class="grid grid-cols-1 lg:grid-cols-3 gap-8">

    <!-- Settings -->
    <div id="settings" class="bg-white p-6 rounded-3xl cs h-fit">
      <h3 class="font-bold text-slate-800 mb-5 flex items-center gap-2 text-base">
        <i class="fas fa-cog text-amber-600"></i> اعدادات التواصل
      </h3>
      <form action="/admin/update_settings" method="POST" class="space-y-3">
        <div>
          <label class="text-[10px] font-bold text-slate-400 block mb-1">رابط واتساب (للزوار)</label>
          <input name="whatsapp" value="{{ settings.whatsapp }}" class="w-full p-3 bg-slate-50 border border-slate-200 rounded-xl text-xs outline-none focus:border-amber-500">
        </div>
        <div>
          <label class="text-[10px] font-bold text-slate-400 block mb-1">رقم الواتساب للاشعارات (966XXXXXXXXX)</label>
          <input name="whatsapp_number" value="{{ settings.whatsapp_number }}" class="w-full p-3 bg-slate-50 border border-slate-200 rounded-xl text-xs outline-none focus:border-amber-500">
        </div>
        <div class="grid grid-cols-2 gap-2">
          <div>
            <label class="text-[10px] font-bold text-slate-400 block mb-1">انستغرام</label>
            <input name="instagram" value="{{ settings.instagram }}" class="w-full p-3 bg-slate-50 border border-slate-200 rounded-xl text-xs">
          </div>
          <div>
            <label class="text-[10px] font-bold text-slate-400 block mb-1">تيك توك</label>
            <input name="tiktok" value="{{ settings.tiktok }}" class="w-full p-3 bg-slate-50 border border-slate-200 rounded-xl text-xs">
          </div>
        </div>
        <div class="grid grid-cols-2 gap-2">
          <div>
            <label class="text-[10px] font-bold text-slate-400 block mb-1">الهاتف</label>
            <input name="phone" value="{{ settings.phone }}" class="w-full p-3 bg-slate-50 border border-slate-200 rounded-xl text-xs">
          </div>
          <div>
            <label class="text-[10px] font-bold text-slate-400 block mb-1">البريد</label>
            <input name="email" value="{{ settings.email }}" class="w-full p-3 bg-slate-50 border border-slate-200 rounded-xl text-xs">
          </div>
        </div>
        <div>
          <label class="text-[10px] font-bold text-slate-400 block mb-1">شريط الاعلانات</label>
          <textarea name="moving_text" class="w-full p-3 bg-slate-50 border border-slate-200 rounded-xl text-xs h-16">{{ settings.moving_text }}</textarea>
        </div>
        <div>
          <label class="text-[10px] font-bold text-slate-400 block mb-1">نص الفوتر</label>
          <textarea name="footer_text" class="w-full p-3 bg-slate-50 border border-slate-200 rounded-xl text-xs h-14">{{ settings.footer_text }}</textarea>
        </div>
        <button type="submit" class="w-full bg-slate-900 text-white py-3 rounded-xl font-bold text-xs hover:bg-slate-800 transition-all">
          <i class="fas fa-save ml-1"></i> حفظ الاعدادات
        </button>
      </form>
    </div>

    <!-- Orders -->
    <div class="lg:col-span-2 bg-white p-6 rounded-3xl cs">
      <div class="flex items-center justify-between mb-5">
        <h3 class="font-bold text-slate-800 flex items-center gap-2 text-base">
          <i class="fas fa-list text-blue-600"></i> الطلبات
        </h3>
        <a href="/admin/export_orders" class="text-[10px] bg-green-50 text-green-600 border border-green-200 px-3 py-2 rounded-xl font-bold hover:bg-green-100 transition-all">
          <i class="fas fa-file-csv ml-1"></i> تصدير
        </a>
      </div>

      <div class="flex gap-5 border-b border-slate-100 mb-5 overflow-x-auto">
        <button onclick="showTab('new')" id="tab-new" class="tab-btn active">🔵 جديدة ({{ total_new }})</button>
        <button onclick="showTab('proc')" id="tab-proc" class="tab-btn">🟡 تحت الاجراء ({{ total_processing }})</button>
        <button onclick="showTab('done')" id="tab-done" class="tab-btn">🟢 مكتملة ({{ completed_orders|length }})</button>
      </div>

      <!-- NEW -->
      <div id="panel-new" class="space-y-3 min-h-24">
        {% for o in new_orders %}
        <div class="oc bg-blue-50 border border-blue-100 rounded-2xl p-4">
          <div class="flex gap-3 items-start">
            <div class="flex-grow min-w-0">
              <div class="flex gap-2 items-center mb-1 flex-wrap">
                <span class="bg-blue-100 text-blue-700 text-[10px] font-black px-2 py-0.5 rounded-full">#{{ o.id }}</span>
                <span class="text-slate-400 text-[10px]">{{ o.order_date.strftime('%Y/%m/%d %H:%M') }}</span>
              </div>
              <p class="font-bold text-slate-800">{{ o.customer_name }}</p>
              <a href="tel:{{ o.customer_phone }}" class="text-xs text-amber-600 font-mono hover:underline">{{ o.customer_phone }}</a>
              <div class="mt-1 space-y-0.5">
                {% if o.parsed_cart %}
                  {% for item in o.parsed_cart %}
                  <p class="text-[11px] text-slate-600">• {{ item.name }} &times;{{ item.qty }}</p>
                  {% endfor %}
                {% else %}
                  <p class="text-[11px] text-slate-600">• {{ o.product_name }}</p>
                {% endif %}
                {% if o.cart_total and o.cart_total > 0 %}
                <p class="text-sm font-black text-green-700">{{ "%.0f"|format(o.cart_total) }} ر.س</p>
                {% endif %}
              </div>
              {% if o.customer_notes %}
              <div class="mt-2 bg-white rounded-xl px-3 py-2">
                <p class="text-[10px] text-slate-500 font-bold mb-0.5">ملاحظات العميل:</p>
                <p class="text-[11px] text-slate-700">{{ o.customer_notes }}</p>
              </div>
              {% endif %}
            </div>
            <div class="flex flex-col gap-1.5 shrink-0 min-w-[90px]">
              <a href="/admin/set_order_status/{{ o.id }}/تحت الإجراء"
                class="text-[10px] bg-amber-500 hover:bg-amber-600 text-white px-2 py-1.5 rounded-xl font-bold text-center transition-all">
                → تنفيذ
              </a>
              <a href="/admin/set_order_status/{{ o.id }}/مكتمل"
                class="text-[10px] bg-green-500 hover:bg-green-600 text-white px-2 py-1.5 rounded-xl font-bold text-center transition-all">
                ✓ مكتمل
              </a>
              <a href="https://wa.me/{{ o.customer_phone|replace(' ','')|replace('+','') }}" target="_blank"
                class="text-[10px] bg-green-50 text-green-700 border border-green-200 px-2 py-1.5 rounded-xl font-bold text-center hover:bg-green-100 transition-all">
                <i class="fab fa-whatsapp"></i> واتساب
              </a>
              <button onclick="analyzeOrder({{ o.id }})"
                class="text-[10px] bg-purple-50 text-purple-600 border border-purple-200 px-2 py-1.5 rounded-xl font-bold text-center hover:bg-purple-100 transition-all">
                <i class="fas fa-robot"></i> AI
              </button>
              <a href="/admin/delete_order/{{ o.id }}" onclick="return confirm('حذف الطلب؟')"
                class="text-[10px] bg-red-50 text-red-500 px-2 py-1.5 rounded-xl font-bold text-center hover:bg-red-500 hover:text-white transition-all">
                <i class="fas fa-trash"></i> حذف
              </a>
            </div>
          </div>
        </div>
        {% endfor %}
        {% if not new_orders %}
        <div class="py-14 text-center text-slate-300 text-xs"><i class="fas fa-inbox text-3xl block mb-3"></i>لا توجد طلبات جديدة</div>
        {% endif %}
      </div>

      <!-- PROCESSING -->
      <div id="panel-proc" class="hidden space-y-3 min-h-24">
        {% for o in processing_orders %}
        <div class="oc bg-amber-50 border border-amber-100 rounded-2xl p-4">
          <div class="flex gap-3 items-start">
            <div class="flex-grow min-w-0">
              <div class="flex gap-2 items-center mb-1 flex-wrap">
                <span class="bg-amber-100 text-amber-700 text-[10px] font-black px-2 py-0.5 rounded-full">#{{ o.id }}</span>
                <span class="text-slate-400 text-[10px]">{{ o.order_date.strftime('%Y/%m/%d %H:%M') }}</span>
              </div>
              <p class="font-bold text-slate-800">{{ o.customer_name }}</p>
              <a href="tel:{{ o.customer_phone }}" class="text-xs text-amber-600 font-mono hover:underline">{{ o.customer_phone }}</a>
              <div class="mt-1 space-y-0.5">
                {% if o.parsed_cart %}
                  {% for item in o.parsed_cart %}
                  <p class="text-[11px] text-slate-600">• {{ item.name }} &times;{{ item.qty }}</p>
                  {% endfor %}
                {% else %}
                  <p class="text-[11px] text-slate-600">• {{ o.product_name }}</p>
                {% endif %}
                {% if o.cart_total and o.cart_total > 0 %}
                <p class="text-sm font-black text-green-700">{{ "%.0f"|format(o.cart_total) }} ر.س</p>
                {% endif %}
              </div>
              {% if o.customer_notes %}
              <div class="mt-2 bg-white rounded-xl px-3 py-2">
                <p class="text-[10px] text-slate-500 font-bold mb-0.5">ملاحظات العميل:</p>
                <p class="text-[11px] text-slate-700">{{ o.customer_notes }}</p>
              </div>
              {% endif %}
            </div>
            <div class="flex flex-col gap-1.5 shrink-0 min-w-[90px]">
              <a href="/admin/set_order_status/{{ o.id }}/جديد"
                class="text-[10px] bg-blue-50 text-blue-600 border border-blue-200 px-2 py-1.5 rounded-xl font-bold text-center hover:bg-blue-100 transition-all">
                ← جديد
              </a>
              <a href="/admin/set_order_status/{{ o.id }}/مكتمل"
                class="text-[10px] bg-green-500 hover:bg-green-600 text-white px-2 py-1.5 rounded-xl font-bold text-center transition-all">
                ✓ مكتمل
              </a>
              <button onclick="analyzeOrder({{ o.id }})"
                class="text-[10px] bg-purple-50 text-purple-600 border border-purple-200 px-2 py-1.5 rounded-xl font-bold text-center hover:bg-purple-100 transition-all">
                <i class="fas fa-robot"></i> AI
              </button>
              <a href="https://wa.me/{{ o.customer_phone|replace(' ','')|replace('+','') }}" target="_blank"
                class="text-[10px] bg-green-50 text-green-700 border border-green-200 px-2 py-1.5 rounded-xl font-bold text-center hover:bg-green-100 transition-all">
                <i class="fab fa-whatsapp"></i> واتساب
              </a>
              <a href="/admin/delete_order/{{ o.id }}" onclick="return confirm('حذف الطلب؟')"
                class="text-[10px] bg-red-50 text-red-500 px-2 py-1.5 rounded-xl font-bold text-center hover:bg-red-500 hover:text-white transition-all">
                <i class="fas fa-trash"></i> حذف
              </a>
            </div>
          </div>
        </div>
        {% endfor %}
        {% if not processing_orders %}
        <div class="py-14 text-center text-slate-300 text-xs"><i class="fas fa-hourglass-half text-3xl block mb-3"></i>لا توجد طلبات تحت الاجراء</div>
        {% endif %}
      </div>

      <!-- COMPLETED -->
      <div id="panel-done" class="hidden">
        <div class="overflow-x-auto scr">
          <table class="w-full text-right min-w-[500px]">
            <thead>
              <tr class="text-[10px] text-slate-400 border-b border-slate-100 uppercase tracking-wide">
                <th class="pb-3 pr-2">#</th>
                <th class="pb-3">العميل</th>
                <th class="pb-3">الخدمة</th>
                <th class="pb-3">القيمة</th>
                <th class="pb-3">الملاحظات</th>
                <th class="pb-3 text-center">اجراء</th>
              </tr>
            </thead>
            <tbody class="text-xs">
            {% for o in completed_orders %}
            <tr class="border-b border-slate-50 hover:bg-slate-50/70">
              <td class="py-3 pr-2 text-slate-400 font-mono text-[10px]">#{{ o.id }}<br><span class="text-[9px]">{{ o.order_date.strftime('%y/%m/%d') }}</span></td>
              <td class="py-3">
                <p class="font-bold text-slate-700">{{ o.customer_name }}</p>
                <a href="tel:{{ o.customer_phone }}" class="text-[10px] text-amber-600 hover:underline">{{ o.customer_phone }}</a>
              </td>
              <td class="py-3 text-blue-600 max-w-[120px]">
                <div class="truncate">{{ o.product_name }}</div>
                {% if o.parsed_cart and o.parsed_cart|length > 1 %}<span class="text-[10px] text-slate-400">+{{ o.parsed_cart|length - 1 }} خدمة اخرى</span>{% endif %}
              </td>
              <td class="py-3 font-black text-green-700">{{ "%.0f"|format(o.cart_total or o.product_price or 0) }} ر.س</td>
              <td class="py-3 max-w-[120px]">
                <p class="text-[10px] text-slate-500 truncate">{{ (o.customer_notes or '')[:50] }}</p>
              </td>
              <td class="py-3">
                <div class="flex justify-center gap-1">
                  <a href="/admin/set_order_status/{{ o.id }}/تحت الإجراء"
                    class="text-[10px] bg-amber-50 text-amber-600 px-2 py-1 rounded-lg font-bold hover:bg-amber-100 transition-all">اعادة فتح</a>
                  <a href="/admin/delete_order/{{ o.id }}" onclick="return confirm('حذف؟')"
                    class="text-[10px] bg-red-50 text-red-400 px-2 py-1 rounded-lg hover:bg-red-100 transition-all"><i class="fas fa-trash"></i></a>
                </div>
              </td>
            </tr>
            {% endfor %}
            {% if not completed_orders %}
            <tr><td colspan="6" class="py-14 text-center text-slate-300">لا توجد طلبات مكتملة بعد</td></tr>
            {% endif %}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  </div>

  <!-- Add Service -->
  <div id="services" class="bg-slate-900 rounded-3xl p-8 text-white shadow-2xl">
    <h3 class="text-xl font-bold mb-6 flex items-center gap-3">
      <i class="fas fa-plus-circle text-amber-500"></i> اضافة خدمة جديدة
    </h3>
    <form method="POST" enctype="multipart/form-data" class="grid grid-cols-1 md:grid-cols-2 gap-6">
      <div class="space-y-4">
        <input name="name" placeholder="عنوان الخدمة *" required
          class="w-full p-4 bg-white/5 border border-white/10 rounded-2xl outline-none focus:border-amber-500 text-sm transition-all">
        <div class="grid grid-cols-3 gap-3">
          <div class="relative">
            <input name="price" id="newPrice" type="number" step="0.01" placeholder="السعر"
              class="w-full p-4 bg-white/5 border border-white/10 rounded-2xl outline-none focus:border-amber-500 text-sm">
            <button type="button" onclick="suggestPrice()"
              class="absolute left-2 top-1/2 -translate-y-1/2 bg-purple-600 hover:bg-purple-500 text-white text-[10px] px-2 py-1 rounded-lg transition-all"
              title="اقتراح سعر بالذكاء الاصطناعي">
              <i class="fas fa-robot"></i>
            </button>
          </div>
          <input name="old_price" type="number" step="0.01" placeholder="السعر القديم"
            class="p-4 bg-white/5 border border-white/10 rounded-2xl outline-none focus:border-amber-500 text-sm">
          <input name="category" placeholder="التصنيف"
            class="p-4 bg-white/5 border border-white/10 rounded-2xl outline-none focus:border-amber-500 text-sm">
        </div>
        <div class="p-4 bg-white/5 border border-dashed border-white/20 rounded-2xl">
          <label class="text-[10px] text-slate-400 font-bold block mb-2">صورة الخدمة</label>
          <input type="file" name="product_file" accept="image/*" class="text-xs text-slate-400 w-full cursor-pointer">
        </div>
      </div>
      <div class="flex flex-col gap-4">
        <textarea name="description" placeholder="وصف الخدمة..."
          class="flex-grow p-4 bg-white/5 border border-white/10 rounded-2xl outline-none focus:border-amber-500 text-sm min-h-[130px]"></textarea>
        <button type="submit" class="w-full bg-amber-600 hover:bg-amber-500 py-4 rounded-2xl font-black text-sm transition-all">
          <i class="fas fa-cloud-upload-alt ml-2"></i> نشر الخدمة
        </button>
      </div>
    </form>
  </div>

  <!-- Manage Products -->
  <div class="bg-white p-6 rounded-3xl cs">
    <h3 class="text-lg font-bold text-slate-800 mb-6 flex items-center gap-3">
      <i class="fas fa-boxes text-amber-600"></i> ادارة الخدمات الحالية
    </h3>
    <div class="overflow-x-auto scr">
      <table class="w-full text-right min-w-[650px]">
        <thead>
          <tr class="text-[10px] text-slate-400 border-b-2 border-slate-100 uppercase tracking-widest">
            <th class="pb-4 pr-3">#</th>
            <th class="pb-4">الخدمة</th>
            <th class="pb-4">السعر</th>
            <th class="pb-4">التصنيف</th>
            <th class="pb-4 text-center">الحالة</th>
            <th class="pb-4 text-center">الاجراءات</th>
          </tr>
        </thead>
        <tbody class="text-xs">
        {% for p in products %}
        <tr class="hover:bg-slate-50 border-b border-slate-50 {% if not p.is_active %}opacity-50{% endif %}">
          <td class="py-4 pr-3 text-slate-400">{{ p.id }}</td>
          <td class="py-4 font-bold text-slate-700 max-w-[200px]">
            <div class="truncate">{{ p.name }}</div>
            <div class="text-[10px] text-slate-400 font-normal truncate">{{ (p.description or '')[:45] }}</div>
          </td>
          <td class="py-4">
            <span class="font-black">{{ p.price }} ر.س</span>
            {% if p.old_price %}<span class="text-[10px] text-slate-400 line-through block">{{ p.old_price }}</span>{% endif %}
          </td>
          <td class="py-4"><span class="bg-amber-50 text-amber-700 px-2 py-1 rounded-full text-[10px] font-bold">{{ p.category }}</span></td>
          <td class="py-4 text-center">
            <a href="/admin/toggle_product/{{ p.id }}"
              class="text-[10px] px-3 py-1.5 rounded-full font-bold transition-all {% if p.is_active %}bg-green-100 text-green-700 hover:bg-green-200{% else %}bg-slate-100 text-slate-500 hover:bg-slate-200{% endif %}">
              {% if p.is_active %}<i class="fas fa-eye ml-1"></i>مرئي{% else %}<i class="fas fa-eye-slash ml-1"></i>مخفي{% endif %}
            </a>
          </td>
          <td class="py-4">
            <div class="flex justify-center gap-2">
              <button onclick='openEdit({{ p.id }}, {{ p.name|tojson }}, {{ p.price }}, {{ p.old_price if p.old_price else "null" }}, {{ p.category|tojson }}, {{ (p.description or "")|tojson }})'
                class="w-8 h-8 bg-blue-50 text-blue-600 rounded-lg flex items-center justify-center hover:bg-blue-600 hover:text-white transition-all">
                <i class="fas fa-edit text-xs"></i>
              </button>
              <a href="/admin/delete_product/{{ p.id }}" onclick="return confirm('حذف الخدمة؟')"
                class="w-8 h-8 bg-red-50 text-red-500 rounded-lg flex items-center justify-center hover:bg-red-600 hover:text-white transition-all">
                <i class="fas fa-trash text-xs"></i>
              </a>
            </div>
          </td>
        </tr>
        {% endfor %}
        {% if not products %}
        <tr><td colspan="6" class="py-14 text-center text-slate-300">لا توجد خدمات مضافة بعد.</td></tr>
        {% endif %}
        </tbody>
      </table>
    </div>
  </div>
</div>

<!-- Edit Modal -->
<div id="editModal" style="display:none" class="fixed inset-0 bg-slate-900/60 backdrop-blur-md flex items-center justify-center p-4 z-[100]">
  <div class="bg-white rounded-3xl w-full max-w-lg p-8 shadow-2xl relative max-h-[90vh] overflow-y-auto">
    <button onclick="closeEdit()" class="absolute top-5 left-5 w-9 h-9 rounded-full bg-slate-100 flex items-center justify-center text-slate-500 hover:bg-slate-200">
      <i class="fas fa-times"></i>
    </button>
    <h3 class="text-xl font-black mb-6 flex items-center gap-2">
      <i class="fas fa-edit text-amber-600"></i> تعديل الخدمة
    </h3>
    <form id="editForm" method="POST" enctype="multipart/form-data" class="space-y-4">
      <input name="name" id="eName" placeholder="اسم الخدمة"
        class="w-full p-4 bg-slate-50 border border-slate-200 rounded-2xl text-sm outline-none focus:border-amber-500">
      <div class="grid grid-cols-3 gap-3">
        <input name="price" id="ePrice" type="number" step="0.01" placeholder="السعر"
          class="p-4 bg-slate-50 border border-slate-200 rounded-2xl text-sm outline-none focus:border-amber-500">
        <input name="old_price" id="eOldPrice" type="number" step="0.01" placeholder="القديم"
          class="p-4 bg-slate-50 border border-slate-200 rounded-2xl text-sm outline-none focus:border-amber-500">
        <input name="category" id="eCategory" placeholder="التصنيف"
          class="p-4 bg-slate-50 border border-slate-200 rounded-2xl text-sm outline-none focus:border-amber-500">
      </div>
      <textarea name="description" id="eDesc" placeholder="الوصف" class="w-full p-4 bg-slate-50 border border-slate-200 rounded-2xl text-sm outline-none focus:border-amber-500 h-28 resize-none"></textarea>
      <div class="p-3 bg-slate-50 border border-dashed border-slate-200 rounded-2xl">
        <label class="text-[10px] font-bold text-slate-400 block mb-1">تغيير الصورة (اختياري)</label>
        <input type="file" name="product_file" accept="image/*" class="text-xs text-slate-500 w-full">
      </div>
      <button type="submit" class="w-full bg-amber-600 hover:bg-amber-500 text-white py-4 rounded-2xl font-black text-sm transition-all">
        حفظ التعديلات
      </button>
    </form>
  </div>
</div>

<script>
function showTab(t) {
  ['new','proc','done'].forEach(function(x){
    document.getElementById('panel-'+x).classList.toggle('hidden', x!==t);
    document.getElementById('tab-'+x).classList.toggle('active', x===t);
  });
}
function openEdit(id, name, price, oldPrice, category, desc) {
  document.getElementById('editForm').action = '/admin/edit_product/' + id;
  document.getElementById('eName').value = name;
  document.getElementById('ePrice').value = price;
  document.getElementById('eOldPrice').value = oldPrice || '';
  document.getElementById('eCategory').value = category;
  document.getElementById('eDesc').value = desc;
  document.getElementById('editModal').style.display = 'flex';
  document.body.style.overflow = 'hidden';
}
function closeEdit() {
  document.getElementById('editModal').style.display = 'none';
  document.body.style.overflow = '';
}
window.addEventListener('click', function(e){ if(e.target===document.getElementById('editModal')) closeEdit(); if(e.target===document.getElementById('aiModal')) closeAiModal(); });
document.addEventListener('keydown', function(e){ if(e.key==='Escape'){ closeEdit(); closeAiModal(); } });

async function analyzeOrder(orderId) {
  document.getElementById('aiModalTitle').innerText = 'تحليل الطلب #' + orderId;
  document.getElementById('aiModalBody').innerHTML = '<div class="flex justify-center py-8"><div class="w-8 h-8 border-4 border-purple-200 border-t-purple-600 rounded-full animate-spin"></div></div>';
  document.getElementById('aiModal').style.display = 'flex';
  document.body.style.overflow = 'hidden';
  try {
    var r = await fetch('/api/ai/analyze_order', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({order_id: orderId})
    });
    var d = await r.json();
    if (d.status === 'success') {
      document.getElementById('aiModalBody').innerHTML = '<div style="white-space:pre-wrap;line-height:1.7;font-size:13px;color:#374151;">' + d.analysis + '</div>';
    } else {
      document.getElementById('aiModalBody').innerHTML = '<p class="text-red-500 text-sm">' + (d.message || 'حدث خطا') + '</p>';
    }
  } catch(e) {
    document.getElementById('aiModalBody').innerHTML = '<p class="text-red-500 text-sm">تعذر الاتصال</p>';
  }
}

async function suggestPrice() {
  var name = document.querySelector('input[name="name"]').value.trim();
  var desc = document.querySelector('textarea[name="description"]').value.trim();
  var cat = document.querySelector('input[name="category"]').value.trim();
  if (!name && !desc) { alert('اكتب اسم الخدمة او وصفها اولا'); return; }
  document.getElementById('aiModalTitle').innerText = 'اقتراح السعر بالذكاء الاصطناعي';
  document.getElementById('aiModalBody').innerHTML = '<div class="flex justify-center py-8"><div class="w-8 h-8 border-4 border-purple-200 border-t-purple-600 rounded-full animate-spin"></div></div>';
  document.getElementById('aiModal').style.display = 'flex';
  document.body.style.overflow = 'hidden';
  try {
    var r = await fetch('/api/ai/suggest_price', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({name: name, description: desc, category: cat})
    });
    var d = await r.json();
    if (d.status === 'success') {
      document.getElementById('aiModalBody').innerHTML = '<div style="white-space:pre-wrap;line-height:1.7;font-size:13px;color:#374151;">' + d.suggestion + '</div>';
    } else {
      document.getElementById('aiModalBody').innerHTML = '<p class="text-red-500 text-sm">' + (d.message || 'حدث خطا') + '</p>';
    }
  } catch(e) {
    document.getElementById('aiModalBody').innerHTML = '<p class="text-red-500 text-sm">تعذر الاتصال</p>';
  }
}

function closeAiModal() {
  document.getElementById('aiModal').style.display = 'none';
  document.body.style.overflow = '';
}
</script>

<!-- AI Modal -->
<div id="aiModal" style="display:none" class="fixed inset-0 bg-slate-900/60 backdrop-blur-md flex items-center justify-center p-4 z-[200]">
  <div class="bg-white rounded-3xl w-full max-w-lg p-8 shadow-2xl relative max-h-[80vh] overflow-y-auto">
    <button onclick="closeAiModal()" class="absolute top-5 left-5 w-9 h-9 rounded-full bg-slate-100 flex items-center justify-center text-slate-500 hover:bg-slate-200">
      <i class="fas fa-times"></i>
    </button>
    <div class="flex items-center gap-3 mb-6">
      <div class="w-10 h-10 bg-purple-100 rounded-xl flex items-center justify-center">
        <i class="fas fa-robot text-purple-600"></i>
      </div>
      <h3 id="aiModalTitle" class="text-lg font-black text-slate-800"></h3>
    </div>
    <div id="aiModalBody" class="text-slate-700 text-sm leading-relaxed"></div>
  </div>
</div>
</body></html>"""

if __name__ == '__main__':
    app.run(debug=True)
