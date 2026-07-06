from flask import Flask, render_template, request, redirect, url_for, session
import mysql.connector
import os
import re  # Librería necesaria para limpiar textos y armar el slug de la URL
from werkzeug.utils import secure_filename

app = Flask(__name__)

# =========================================================================
# CLAVE SECRETA: Necesaria para activar y encriptar las sesiones (session)
# =========================================================================
app.secret_key = "clave_secreta_super_segura_para_el_granero"

# ==========================================
# CONFIGURACIÓN DE CARPETA PARA SUBIR FOTOS
# ==========================================
CARPETA_IMAGENES = os.path.join('static', 'imagenes')
app.config['UPLOAD_FOLDER'] = CARPETA_IMAGENES

# ==========================================
# CONFIGURACIÓN DE LA BASE DE DATOS (HeidiSQL)
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
# CONTROL DE ACCESO (LOGIN INTELIGENTE DINÁMICO)
# =========================================================================
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        usuario_ingresado = request.form['usuario']
        contrasena_ingresada = request.form['contrasena']
        
        try:
            conexion = obtener_conexion()
            cursor = conexion.cursor()
            
            # Consultamos el usuario, la contraseña Y traemos el id_tienda asociado
            cursor.execute("SELECT id_usuario, id_tienda FROM usuarios WHERE usuario = %s AND contrasena = %s", 
                           (usuario_ingresado, contrasena_ingresada))
            usuario_encontrado = cursor.fetchone()
            
            cursor.close()
            conexion.close()
            
            if usuario_encontrado:
                # ¡Credenciales correctas! Guardamos la sesión en el servidor
                session['admin_logeado'] = True
                session['usuario_nombre'] = usuario_ingresado
                
                # Guardamos dinámicamente el id_tienda asignado a este administrador
                id_tienda_usuario = usuario_encontrado[1] if usuario_encontrado[1] else 1
                session['id_tienda'] = id_tienda_usuario
                
                # Mandamos directo al panel de administración de SU propia tienda
                return redirect(url_for('panel_administrador', id_tienda=id_tienda_usuario))
            else:
                # MODIFICACIÓN: Mensaje con enlace para recuperar
                mensaje_error = 'Usuario o contraseña incorrectos. <a href="/recuperar-cuenta">¿Olvidaste tus datos?</a>'
                return render_template('login.html', error=mensaje_error)
                
        except mysql.connector.Error as err:
            return f"<h1>Error de base de datos en Login: {err}</h1>"
            
    # Si entra por GET, mostramos el formulario limpio sin errores
    return render_template('login.html', error=None)


# =========================================================================
# RUTA PARA RECUPERACIÓN DE CUENTA (INTEGRACIÓN WHATSAPP)
# =========================================================================
@app.route('/recuperar-cuenta', methods=['GET', 'POST'])
def recuperar_cuenta():
    if request.method == 'POST':
        email_ingresado = request.form['email'].strip()
        
        try:
            conexion = obtener_conexion()
            cursor = conexion.cursor(dictionary=True)
            
            # Buscamos la tienda y las credenciales del usuario usando el email
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
                # Armamos el mensaje para WhatsApp
                mensaje = f"Hola, tus credenciales para {resultado['nombre_tienda']} son: Usuario: {resultado['usuario']}, Contraseña: {resultado['contrasena']}"
                link_whatsapp = f"https://wa.me/{resultado['telefono_whatsapp']}?text={mensaje}"
                
                return f"""
                <h1>¡Éxito!</h1>
                <p>Encontramos tu cuenta.</p>
                <a href='{link_whatsapp}' target='_blank' style='padding: 15px; background: #25D366; color: white; text-decoration: none; border-radius: 5px;'>
                    Enviar credenciales a mi WhatsApp
                </a>
                <br><br><a href='/login'>Volver al login</a>
                """
            else:
                return "<h1>Error</h1><p>No encontramos ninguna empresa registrada con ese correo.</p><a href='/recuperar-cuenta'>Intentar de nuevo</a>"
        except mysql.connector.Error as err:
            return f"<h1>Error de base de datos: {err}</h1>"
            
    return render_template('recuperar_cuenta.html')


