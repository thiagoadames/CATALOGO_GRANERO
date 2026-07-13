from flask import Flask, render_template, request, redirect, url_for, session
import mysql.connector
import os
import re  # Librería necesaria para limpiar textos y armar el slug de la URL
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash

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
# MIDDLEWARE DE SEGURIDAD REFORZADA (HEADERS GLOBALES)
# =========================================================================
@app.after_request
def añadir_headers_seguridad(response):
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['X-XSS-Protection'] = '1; mode=block'
    return response


# =========================================================================
# MANEJO GLOBAL DE ERRORES AMIGABLES
# =========================================================================
@app.errorhandler(404)
def pagina_no_encontrada(e):
    return render_template('login.html', error="La página solicitada no existe o la URL cambió. Por favor inicia sesión."), 404

@app.errorhandler(500)
def error_interno_servidor(e):
    return "<h1>Error Interno del Servidor</h1><p>Ocurrió un inconveniente con los servicios. Inténtalo de nuevo más tarde.</p>", 500


# =========================================================================
# CONTROL DE ACCESO (LOGIN INTELIGENTE DINÁMICO CON VERIFICACIÓN DE HASH)
# =========================================================================
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        usuario_ingresado = request.form['usuario']
        contrasena_ingresada = request.form['contrasena']
        
        # Validación alfanumérica en el servidor
        if not re.match(r'^[A-Za-z0-9]+$', contrasena_ingresada):
            return render_template('login.html', error="La contraseña solo debe contener letras y números.")
        
        try:
            conexion = obtener_conexion()
            cursor = conexion.cursor(dictionary=True)
            
            # Consultamos el usuario por su nombre para obtener su hash de contraseña y su id_tienda
            cursor.execute("SELECT id_usuario, contrasena, id_tienda FROM usuarios WHERE usuario = %s", (usuario_ingresado,))
            usuario_encontrado = cursor.fetchone()
            
            cursor.close()
            conexion.close()
            
            # Verificamos si el usuario existe y si el hash de la contraseña coincide
            if usuario_encontrado and check_password_hash(usuario_encontrado['contrasena'], contrasena_ingresada):
                # ¡Credenciales correctas! Guardamos la sesión en el servidor
                session['admin_logeado'] = True
                session['usuario_nombre'] = usuario_ingresado
                
                # Guardamos dinámicamente el id_tienda asignado a este administrador
                id_tienda_usuario = usuario_encontrado['id_tienda'] if usuario_encontrado['id_tienda'] else 1
                session['id_tienda'] = id_tienda_usuario
                
                # Mandamos directo al panel de administración de SU propia tienda
                return redirect(url_for('panel_administrador', id_tienda=id_tienda_usuario))
            else:
                # Mensaje con enlace para recuperar
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
                # Nota: Al usar Hashing, el mensaje de WhatsApp enviará un recordatorio indicando que la clave está encriptada
                # Por seguridad, lo ideal en producción es dirigir al usuario a cambiar-clave, pero mantenemos tu lógica de flujo:
                mensaje = f"Hola, tu usuario para {resultado['nombre_tienda']} es: {resultado['usuario']}. Tu contraseña está protegida por seguridad, si no la recuerdas solicítale al administrador restablecerla o usa el panel."
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
# REGISTRO AUTOMATIZADO CON ENCRIPTACIÓN DE CONTRASEÑA (HASH)
# =========================================================================
@app.route('/registrar-tienda', methods=['GET', 'POST'])
def registrar_tienda():
    if request.method == 'POST':
        # Captura de datos del negocio
        nombre_tienda = request.form['nombre_tienda'].strip()
        raw_telefono = request.form['telefono'].strip()
        direccion = request.form['direccion'].strip()
        ciudad = request.form['ciudad'].strip()
        email_recuperacion = request.form['email_recuperacion'].strip()
        
        # Captura de datos de acceso
        usuario = request.form['usuario'].strip()
        contrasena = request.form['contrasena'].strip()

        # Validación alfanumérica en el servidor
        if not re.match(r'^[A-Za-z0-9]+$', contrasena):
            return "<h1>Error: La contraseña debe ser alfanumérica.</h1><a href='/registrar-tienda'>Volver</a>"
        
        # Generamos el hash seguro de la contraseña antes de guardarla
        contrasena_encriptada = generate_password_hash(contrasena)
        
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
            
            # 1. Insertamos la nueva empresa con el logo y email_recuperacion (Y valores por defecto del nuevo menú)
            sql_tienda = """INSERT INTO tiendas (nombre_tienda, slug, telefono, direccion, city, ciudad, telefono_whatsapp, url_logo, email_recuperacion, color_primario, tipo_negocio, configuracion_subcarpetas) 
                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, '#0056b3', 'General', 0)"""
            valores_tienda = (nombre_tienda, slug, whatsapp_final, direccion, ciudad, whatsapp_final, url_logo_db, email_recuperacion)
            cursor.execute(sql_tienda, valores_tienda)
            
            # Obtenemos el ID asignado automáticamente a esta nueva tienda
            nuevo_id_tienda = cursor.lastrowid
            
            # 2. Insertamos el nuevo dueño en la tabla 'usuarios' guardando la contraseña encriptada
            sql_usuario = """INSERT INTO usuarios (usuario, contrasena, id_tienda) 
                             VALUES (%s, %s, %s)"""
            valores_usuario = (usuario, contrasena_encriptada, nuevo_id_tienda)
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
# PANEL DE ADMINISTRACIÓN (ACTUALIZADO CON DATOS E HIGHLIGHTS DEL MENÚ)
# =========================================================================
@app.route('/tienda/<int:id_tienda>/admin')
def panel_administrador(id_tienda):
    if not session.get('admin_logeado'):
        return redirect(url_for('login'))
        
    try:
        conexion = obtener_conexion()
        cursor = conexion.cursor(dictionary=True)
        
        # Recuperamos la información completa de la tienda para usarla en el menú dinámico del panel
        cursor.execute("SELECT * FROM tiendas WHERE id_tienda = %s", (id_tienda,))
        datos_tienda = cursor.fetchone()
        
        nombre_tienda = datos_tienda['nombre_tienda'] if datos_tienda else "Mi Granero Piloto"
        slug_tienda = datos_tienda['slug'] if datos_tienda else "default-slug"
        color_tienda = datos_tienda.get('color_primario', '#0056b3') if datos_tienda else '#0056b3'
        
        # Ejecutamos búsqueda limpia de productos vinculados
        cursor.execute("""
            SELECT id_producto, nombre_producto, precio, categoria, descripcion, url_imagen, id_tienda 
            FROM productos 
            WHERE id_tienda = %s
        """, (id_tienda,))
        productos_tienda = cursor.fetchall()
        
        cursor.close()
        conexion.close()
        
        # Pasamos los nuevos campos para renderizar los accesos en el menú interactivo
        return render_template('panel_admin.html', 
                               id_tienda=id_tienda, 
                               nombre_tienda=nombre_tienda, 
                               slug_tienda=slug_tienda,
                               color_tienda=color_tienda,
                               tienda_completa=datos_tienda,
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
        cursor = conexion.cursor(dictionary=True)

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
# VISTA PÚBLICA (ADAPTADA CON DETALLES DE COLORES Y TIPO DE NEGOCIO DESDE BD)
# =========================================================================
@app.route('/tienda/<int:id_tienda>/catalogo')
def ver_catalogo(id_tienda):
    try:
        categoria_seleccionada = request.args.get('cat')
        termino_busqueda = request.args.get('q')
        
        if termino_busqueda is None:
            termino_busqueda = ""
        
        conexion = obtener_conexion()
        cursor = conexion.cursor(dictionary=True)
        
        cursor.execute("SELECT nombre_tienda, telefono, ciudad, url_logo, color_primario, tipo_negocio, configuracion_subcarpetas FROM tiendas WHERE id_tienda = %s", (id_tienda,))
        datos_tienda = cursor.fetchone()
        
        if datos_tienda:
            nombre_tienda = datos_tienda['nombre_tienda']
            telefono_whatsapp = datos_tienda['telefono']
            ciudad_tienda = datos_tienda['ciudad']
            url_logo = datos_tienda['url_logo']
            color_primario = datos_tienda.get('color_primario', '#0056b3')
            tipo_negocio = datos_tienda.get('tipo_negocio', 'General')
        else:
            nombre_tienda = "Mi Granero"
            telefono_whatsapp = "573000000000"
            ciudad_tienda = "Colombia"
            url_logo = '/static/imagenes/default_logo.png'
            color_primario = '#0056b3'
            tipo_negocio = 'General'
            
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
                               color_primario=color_primario,
                               tipo_negocio=tipo_negocio,
                               lista_productos=productos_tienda,
                               categoria_actual=categoria_seleccionada,
                               busqueda_actual=termino_busqueda)
                               
    except mysql.connector.Error as err:
        return f"<h1>Error de base de datos en Catálogo: {err}</h1>"


