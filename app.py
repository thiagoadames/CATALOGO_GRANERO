from flask import Flask, render_template, request, redirect, url_for, session
import mysql.connector
import os
import re
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
import google.generativeai as genai

app = Flask(__name__)

# =========================================================================
# CONFIGURACIÓN DE IA (GEMINI)
# =========================================================================
genai.configure(api_key=os.environ.get("GEMINI_API_KEY", "TU_API_KEY_AQUI"))
model = genai.GenerativeModel('gemini-1.5-flash')

def generar_descripcion_ia(nombre_producto):
    try:
        prompt = f"Genera una descripción corta y vendedora para un producto llamado {nombre_producto}."
        response = model.generate_content(prompt)
        return response.text.strip()
    except:
        return "Descripción profesional del producto."

def clasificar_producto(nombre_producto, categorias_disponibles):
    if not categorias_disponibles:
        return None
    try:
        nombres_categorias = ", ".join([c['nombre_categoria'] for c in categorias_disponibles])
        prompt = f"Clasifica el producto '{nombre_producto}' en una de estas categorías: {nombres_categorias}. Responde solo el nombre exacto de la categoría, sin explicaciones."
        response = model.generate_content(prompt)
        nombre_sugerido = response.text.strip()

        for cat in categorias_disponibles:
            if cat['nombre_categoria'].lower() == nombre_sugerido.lower():
                return cat['id_categoria']

        return categorias_disponibles[0]['id_categoria']
    except:
        return categorias_disponibles[0]['id_categoria'] if categorias_disponibles else None

# =========================================================================
# CLAVE SECRETA PARA SESIONES
# =========================================================================
app.secret_key = "clave_secreta_super_segura_para_el_granero"

# ==========================================
# CONFIGURACIÓN DE CARPETA PARA SUBIR FOTOS
# ==========================================
CARPETA_IMAGENES = os.path.join('static', 'imagenes')
app.config['UPLOAD_FOLDER'] = CARPETA_IMAGENES

# ==========================================
# CONFIGURACIÓN DE LA BASE DE DATOS
# ==========================================
def obtener_conexion():
    return mysql.connector.connect(
        host=os.environ.get("MYSQLHOST", "reseau.proxy.rlwy.net"),
        user=os.environ.get("MYSQLUSER", "root"),
        password=os.environ.get("MYSQLPASSWORD", "edkZloxlaigQCBmHyYkjHjKEPtaMQRbo"),
        database=os.environ.get("MYSQLDATABASE", "plataforma_catalogos"),
        port=int(os.environ.get("MYSQLPORT", 59970))
    )


# =========================================================================
# MIDDLEWARE DE SEGURIDAD
# =========================================================================
@app.after_request
def añadir_headers_seguridad(response):
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['X-XSS-Protection'] = '1; mode=block'
    return response


# =========================================================================
# MANEJO GLOBAL DE ERRORES
# =========================================================================
@app.errorhandler(404)
def pagina_no_encontrada(e):
    return render_template('login.html', error="La página solicitada no existe o la URL cambió. Por favor inicia sesión."), 404

@app.errorhandler(500)
def error_interno_servidor(e):
    return "", 500


# =========================================================================
# CONTROL DE ACCESO (LOGIN CON VERIFICACIÓN DE HASH)
# =========================================================================
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        usuario_ingresado = request.form['usuario']
        contrasena_ingresada = request.form['contrasena']
        
        if not re.match(r'^[A-Za-z0-9]+$', contrasena_ingresada):
            return render_template('login.html', error="La contraseña solo debe contener letras y números.")
        
        try:
            conexion = obtener_conexion()
            cursor = conexion.cursor(dictionary=True)
            
            cursor.execute("SELECT id_usuario, contrasena, id_tienda FROM usuarios WHERE usuario = %s", (usuario_ingresado,))
            usuario_encontrado = cursor.fetchone()
            
            cursor.close()
            conexion.close()
            
            if usuario_encontrado and check_password_hash(usuario_encontrado['contrasena'], contrasena_ingresada):
                session['admin_logeado'] = True
                session['usuario_nombre'] = usuario_ingresado
                
                id_tienda_usuario = usuario_encontrado['id_tienda'] if usuario_encontrado['id_tienda'] else 1
                session['id_tienda'] = id_tienda_usuario
                
                return redirect(url_for('panel_administrador', id_tienda=id_tienda_usuario))
            else:
                mensaje_error = 'Usuario o contraseña incorrectos. '
                return render_template('login.html', error=mensaje_error)
                
        except mysql.connector.Error as err:
            return f""
            
    return render_template('login.html', error=None)


