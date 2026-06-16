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
        host="localhost",
        user="root",        
        password="1509",                # Tu contraseña configurada de MySQL
        database="plataforma_catalogos" # Base de datos real
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
                # Si se equivoca, recargamos el login con el mensaje de error
                return render_template('login.html', error="Usuario o contraseña incorrectos.")
                
        except mysql.connector.Error as err:
            return f"<h1>Error de base de datos en Login: {err}</h1>"
            
    # Si entra por GET, mostramos el formulario limpio sin errores
    return render_template('login.html', error=None)


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
        
        # Captura de datos de acceso
        usuario = request.form['usuario'].strip()
        contrasena = request.form['contrasena'].strip()
        
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
            
            # 1. Insertamos la nueva empresa con todas las columnas validadas de HeidiSQL
            sql_tienda = """INSERT INTO tiendas (nombre_tienda, slug, telefono, direccion, city) 
                            VALUES (%s, %s, %s, %s, %s)"""
            valores_tienda = (nombre_tienda, slug, whatsapp_final, direccion, ciudad)
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
            
            # Redireccionamos exitosamente al login para que el nuevo usuario estrene su cuenta
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
# PANEL DE ADMINISTRACIÓN (DASHBOARD CON DISEÑO DE TARJETAS CORREGIDO)
# =========================================================================
@app.route('/tienda/<int:id_tienda>/admin')
def panel_administrador(id_tienda):
    # FILTRO DE SEGURIDAD: Si no ha iniciado sesión, mándelo al login de una
    if not session.get('admin_logeado'):
        return redirect(url_for('login'))
        
    try:
        conexion = obtener_conexion()
        cursor = conexion.cursor()
        
        # 1. Traemos el nombre dinámico de la tienda usando la columna real 'nombre_tienda'
        cursor.execute("SELECT nombre_tienda FROM tiendas WHERE id_tienda = %s", (id_tienda,))
        datos_tienda = cursor.fetchone()
        nombre_tienda = datos_tienda[0] if datos_tienda else "Mi Granero Piloto"
        
        # 2. AJUSTE REQUERIDO: Traemos los campos en un orden explícito para que correspondan al HTML
        cursor.execute("""
            SELECT id_producto, nombre_producto, precio, categoria, descripcion, url_imagen, id_tienda 
            FROM productos 
            WHERE id_tienda = %s
        """, (id_tienda,))
        productos_tienda = cursor.fetchall()
        
        cursor.close()
        conexion.close()
        
        # Renderizamos el nuevo panel enviando los datos limpios
        return render_template('panel_admin.html', 
                               id_tienda=id_tienda, 
                               nombre_tienda=nombre_tienda, 
                               lista_productos=productos_tienda)
                               
    except mysql.connector.Error as err:
        return f"<h1>Error al cargar el panel de administración: {err}</h1>"


# ==========================================
# FORMULARIO AGREGAR PRODUCTO (PROTEGIDO)
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
            
            # EL ÚNICO CAMBIO: Agregamos el parámetro 'categoria' al final del INSERT y sus valores correspondientes
            sql = """INSERT INTO productos (id_tienda, nombre_producto, precio, descripcion, url_imagen, categoria) 
                     VALUES (%s, %s, %s, %s, %s, %s)"""
            valores = (id_tienda, nombre, precio, descripcion, url_imagen_db, categoria)
            
            cursor.execute(sql, valores)
            conexion.commit()  
            
            cursor.close()
            conexion.close()
            
            # Al agregar con éxito, regresa directo al panel de control
            return redirect(url_for('panel_administrador', id_tienda=id_tienda))
            
        except mysql.connector.Error as err:
            return f"<h1>Error al guardar en la base de datos: {err}</h1>"
            
    return render_template('agregar_producto.html', id_tienda=id_tienda)