# =========================================================================
# ACCESO DIRECTO POR LINK DE SLUG (IDENTIFICADOR EXCLUSIVO DE CATÁLOGO)
# =========================================================================
@app.route('/c/<string:slug_tienda>')
def ver_catalogo_por_slug(slug_tienda):
    try:
        conexion = obtener_conexion()
        cursor = conexion.cursor(dictionary=True)
        cursor.execute("SELECT id_tienda FROM tiendas WHERE slug = %s", (slug_tienda.strip().lower(),))
        tienda_encontrada = cursor.fetchone()
        cursor.close()
        conexion.close()
        
        if tienda_encontrada:
            # Redirigimos internamente usando la lógica limpia de id_tienda
            return redirect(url_for('ver_catalogo', id_tienda=tienda_encontrada['id_tienda'], **request.args))
        else:
            return "<h1>Catálogo no encontrado</h1><p>El enlace ingresado no corresponde a ninguna tienda registrada.</p><a href='/login'>Ir al acceso</a>", 404
    except Exception as e:
        return f"<h1>Error al procesar el enlace de catálogo: {e}</h1>", 500


# =========================================================================
# RUTA: MENÚ DE CONFIGURACIÓN DE LA TIENDA (COLORES, SLUG, TIPO NEGOCIO)
# =========================================================================
@app.route('/tienda/<int:id_tienda>/configuracion', methods=['GET', 'POST'])
def configurar_tienda(id_tienda):
    if not session.get('admin_logeado'):
        return redirect(url_for('login'))
        
    try:
        conexion = obtener_conexion()
        cursor = conexion.cursor(dictionary=True)
        
        if request.method == 'POST':
            color_ingresado = request.form['color_primario'].strip()
            tipo_negocio = request.form['tipo_negocio'].strip()
            subcarpetas = 1 if 'subcarpetas' in request.form else 0
            slug_ingresado = request.form['slug'].strip().lower()
            
            # 1. Validación de formato de color Hexadecimal (#RRGGBB)
            if not re.match(r'^#[A-Fa-f0-9]{6}$', color_ingresado):
                cursor.close(); conexion.close()
                return "<h1>Error: Formato de color inválido. Debe ser un formato Hexadecimal (#0056b3).</h1><a href='javascript:history.back()'>Volver</a>", 400
            
            # 2. Validación de caracteres en el slug
            slug_ingresado = re.sub(r'[^a-z0-9\s-]', '', slug_ingresado)
            slug_ingresado = re.sub(r'[\s-]+', '-', slug_ingresado).strip('-')
            
            if not slug_ingresado:
                cursor.close(); conexion.close()
                return "<h1>Error: El slug asignado no es válido.</h1><a href='javascript:history.back()'>Volver</a>", 400
                
            # 3. Validación de unicidad de Slug (Para no duplicar el enlace dinámico de otro cliente)
            cursor.execute("SELECT id_tienda FROM tiendas WHERE slug = %s AND id_tienda != %s", (slug_ingresado, id_tienda))
            conflicto_slug = cursor.fetchone()
            
            if conflicto_slug:
                cursor.close(); conexion.close()
                return "<h1>Error: Este nombre de enlace ya está siendo utilizado por otra tienda. Elige uno diferente.</h1><a href='javascript:history.back()'>Volver</a>", 400
            
            # 4. Actualización limpia de parámetros en la base de datos
            sql_update = """
                UPDATE tiendas 
                SET color_primario = %s, tipo_negocio = %s, configuracion_subcarpetas = %s, slug = %s 
                WHERE id_tienda = %s
            """
            cursor.execute(sql_update, (color_ingresado, tipo_negocio, subcarpetas, slug_ingresado, id_tienda))
            conexion.commit()
            
            cursor.close()
            conexion.close()
            return redirect(url_for('panel_administrador', id_tienda=id_tienda))
            
        # Petición GET: Recuperar datos para precargar los inputs en el menú desplegable/vista
        cursor.execute("SELECT * FROM tiendas WHERE id_tienda = %s", (id_tienda,))
        tienda_actual = cursor.fetchone()
        cursor.close()
        conexion.close()
        
        return render_template('configuracion.html', id_tienda=id_tienda, tienda=tienda_actual)
        
    except mysql.connector.Error as err:
        return f"<h1>Error en el módulo de configuración: {err}</h1>"


# =========================================================================
# RUTA: CAMBIAR CONTRASEÑA (CON BLINDAJE Y ENCRIPTACIÓN HASH)
# =========================================================================
@app.route('/tienda/<int:id_tienda>/cambiar-clave', methods=['GET', 'POST'])
def cambiar_clave(id_tienda):
    if not session.get('admin_logeado'):
        return redirect(url_for('login'))

    if request.method == 'POST':
        nueva_clave = request.form['nueva_clave']
        
        # Validación alfanumérica en el servidor
        if not re.match(r'^[A-Za-z0-9]+$', nueva_clave):
            return "<h1>Error: La contraseña solo puede contener letras y números, sin espacios ni caracteres especiales.</h1><a href='javascript:history.back()'>Volver atrás</a>", 400
        
        # Generamos el hash seguro de la nueva contraseña
        nueva_clave_encriptada = generate_password_hash(nueva_clave)
        
        try:
            conexion = obtener_conexion()
            cursor = conexion.cursor()
            
            # Actualizamos la base de datos con la contraseña encriptada
            sql = "UPDATE usuarios SET contrasena = %s WHERE id_tienda = %s"
            cursor.execute(sql, (nueva_clave_encriptada, id_tienda))
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