# =========================================================================
# RECUPERACIÓN DE CUENTA (INTEGRACIÓN WHATSAPP)
# =========================================================================
@app.route('/recuperar-cuenta', methods=['GET', 'POST'])
def recuperar_cuenta():
    if request.method == 'POST':
        email_ingresado = request.form['email'].strip()
        
        try:
            conexion = obtener_conexion()
            cursor = conexion.cursor(dictionary=True)
            
            sql = """
                SELECT t.nombre_tienda, t.telefono_whatsapp, u.usuario, u.contrasena 
                FROM tiendas t
                JOIN usuarios u ON t.id_tienda = u.id_tienda
                WHERE t.email_recuperacion = %s
            """
            cursor.execute(sql, (email_ingresado,))
            resultado = cursor.fetchone()
            
            cursor.close()
            conexion.close()
            
            if resultado:
                mensaje = f"Hola, tu usuario para {resultado['nombre_tienda']} es: {resultado['usuario']}. Tu contraseña está protegida por seguridad, si no la recuerdas solicítale al administrador restablecerla."
                link_whatsapp = f"https://wa.me/{resultado['telefono_whatsapp']}?text={mensaje}"
                
                return f"""
                
                
                
                
                """
            else:
                return ""
        except mysql.connector.Error as err:
            return f""
            
    return render_template('recuperar_cuenta.html')


# =========================================================================
# REGISTRO AUTOMATIZADO CON ENCRIPTACIÓN DE CONTRASEÑA
# =========================================================================
@app.route('/registrar-tienda', methods=['GET', 'POST'])
def registrar_tienda():
    if request.method == 'POST':
        nombre_tienda = request.form['nombre_tienda'].strip()
        raw_telefono = request.form['telefono'].strip()
        direccion = request.form['direccion'].strip()
        ciudad = request.form['ciudad'].strip()
        email_recuperacion = request.form['email_recuperacion'].strip()
        
        usuario = request.form['usuario'].strip()
        contrasena = request.form['contrasena'].strip()

        if not re.match(r'^[A-Za-z0-9]+$', contrasena):
            return ""
        
        contrasena_encriptada = generate_password_hash(contrasena)
        
        url_logo_db = '/static/imagenes/default_logo.png'
        if 'logo' in request.files:
            archivo_logo = request.files['logo']
            if archivo_logo.filename != '':
                nombre_archivo_seguro = secure_filename(archivo_logo.filename)
                ruta_guardado = os.path.join(app.config['UPLOAD_FOLDER'], nombre_archivo_seguro)
                archivo_logo.save(ruta_guardado)
                url_logo_db = f"/static/imagenes/{nombre_archivo_seguro}"
        
        slug = nombre_tienda.lower()
        slug = re.sub(r'[^a-z0-9\s-]', '', slug)
        slug = re.sub(r'[\s-]+', '-', slug).strip('-')
        
        if not raw_telefono.startswith('57') and len(raw_telefono) == 10:
            whatsapp_final = f"57{raw_telefono}"
        else:
            whatsapp_final = raw_telefono

        try:
            conexion = obtener_conexion()
            cursor = conexion.cursor()
            
            sql_tienda = """INSERT INTO tiendas (nombre_tienda, slug, telefono, direccion, ciudad, telefono_whatsapp, url_logo, email_recuperacion, color_primario, tipo_negocio, configuracion_subcarpetas) 
                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"""
            
            valores_tienda = (nombre_tienda, slug, whatsapp_final, direccion, ciudad, whatsapp_final, url_logo_db, email_recuperacion, '#0056b3', 'General', 0)
            
            cursor.execute(sql_tienda, valores_tienda)
            
            nuevo_id_tienda = cursor.lastrowid
            
            sql_usuario = """INSERT INTO usuarios (usuario, contrasena, id_tienda) 
                            VALUES (%s, %s, %s)"""
            valores_usuario = (usuario, contrasena_encriptada, nuevo_id_tienda)
            cursor.execute(sql_usuario, valores_usuario)
            
            conexion.commit()
            
            cursor.close()
            conexion.close()
            
            return redirect(url_for('login'))
            
        except mysql.connector.Error as err:
            return f""

    return render_template('registrar_tienda.html')