# =========================================================================
# REGISTRO AUTOMATIZADO DE NUEVAS EMPRESAS / TIENDAS (CON SOPORTE SLUG)
# =========================================================================
@app.route('/registrar-tienda', methods=['GET', 'POST'])
def registrar_tienda():
    if request.method == 'POST':
        # Captura de datos del negocio
        nombre_tienda = request.form['nombre_tienda'].strip()
        raw_telefono = request.form['telefono'].strip()
        direccion = request.form['direccion'].strip()
        ciudad = request.form['ciudad'].strip()
        # Captura del email de recuperación
        email_recuperacion = request.form['email_recuperacion'].strip()
        
        # Captura de datos de acceso
        usuario = request.form['usuario'].strip()
        contrasena = request.form['contrasena'].strip()
        
        # Gestión del logo
        url_logo_db = '/static/imagenes/default_logo.png'
        if 'logo' in request.files:
            archivo_logo = request.files['logo']
            if archivo_logo.filename != '':
                nombre_archivo_seguro = secure_filename(archivo_logo.filename)
                ruta_guardado = os.path.join(app.config['UPLOAD_FOLDER'], nombre_archivo_seguro)
                archivo_logo.save(ruta_guardado)
                url_logo_db = f"/static/imagenes/{nombre_archivo_seguro}"
        
        # GENERACIÓN DEL SLUG AUTOMÁTICO:
        slug = nombre_tienda.lower()
        slug = re.sub(r'[^a-z0-9\s-]', '', slug)
        slug = re.sub(r'[\s-]+', '-', slug).strip('-')
        
        # Limpieza automática del formato de WhatsApp para Colombia (57)
        if not raw_telefono.startswith('57') and len(raw_telefono) == 10:
            whatsapp_final = f"57{raw_telefono}"
        else:
            whatsapp_final = raw_telefono

        try:
            conexion = obtener_conexion()
            cursor = conexion.cursor()
            
            # 1. Insertamos la nueva empresa con el logo y email_recuperacion
            sql_tienda = """INSERT INTO tiendas (nombre_tienda, slug, telefono, direccion, ciudad, telefono_whatsapp, url_logo, email_recuperacion) 
                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)"""
            valores_tienda = (nombre_tienda, slug, whatsapp_final, direccion, ciudad, whatsapp_final, url_logo_db, email_recuperacion)
            cursor.execute(sql_tienda, valores_tienda)
            
            # Obtenemos el ID asignado automáticamente a esta nueva tienda
            nuevo_id_tienda = cursor.lastrowid
            
            # 2. Insertamos el nuevo dueño en la tabla 'usuarios' vinculándolo a su tienda
            sql_usuario = """INSERT INTO usuarios (usuario, contrasena, id_tienda) 
                             VALUES (%s, %s, %s)"""
            valores_usuario = (usuario, contrasena, nuevo_id_tienda)
            cursor.execute(sql_usuario, valores_usuario)
            
            # Confirmamos la transacción en la Base de Datos
            conexion.commit()
            
            cursor.close()
            conexion.close()
            
            # Redireccionamos exitosamente al login
            return redirect(url_for('login'))
            
        except mysql.connector.Error as err:
            return f"<h1>Error al registrar la nueva empresa: {err}</h1>"

    # Si se accede por GET (navegador), se muestra el formulario visual diseñado
    return render_template('registrar_tienda.html')


# =========================================================================
# CERRAR SESIÓN (LOGOUT)
# =========================================================================
@app.route('/logout')
def logout():
    session.clear() # Borra la memoria de la sesión por seguridad
    return redirect(url_for('login'))


# =========================================================================
# RUTA RAÍZ REDIRECCIONADA: ENTRAR A LA PÁGINA LIMPIA DE UNA
# =========================================================================
@app.route('/')
def inicio():
    # Si el administrador NO ha iniciado sesión, lo manda directo al Login automáticamente
    if not session.get('admin_logeado'):
        return redirect(url_for('login'))
    
    # Si YA inició sesión, recupera el id de su tienda de la memoria y lo redirige a su panel
    id_tienda_usuario = session.get('id_tienda', 1)
    return redirect(url_for('panel_administrador', id_tienda=id_tienda_usuario))


