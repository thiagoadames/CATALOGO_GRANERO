from flask import Flask, render_template, request, redirect, url_for, session
import mysql.connector
import os
import re 
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)

app.secret_key = "clave_secreta_super_segura_para_el_granero"

CARPETA_IMAGENES = os.path.join('static', 'imagenes')
app.config['UPLOAD_FOLDER'] = CARPETA_IMAGENES

def obtener_conexion():
    return mysql.connector.connect(
        host=os.environ.get("MYSQLHOST", "reseau.proxy.rlwy.net"),
        user=os.environ.get("MYSQLUSER", "root"),
        password=os.environ.get("MYSQLPASSWORD", "edkZloxlaigQCBmHyYkjHjKEPtaMQRbo"),
        database=os.environ.get("MYSQLDATABASE", "plataforma_catalogos"),
        port=int(os.environ.get("MYSQLPORT", 59970))
    )

@app.after_request
def añadir_headers_seguridad(response):
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['X-XSS-Protection'] = '1; mode=block'
    return response

@app.errorhandler(404)
def pagina_no_encontrada(e):
    return render_template('login.html', error="La página solicitada no existe."), 404

@app.errorhandler(500)
def error_interno_servidor(e):
    return "<h1>Error Interno del Servidor</h1>", 500

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
                return render_template('login.html', error='Usuario o contraseña incorrectos.')
        except mysql.connector.Error as err:
            return f"<h1>Error de base de datos en Login: {err}</h1>"
    return render_template('login.html', error=None)

@app.route('/recuperar-cuenta', methods=['GET', 'POST'])
def recuperar_cuenta():
    if request.method == 'POST':
        email_ingresado = request.form['email'].strip()
        try:
            conexion = obtener_conexion()
            cursor = conexion.cursor(dictionary=True)
            sql = "SELECT t.nombre_tienda, t.telefono_whatsapp, u.usuario FROM tiendas t JOIN usuarios u ON t.id_tienda = u.id_tienda WHERE t.email_recuperacion = %s"
            cursor.execute(sql, (email_ingresado,))
            resultado = cursor.fetchone()
            cursor.close()
            conexion.close()
            if resultado:
                mensaje = f"Hola, tu usuario para {resultado['nombre_tienda']} es: {resultado['usuario']}."
                link_whatsapp = f"https://wa.me/{resultado['telefono_whatsapp']}?text={mensaje}"
                return f"<h1>Éxito</h1><a href='{link_whatsapp}'>Enviar credenciales a WhatsApp</a>"
            else:
                return "<h1>Error</h1><p>No encontramos cuenta con ese correo.</p>"
        except mysql.connector.Error as err:
            return f"<h1>Error: {err}</h1>"
    return render_template('recuperar_cuenta.html')

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
            return "<h1>Error: Contraseña alfanumérica necesaria.</h1>"
        
        contrasena_encriptada = generate_password_hash(contrasena)
        url_logo_db = '/static/imagenes/default_logo.png'
        
        slug = re.sub(r'[\s-]+', '-', re.sub(r'[^a-z0-9\s-]', '', nombre_tienda.lower())).strip('-')
        whatsapp_final = f"57{raw_telefono}" if not raw_telefono.startswith('57') and len(raw_telefono) == 10 else raw_telefono

        try:
            conexion = obtener_conexion()
            cursor = conexion.cursor()
            
            # CORRECCIÓN: Se eliminó 'city' y se ajustó a 11 columnas para coincidir con tu BD
            sql_tienda = """INSERT INTO tiendas (nombre_tienda, slug, telefono, direccion, ciudad, telefono_whatsapp, url_logo, email_recuperacion, color_primario, tipo_negocio, configuracion_subcarpetas) 
                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"""
            
            valores_tienda = (nombre_tienda, slug, whatsapp_final, direccion, ciudad, whatsapp_final, url_logo_db, email_recuperacion, '#0056b3', 'General', 0)
            
            cursor.execute(sql_tienda, valores_tienda)
            nuevo_id_tienda = cursor.lastrowid
            
            sql_usuario = "INSERT INTO usuarios (usuario, contrasena, id_tienda) VALUES (%s, %s, %s)"
            cursor.execute(sql_usuario, (usuario, contrasena_encriptada, nuevo_id_tienda))
            
            conexion.commit()
            cursor.close()
            conexion.close()
            return redirect(url_for('login'))
        except mysql.connector.Error as err:
            return f"<h1>Error al registrar: {err}</h1>"
    return render_template('registrar_tienda.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/')
def inicio():
    if not session.get('admin_logeado'):
        return redirect(url_for('login'))
    return redirect(url_for('panel_administrador', id_tienda=session.get('id_tienda', 1)))

@app.route('/tienda/<int:id_tienda>/admin')
def panel_administrador(id_tienda):
    if not session.get('admin_logeado'): return redirect(url_for('login'))
    try:
        conexion = obtener_conexion()
        cursor = conexion.cursor(dictionary=True)
        cursor.execute("SELECT * FROM tiendas WHERE id_tienda = %s", (id_tienda,))
        datos_tienda = cursor.fetchone()
        cursor.execute("SELECT * FROM productos WHERE id_tienda = %s", (id_tienda,))
        productos = cursor.fetchall()
        cursor.close()
        conexion.close()
        return render_template('panel_admin.html', id_tienda=id_tienda, tienda_completa=datos_tienda, lista_productos=productos)
    except mysql.connector.Error as err:
        return f"<h1>Error: {err}</h1>"

@app.route('/tienda/<int:id_tienda>/agregar', methods=['GET', 'POST'])
def agregar_producto(id_tienda):
    if not session.get('admin_logeado'): return redirect(url_for('login'))
    if request.method == 'POST':
        nombre, precio, categoria, descripcion = request.form['nombre'], request.form['precio'], request.form['categoria'], request.form['descripcion']
        try:
            conexion = obtener_conexion()
            cursor = conexion.cursor()
            cursor.execute("INSERT INTO productos (id_tienda, nombre_producto, precio, descripcion, categoria) VALUES (%s, %s, %s, %s, %s)", 
                           (id_tienda, nombre, precio, descripcion, categoria))
            conexion.commit()
            cursor.close()
            conexion.close()
            return redirect(url_for('panel_administrador', id_tienda=id_tienda))
        except mysql.connector.Error as err:
            return f"<h1>Error: {err}</h1>"
    return render_template('agregar_producto.html', id_tienda=id_tienda)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 8080)))