# =========================================================================
# CERRAR SESIÓN (LOGOUT)
# =========================================================================
@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))


# =========================================================================
# RUTA RAÍZ REDIRECCIONADA
# =========================================================================
@app.route('/')
def inicio():
    if not session.get('admin_logeado'):
        return redirect(url_for('login'))
    
    id_tienda_usuario = session.get('id_tienda', 1)
    return redirect(url_for('panel_administrador', id_tienda=id_tienda_usuario))


# =========================================================================
# PANEL DE ADMINISTRACIÓN
# =========================================================================
@app.route('/tienda//admin')
def panel_administrador(id_tienda):
    if not session.get('admin_logeado'):
        return redirect(url_for('login'))
        
    try:
        conexion = obtener_conexion()
        cursor = conexion.cursor(dictionary=True)
        
        cursor.execute("SELECT * FROM tiendas WHERE id_tienda = %s", (id_tienda,))
        datos_tienda = cursor.fetchone()
        
        nombre_tienda = datos_tienda['nombre_tienda'] if datos_tienda else "Mi Granero Piloto"
        slug_tienda = datos_tienda['slug'] if datos_tienda else "default-slug"
        color_tienda = datos_tienda.get('color_primario', '#0056b3') if datos_tienda else '#0056b3'
        
        cursor.execute("""
            SELECT p.id_producto, p.nombre_producto, p.precio, p.categoria, p.descripcion, p.url_imagen, p.id_tienda,
                   c.nombre_categoria
            FROM productos p
            LEFT JOIN categorias c ON p.categoria = c.id_categoria
            WHERE p.id_tienda = %s
        """, (id_tienda,))
        productos_tienda = cursor.fetchall()
        
        cursor.close()
        conexion.close()
        
        return render_template('panel_admin.html', 
                               id_tienda=id_tienda, 
                               nombre_tienda=nombre_tienda, 
                               slug_tienda=slug_tienda,
                               color_tienda=color_tienda,
                               tienda_completa=datos_tienda,
                               lista_productos=productos_tienda)
                               
    except mysql.connector.Error as err:
        return f""
        

# ==========================================
# AGREGAR PRODUCTO (CON IA)
# ==========================================
@app.route('/tienda//agregar', methods=['GET', 'POST'])
def agregar_producto(id_tienda):
    if not session.get('admin_logeado'):
        return redirect(url_for('login'))

    try:
        conexion = obtener_conexion()
        cursor = conexion.cursor(dictionary=True)

        cursor.execute("SELECT id_categoria, nombre_categoria FROM categorias WHERE id_tienda = %s", (id_tienda,))
        categorias_tienda = cursor.fetchall()

        if request.method == 'POST':
            nombre = request.form['nombre']
            precio = request.form['precio']
            categoria_form = request.form.get('categoria')
            categoria = int(categoria_form) if categoria_form else clasificar_producto(nombre, categorias_tienda)
            descripcion = request.form.get('descripcion') or generar_descripcion_ia(nombre)
            
            if 'imagen' not in request.files:
                cursor.close(); conexion.close()
                return "", 400
                
            archivo_foto = request.files['imagen']
            
            if archivo_foto.filename == '':
                cursor.close(); conexion.close()
                return...