# =========================================================================
# PANEL DE ADMINISTRACIÓN
# =========================================================================
@app.route('/tienda/<int:id_tienda>/admin')
def panel_administrador(id_tienda):
    if not session.get('admin_logeado'):
        return redirect(url_for('login'))
        
    try:
        conexion = obtener_conexion()
        cursor = conexion.cursor()
        
        cursor.execute("SELECT nombre_tienda FROM tiendas WHERE id_tienda = %s", (id_tienda,))
        datos_tienda = cursor.fetchone()
        nombre_tienda = datos_tienda[0] if datos_tienda else "Mi Granero Piloto"
        
        cursor.execute("""
            SELECT id_producto, nombre_producto, precio, categoria, descripcion, url_imagen, id_tienda 
            FROM productos 
            WHERE id_tienda = %s
        """, (id_tienda,))
        productos_tienda = cursor.fetchall()
        
        cursor.close()
        conexion.close()
        
        return render_template('panel_admin.html', 
                               id_tienda=id_tienda, 
                               nombre_tienda=nombre_tienda, 
                               lista_productos=productos_tienda)
                               
    except mysql.connector.Error as err:
        return f"<h1>Error al cargar el panel de administración: {err}</h1>"
        

# ==========================================
# FORMULARIO AGREGAR PRODUCTO
# ==========================================
@app.route('/tienda/<int:id_tienda>/agregar', methods=['GET', 'POST'])
def agregar_producto(id_tienda):
    if not session.get('admin_logeado'):
        return redirect(url_for('login'))

    if request.method == 'POST':
        nombre = request.form['nombre']
        precio = request.form['precio']
        categoria = request.form['categoria']  
        descripcion = request.form['descripcion']
        
        if 'imagen' not in request.files:
            return "<h1>Error: No se detectó el campo de imagen en el formulario.</h1>", 400
            
        archivo_foto = request.files['imagen']
        
        if archivo_foto.filename == '':
            return "<h1>Error: No seleccionaste ninguna foto para subir.</h1>", 400
            
        if archivo_foto:
            nombre_archivo_seguro = secure_filename(archivo_foto.filename)
            ruta_guardado = os.path.join(app.config['UPLOAD_FOLDER'], nombre_archivo_seguro)
            archivo_foto.save(ruta_guardado)
            url_imagen_db = f"/static/imagenes/{nombre_archivo_seguro}"
        
        try:
            conexion = obtener_conexion()
            cursor = conexion.cursor()
            
            sql = """INSERT INTO productos (id_tienda, nombre_producto, precio, descripcion, url_imagen, categoria) 
                      VALUES (%s, %s, %s, %s, %s, %s)"""
            valores = (id_tienda, nombre, precio, descripcion, url_imagen_db, categoria)
            
            cursor.execute(sql, valores)
            conexion.commit()  
            
            cursor.close()
            conexion.close()
            
            return redirect(url_for('panel_administrador', id_tienda=id_tienda))
            
        except mysql.connector.Error as err:
            return f"<h1>Error al guardar en la base de datos: {err}</h1>"
            
    return render_template('agregar_producto.html', id_tienda=id_tienda)


# =========================================================================
# EDITAR PRODUCTO
# =========================================================================
@app.route('/tienda/<int:id_tienda>/editar/<int:id_producto>', methods=['GET', 'POST'])
def editar_producto(id_tienda, id_producto):
    if not session.get('admin_logeado'):
        return redirect(url_for('login'))

    try:
        conexion = obtener_conexion()
        cursor = conexion.cursor()

        if request.method == 'POST':
            nombre = request.form['nombre']
            precio = request.form['precio']
            categoria = request.form['categoria']
            descripcion = request.form['descripcion']
            
            archivo_foto = request.files.get('imagen')
            
            if archivo_foto and archivo_foto.filename != '':
                nombre_archivo_seguro = secure_filename(archivo_foto.filename)
                ruta_guardado = os.path.join(app.config['UPLOAD_FOLDER'], nombre_archivo_seguro)
                archivo_foto.save(ruta_guardado)
                url_imagen_db = f"/static/imagenes/{nombre_archivo_seguro}"
                
                sql_update = """UPDATE productos 
                                SET nombre_producto=%s, precio=%s, categoria=%s, descripcion=%s, url_imagen=%s 
                                WHERE id_producto=%s AND id_tienda=%s"""
                valores_update = (nombre, precio, categoria, descripcion, url_imagen_db, id_producto, id_tienda)
            else:
                sql_update = """UPDATE productos 
                                SET nombre_producto=%s, precio=%s, categoria=%s, descripcion=%s 
                                WHERE id_producto=%s AND id_tienda=%s"""
                valores_update = (nombre, precio, categoria, descripcion, id_producto, id_tienda)

            cursor.execute(sql_update, valores_update)
            conexion.commit()
            
            cursor.close()
            conexion.close()
            return redirect(url_for('panel_administrador', id_tienda=id_tienda))

        cursor.execute("""SELECT id_producto, nombre_producto, precio, categoria, descripcion, url_imagen 
                          FROM productos WHERE id_producto = %s AND id_tienda = %s""", (id_producto, id_tienda))
        producto_seleccionado = cursor.fetchone()
        
        cursor.close()
        conexion.close()

        if not producto_seleccionado:
            return "<h1>Error: Producto no encontrado.</h1>", 404

        return render_template('editar_producto.html', id_tienda=id_tienda, producto=producto_seleccionado)

    except mysql.connector.Error as err:
        return f"<h1>Error en el proceso de edición: {err}</h1>"


