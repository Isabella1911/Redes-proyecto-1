# Guía de conexiones MCP

Procedimiento para cada tipo de conexión del proyecto: cómo se configura, cómo
se levanta y cómo se verifica **antes** de depurar a través del chatbot.

Todos los comandos se corren desde la raíz del repo. Si activás el entorno
virtual (`.venv\Scripts\activate`) podés usar los nombres cortos
(`flora-mcp`, `flora-assistant`, `flora-assistant-web`); si no, antepené
`.venv\Scripts\python.exe -m` como se muestra abajo.

---

## Los seis tipos de conexión

| # | Tipo | Transporte | Quién lo arranca | Dónde se configura |
|---|------|-----------|------------------|--------------------|
| 1 | Servidores oficiales (Filesystem, Git) | stdio | el host, como subproceso | `stdio_servers()` en `config.py` |
| 2 | Tu servidor propio (`flora`) | stdio | el host, como subproceso | `stdio_servers()` en `config.py` |
| 3 | Servidores de compañeros, misma máquina | stdio | el host, como subproceso | `stdio_servers()` en `config.py` |
| 4 | Tu servidor consumido por otros | HTTP | **vos, a mano** | `--http --host 0.0.0.0` |
| 5 | Servidores de otros, por red | HTTP | el dueño, en su máquina | `FLORA_REMOTE_MCP` en `.env` |
| 6 | Tu servidor en la nube (Cloudflare) | HTTPS | Cloudflare, siempre encendido | `FLORA_REMOTE_MCP` en `.env` |

Los tipos 1-3 no requieren red: el host lanza el proceso y le habla por stdin y
stdout. Los tipos 4, 5 y 6 son los que cruzan la red.

---

## Preparación (una sola vez)

```bash
uv venv .venv
uv pip install -e .
```

```powershell
Copy-Item .env.example .env
```

Editá `.env` y poné tu `ANTHROPIC_API_KEY` y tu `PLANTNET_API_KEY`.

Verificá que todo está sano:

```bash
.venv/Scripts/python.exe -m pytest -q -m "not network"
```

---

## Tipo 1 y 2 — Servidores locales por stdio

No hay nada que arrancar: el host lanza `npx`, `uvx` y Python como subprocesos
cuando inicia. Solo necesitás Node.js y `uv` instalados.

**Levantar el chatbot:**

```bash
.venv/Scripts/python.exe -m flora_assistant.main
```

**Verificar:** al arrancar imprime qué conectó.

```
Servidores conectados (6): filesystem, git, flora, docfinder, library, flora-remoto
Herramientas disponibles: 41
```

Si alguno falta aparece con `[!]` y el motivo.

---

## Tipo 3 — Servidores de compañeros en tu máquina

Se clonan como carpetas hermanas y cada uno se instala según **su propio
README**. Las rutas están en `stdio_servers()` dentro de
[`src/flora_assistant/config.py`](src/flora_assistant/config.py).

| Servidor | Ruta esperada | Requiere |
|----------|---------------|----------|
| `docfinder` | `../Proyecto1_Redes/CC3067-Proyecto1-docfinder` | `npm install` en ese repo |
| `library` | `../Proyecto1_Redes/CC3067-library-mcp` | su `.venv` + MySQL corriendo |

El de biblioteca necesita su base de datos levantada, o conecta pero sus
herramientas devuelven error:

```bash
docker compose -f ../Proyecto1_Redes/CC3067-library-mcp/docker-compose.yml up -d
```

Para agregar el servidor de otro compañero, copiá una entrada en
`stdio_servers()` con su comando y su `cwd`. Si no lo tenés clonado, el host lo
reporta como caído y sigue con el resto — no hace falta borrar la entrada.

---

## Tipo 4 — Que otros consuman tu servidor

### Paso 1: permitir el puerto en el firewall (una sola vez)

PowerShell **como administrador**:

```powershell
New-NetFirewallRule -DisplayName "flora-mcp" -Direction Inbound -Protocol TCP -LocalPort 8100 -Action Allow -Profile Private
```

