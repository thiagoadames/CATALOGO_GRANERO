from flask import Flask, render_template, request, redirect, url_for, session
import sqlite3
import os
import re
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = "clave_secreta_super_segura_para_el_granero"

CARPETA_IMAGENES = os.path.join('static', 'imagenes')
app.config['UPLOAD_FOLDER'] = CARPETA_IMAGENES

# Conexión a SQLite
def obtener_conexion():
    conexion = sqlite3.connect('catalogo.db')
    conexion.row_factory = sqlite3.Row 
    return conexion

# Login modificado
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        usuario = request.form['usuario']
        contrasena = request.form['contrasena']
        conexion = obtener_conexion()
        cursor = conexion.cursor()
        cursor.execute("SELECT id_usuario, id_tienda FROM usuarios WHERE usuario = ? AND contrasena = ?", (usuario, contrasena))
        user = cursor.fetchone()
        conexion.close()
        if user:
            session['admin_logeado'] = True
            session['id_tienda'] = user['id_tienda']
            return redirect(url_for('panel_administrador', id_tienda=user['id_tienda']))
        return render_template('login.html', error="Usuario o contraseña incorrectos.")
    return render_template('login.html')

# Registro modificado (usando ? en lugar de %s)
@app.route('/registrar-tienda', methods=['GET', 'POST'])
def registrar_tienda():
    if request.method == 'POST':
        nombre = request.form['nombre_tienda']
        slug = re.sub(r'[^a-z0-9-]', '', nombre.lower().replace(' ', '-'))
        conexion = obtener_conexion()
        cursor = conexion.cursor()
        cursor.execute("INSERT INTO tiendas (nombre_tienda, slug, telefono, direccion, city) VALUES (?, ?, ?, ?, ?)", 
                       (nombre, slug, request.form['telefono'], request.form['direccion'], request.form['ciudad']))
        id_tienda = cursor.lastrowid
        cursor.execute("INSERT INTO usuarios (usuario, contrasena, id_tienda) VALUES (?, ?, ?)", 
                       (request.form['usuario'], request.form['contrasena'], id_tienda))
        conexion.commit()
        conexion.close()
        return redirect(url_for('login'))
    return render_template('registrar_tienda.html')

# Panel administrador (igual, pero con sintaxis SQLite)
@app.route('/tienda/<int:id_tienda>/admin')
def panel_administrador(id_tienda):
    if not session.get('admin_logeado'): return redirect(url_for('login'))
    conexion = obtener_conexion()
    cursor = conexion.cursor()
    cursor.execute("SELECT nombre_tienda FROM tiendas WHERE id_tienda = ?", (id_tienda,))
    nombre = cursor.fetchone()[0]
    cursor.execute("SELECT id_producto, nombre_producto, precio, categoria, descripcion, url_imagen FROM productos WHERE id_tienda = ?", (id_tienda,))
    productos = cursor.fetchall()
    conexion.close()
    return render_template('panel_admin.html', id_tienda=id_tienda, nombre_tienda=nombre, lista_productos=productos)

# Agregar producto
@app.route('/tienda/<int:id_tienda>/agregar', methods=['GET', 'POST'])
def agregar_producto(id_tienda):
    if request.method == 'POST':
        f = request.files['imagen']
        ruta = f"/static/imagenes/{secure_filename(f.filename)}"
        f.save(os.path.join(app.config['UPLOAD_FOLDER'], secure_filename(f.filename)))
        conexion = obtener_conexion()
        cursor = conexion.cursor()
        cursor.execute("INSERT INTO productos (id_tienda, nombre_producto, precio, descripcion, url_imagen, categoria) VALUES (?, ?, ?, ?, ?, ?)",
                       (id_tienda, request.form['nombre'], request.form['precio'], request.form['descripcion'], ruta, request.form['categoria']))
        conexion.commit()
        conexion.close()
        return redirect(url_for('panel_administrador', id_tienda=id_tienda))
    return render_template('agregar_producto.html', id_tienda=id_tienda)

@app.route('/')
def inicio(): return redirect(url_for('login'))

if __name__ == '__main__':
    app.run(debug=True)