# =========================================================================
# VISTA PÚBLICA
# =========================================================================
@app.route('/tienda/<int:id_tienda>/catalogo')
def ver_catalogo(id_tienda):
    try:
        categoria_seleccionada = request.args.get('cat')
        termino_busqueda = request.args.get('q')
        
        if termino_busqueda is None:
            termino_busqueda = ""
        
        conexion = obtener_conexion()
        cursor = conexion.cursor()
        
        cursor.execute("SELECT nombre_tienda, telefono, ciudad, url_logo FROM tiendas WHERE id_tienda = %s", (id_tienda,))
        datos_tienda = cursor.fetchone()
        
        if datos_tienda:
            nombre_tienda = datos_tienda[0]
            telefono_whatsapp = datos_tienda[1]
            ciudad_tienda = datos_tienda[2]
            url_logo = datos_tienda[3]
        else:
            nombre_tienda = "Mi Granero"
            telefono_whatsapp = "573000000000"
            ciudad_tienda = "Colombia"
            url_logo = '/static/imagenes/default_logo.png'
            
        if termino_busqueda:
            sql_productos = """
                SELECT id_producto, nombre_producto, precio, categoria, descripcion, url_imagen 
                FROM productos 
                WHERE id_tienda = %s AND (nombre_producto LIKE %s OR descripcion LIKE %s)
            """
            porcentaje_busqueda = f"%{termino_busqueda}%"
            cursor.execute(sql_productos, (id_tienda, porcentaje_busqueda, porcentaje_busqueda))
            
        elif categoria_seleccionada:
            sql_productos = """
                SELECT id_producto, nombre_producto, precio, categoria, descripcion, url_imagen 
                FROM productos 
                WHERE id_tienda = %s AND categoria = %s
            """
            cursor.execute(sql_productos, (id_tienda, categoria_seleccionada))
        else:
            sql_productos = """
                SELECT id_producto, nombre_producto, precio, categoria, descripcion, url_imagen 
                FROM productos 
                WHERE id_tienda = %s
            """
            cursor.execute(sql_productos, (id_tienda,))
            
        productos_tienda = cursor.fetchall()
        
        cursor.close()
        conexion.close()
        
        return render_template('ver_catalogo.html', 
                               id_tienda=id_tienda, 
                               nombre_tienda=nombre_tienda,
                               telefono=telefono_whatsapp,
                               ciudad=ciudad_tienda,
                               url_logo=url_logo,
                               lista_productos=productos_tienda,
                               categoria_actual=categoria_seleccionada,
                               busqueda_actual=termino_busqueda)
                               
    except mysql.connector.Error as err:
        return f"<h1>Error de base de datos en Catálogo: {err}</h1>"

# =========================================================================
# NUEVA RUTA: CAMBIAR CONTRASEÑA
# =========================================================================
@app.route('/tienda/<int:id_tienda>/cambiar-clave', methods=['GET', 'POST'])
def cambiar_clave(id_tienda):
    if not session.get('admin_logeado'):
        return redirect(url_for('login'))

    if request.method == 'POST':
        nueva_clave = request.form['nueva_clave']
        
        try:
            conexion = obtener_conexion()
            cursor = conexion.cursor()
            
            sql = "UPDATE usuarios SET contrasena = %s WHERE id_tienda = %s"
            cursor.execute(sql, (nueva_clave, id_tienda))
            conexion.commit()
            
            cursor.close()
            conexion.close()
            
            return "<h1>Contraseña actualizada con éxito</h1><a href='/'>Volver al panel</a>"
        except mysql.connector.Error as err:
            return f"<h1>Error al actualizar la contraseña: {err}</h1>"
        
    return render_template('cambiar_clave.html', id_tienda=id_tienda)


if __name__ == '__main__':
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)