### Paso 2: apagar la VPN

Un cliente de VPN activo (NordVPN y similares) normalmente bloquea el tráfico
entre equipos de la misma LAN. Apagalo antes de la demo.

### Paso 3: levantar el servidor en una terminal aparte

```bash
cd ../Proyecto-Redes-Isa/flora-remote-mcp && .venv/Scripts/python.exe -m flora_mcp.server --http --host 0.0.0.0 --port 8100
```

`0.0.0.0` acepta conexiones de la red. El servidor **no tiene autenticación**,
así que usalo solo en una red en la que confíes.

Queda ocupando esa terminal. `Ctrl+C` para pararlo.

### Paso 4: averiguar tu URL y pasarla

```bash
.venv/Scripts/python.exe scripts/check_remote_mcp.py
```

```
Tu servidor flora-mcp en el puerto 8100
[ok] esta escuchando en este momento

URLs que pueden usar tus companeros:
     FLORA_REMOTE_MCP=anthony=http://192.168.1.53:8100/mcp
```

Esa línea es la que le pasás a tus compañeros. Si aparecen varias IPs, la de la
LAN suele ser la `192.168.x.x` de tu adaptador Wi-Fi.

> Tu IP cambia si te reconectás al Wi-Fi. Volvé a correr el script si algo deja
> de funcionar a mitad de la demo.

---

## Tipo 5 — Consumir servidores de otros por red

### Paso 1: verificar que el peer responde

**Antes** de tocar el `.env`. Esto aísla el problema a una capa:

```bash
.venv/Scripts/python.exe scripts/check_remote_mcp.py http://192.168.1.20:8100/mcp
```

```
=== http://192.168.1.20:8100/mcp
[ok] TCP    192.168.1.20:8100 acepta conexiones
[ok] MCP    flora-mcp -- 4 tools: identify_plant_from_photo, ...
```

Acepta varias URLs de una vez:

```bash
.venv/Scripts/python.exe scripts/check_remote_mcp.py http://192.168.1.20:8100/mcp http://192.168.1.31:9000/mcp
```

### Paso 2: agregarlos al `.env`

Una línea, entradas separadas por coma, cada una con un nombre antes del `=`:

```env
FLORA_REMOTE_MCP=pedro=http://192.168.1.20:8100/mcp,maria=http://192.168.1.31:9000/mcp
```

El nombre es libre pero conviene que sea corto: es el prefijo que van a llevar
sus herramientas (`pedro__buscar_libros_tool`) y lo que ves en el sidebar.

Sin nombre también funciona, y se llaman `remoto1`, `remoto2`:

```env
FLORA_REMOTE_MCP=http://192.168.1.20:8100/mcp
```

### Paso 3: levantar el chatbot

```bash
.venv/Scripts/python.exe -m flora_assistant.web
```

Los servidores remotos aparecen en el sidebar junto a los locales. Uno caído
sale en rojo con su error, y el resto sigue funcionando.

### Paso 4: probar que el modelo realmente los usa

Pedíselo por nombre, para que no elija la herramienta local equivalente:

```
Usando especificamente el servidor pedro, buscá libros sobre redes.
```

La traza debajo de la respuesta ("N herramientas usadas") te dice qué servidor
atendió.

---

## Tipo 6 — Tu servidor en la nube (Cloudflare Workers)

Es el punto 7 de la rúbrica: un servidor MCP ejecutándose en un servicio de
nube, no como subproceso local. Está desplegado y siempre encendido, así que no
hay nada que levantar antes de la demo.

```
https://flora-remote-mcp.isaproyecto.workers.dev/mcp
```

Ya está en el `.env`. Para verificarlo:

```bash
.venv/Scripts/python.exe scripts/check_remote_mcp.py https://flora-remote-mcp.isaproyecto.workers.dev/mcp
```

