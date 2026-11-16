# Hotel Ríos del Sur – Sistema de gestión hotelera

Prototipo en Django 5.2 + SQLite + Bootstrap 5: consulta de disponibilidad, reservas (incluye paquetes
combinados para grupos grandes), check-in/check-out y panel de recepción.

## Instalación (Python 3.10 o superior)

```bash
python -m venv venv
venv\Scripts\activate          
pip install -r requirements.txt
python manage.py migrate
python manage.py cargar_demo  
python manage.py runserver
```

Abrir http://127.0.0.1:8000/

## Credenciales de prueba (tras ejecutar `cargar_demo`)

| Rol | Usuario | Contraseña |
|---|---|---|
| Recepción (panel) | recepcion | Demo#2026 |
| Cliente | cliente1 / cliente2 / cliente3 | Demo#2026 |
| Administrador (/admin) | admin | (la definida al crear el superusuario) |

## Pruebas automatizadas

```bash
python manage.py test
```

## Variables de entorno (opcional, ver `.env.example`)

`DEBUG`, `SECRET_KEY` (obligatoria si `DEBUG=False`), `ALLOWED_HOSTS`.

## Base de datos

SQLite (`db.sqlite3`, incluida con datos de prueba). Tablas principales: Habitacion, Huesped, Reserva.