# =========================================================================
# FASE 1 COMPLETADA: FORMULARIO ACTUALIZAR / EDITAR PRODUCTO (FOTO OPCIONAL)
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
            
            # Revisamos si el usuario subió una foto nueva
            archivo_foto = request.files.get('imagen')
            
            if archivo_foto and archivo_foto.filename != '':
                # Si subió foto nueva, la guardamos de una
                nombre_archivo_seguro = secure_filename(archivo_foto.filename)
                ruta_guardado = os.path.join(app.config['UPLOAD_FOLDER'], nombre_archivo_seguro)
                archivo_foto.save(ruta_guardado)
                url_imagen_db = f"/static/imagenes/{nombre_archivo_seguro}"
                
                # Consulta SQL actualizando la foto nueva
                sql_update = """UPDATE productos 
                                SET nombre_producto=%s, precio=%s, categoria=%s, descripcion=%s, url_imagen=%s 
                                WHERE id_producto=%s AND id_tienda=%s"""
                valores_update = (nombre, precio, categoria, descripcion, url_imagen_db, id_producto, id_tienda)
            else:
                # Si NO subió foto, actualizamos los datos manteniendo la foto vieja intacta
                sql_update = """UPDATE productos 
                                SET nombre_producto=%s, precio=%s, categoria=%s, descripcion=%s 
                                WHERE id_producto=%s AND id_tienda=%s"""
                valores_update = (nombre, precio, categoria, descripcion, id_producto, id_tienda)

            cursor.execute(sql_update, valores_update)
            conexion.commit()
            
            cursor.close()
            conexion.close()
            return redirect(url_for('panel_administrador', id_tienda=id_tienda))

        # Si entra por GET, traemos los datos actuales del producto para rellenar el formulario
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
# RUTA DETECTADA Y CORREGIDA: VISTA PÚBLICA DEL CLIENTE CON FILTRO Y BUSCADOR ACTIVO
# =========================================================================
@app.route('/tienda/<int:id_tienda>/catalogo')
def ver_catalogo(id_tienda):
    try:
        # CAPTURAMOS EL FILTRO DE CATEGORÍA Y EL TÉRMINO DE BÚSQUEDA POR TEXTO
        categoria_seleccionada = request.args.get('cat')
        termino_busqueda = request.args.get('q')
        
        # AGREGADO: Corrección para evitar que se muestre la palabra 'None' en el HTML
        if termino_busqueda is None:
            termino_busqueda = ""
        
        conexion = obtener_conexion()
        cursor = conexion.cursor()
        
        # 1. Recuperamos la información básica de la tienda (Nombre, WhatsApp, etc.)
        cursor.execute("SELECT nombre_tienda, telefono, ciudad FROM tiendas WHERE id_tienda = %s", (id_tienda,))
        datos_tienda = cursor.fetchone()
        
        if datos_tienda:
            nombre_tienda = datos_tienda[0]
            telefono_whatsapp = datos_tienda[1]
            ciudad_tienda = datos_tienda[2]
        else:
            nombre_tienda = "Mi Granero"
            telefono_whatsapp = "573000000000"
            ciudad_tienda = "Colombia"
            
        # 2. CONSULTA DINÁMICA CON FILTRO DE CATEGORÍAS O BUSCADOR POR NOMBRE/DESCRIPCIÓN
        if termino_busqueda:
            # Si se usa la barra de búsqueda, se filtra el catálogo aplicando el comodín LIKE seguro
            sql_productos = """
                SELECT id_producto, nombre_producto, precio, categoria, descripcion, url_imagen 
                FROM productos 
                WHERE id_tienda = %s AND (nombre_producto LIKE %s OR descripcion LIKE %s)
            """
            porcentaje_busqueda = f"%{termino_busqueda}%"
            cursor.execute(sql_productos, (id_tienda, porcentaje_busqueda, porcentaje_busqueda))
            
        elif categoria_seleccionada:
            # Filtro por categoría activa: Se ordenan las columnas exactamente como las procesa el HTML
            sql_productos = """
                SELECT id_producto, nombre_producto, precio, categoria, descripcion, url_imagen 
                FROM productos 
                WHERE id_tienda = %s AND categoria = %s
            """
            cursor.execute(sql_productos, (id_tienda, categoria_seleccionada))
        else:
            # Vista general: Se ordenan las columnas exactamente in the same orden estructural
            sql_productos = """
                SELECT id_producto, nombre_producto, precio, categoria, descripcion, url_imagen 
                FROM productos 
                WHERE id_tienda = %s
            """
            cursor.execute(sql_productos, (id_tienda,))
            
        productos_tienda = cursor.fetchall()
        
        cursor.close()
        conexion.close()
        
        # Renderiza tu archivo original con el diseño del carrito intacto
        return render_template('ver_catalogo.html', 
                               id_tienda=id_tienda, 
                               nombre_tienda=nombre_tienda,
                               telefono=telefono_whatsapp,
                               ciudad=ciudad_tienda,
                               lista_productos=productos_tienda,
                               categoria_actual=categoria_seleccionada,
                               busqueda_actual=termino_busqueda)
                               
    except mysql.connector.Error as err:
        return f"<h1>Error de base de datos en Catálogo: {err}</h1>"


# =========================================================================
# CONFIGURACIÓN DE ARRANQUE ROBUSTA (IP LOCAL FIJA CONTRA CONGELAMIENTO)
# =========================================================================
if __name__ == '__main__':
    # Usamos host='127.0.0.1' de forma obligatoria para evitar los bloqueos de puerto de Windows
    app.run(host='127.0.0.1', port=5000, debug=True)