```
[ok] TCP    172.67.128.151:443 acepta conexiones
[ok] TLS    TLSv1.3, certificado para isaproyecto.workers.dev, *.isaproyecto.workers.dev
[ok] MCP    flora-remote -- 3 tools: lookup_species, native_range, occurrences_in_country
```

El código vive en [`remote-server/`](remote-server/README.md), con sus propias
instrucciones de despliegue. Ojo con el nombre: este es el Worker de
TypeScript, distinto del repo `flora-remote-mcp` que aloja el servidor local
de Python.

**Escenario para la demo** — muestra los dos servidores como complementarios:

```
Usando el servidor flora-remoto, de donde es originaria Hydrilla verticillata
y cuantos registros hay en Guatemala?
```

El remoto responde el origen y la presencia, y avisa que el estatus
(nativa/introducida/invasora) requiere el servidor local. Ahí pedís la
clasificación completa y se ve el ruteo entre ambos.

> Si acabás de crear el subdominio `.workers.dev`, el certificado TLS tarda
> unos minutos en emitirse. Mientras tanto el TCP conecta pero el TLS falla:
> por eso el script revisa esa capa por separado.

---

## Checklist de la demo

1. [ ] VPN apagada, todos en la misma red Wi-Fi
2. [ ] Regla de firewall creada (una vez por máquina)
3. [ ] `flora-mcp --http --host 0.0.0.0` corriendo en su propia terminal
4. [ ] `check_remote_mcp.py` sin argumentos → confirma que escuchás
5. [ ] URLs intercambiadas con el grupo
6. [ ] `check_remote_mcp.py <url>` de cada compañero → todos en `[ok]`
7. [ ] `FLORA_REMOTE_MCP` actualizado en el `.env`
8. [ ] Chatbot levantado **antes** de que te toque presentar (tarda ~30s en
       conectar los servidores locales)

---

## Si algo falla

| Síntoma | Causa probable | Qué hacer |
|---------|----------------|-----------|
| `rechazo la conexion` | Nada escucha en ese puerto | Que arranque el servidor, y que use `--host 0.0.0.0` y no `127.0.0.1` |
| `no respondio en 5s` | Firewall descartando paquetes, o IP equivocada | Regla de firewall en la máquina del otro; confirmar la IP con `check_remote_mcp.py` sin argumentos |
| `no se pudo resolver` | Nombre de host mal escrito | Usar la IP numérica |
| `handshake TLS rechazado` | Certificado todavía no emitido en un subdominio `.workers.dev` recién creado | Esperar unos minutos y reintentar |
| TCP `[ok]` pero MCP falla | Puerto ocupado por otra cosa, o la ruta no es `/mcp` | Confirmar la URL completa con el dueño |
| Se ven entre sí pero no conectan | VPN activa en alguno de los dos | Apagarla en ambos |
| El servidor arranca pero nadie lo alcanza | Bindeado a `127.0.0.1` | Relanzar con `--host 0.0.0.0` |
| Un cambio en el código no se refleja | Proceso viejo ocupando el puerto | `netstat -ano \| findstr 8100` y matar el PID |
| `[!] library no conecto` | MySQL apagado | `docker compose ... up -d` en ese repo |
| Herramientas duplicadas o faltantes | — | No debería pasar: van prefijadas por servidor. Si pasa, es un bug |

---

## Referencia rápida

```bash
# mi servidor, para que me consuman
cd ../Proyecto-Redes-Isa/flora-remote-mcp && .venv/Scripts/python.exe -m flora_mcp.server --http --host 0.0.0.0 --port 8100

# mis URLs para compartir
.venv/Scripts/python.exe scripts/check_remote_mcp.py

# probar el servidor de alguien más
.venv/Scripts/python.exe scripts/check_remote_mcp.py http://IP:8100/mcp

# chatbot en consola
.venv/Scripts/python.exe -m flora_assistant.main

# chatbot en el navegador -> http://127.0.0.1:8765
.venv/Scripts/python.exe -m flora_assistant.web

# pruebas (sin red)
.venv/Scripts/python.exe -m pytest -q -m "not network"
```
