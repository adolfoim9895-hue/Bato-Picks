# ⚽ Bato Picks Analyzer

Una aplicación de análisis futbolístico en español que se publica desde **GitHub** con **Streamlit Community Cloud**.

> ⚠️ La versión inicial usa estadísticas de un proveedor (API-Football), un modelo de Poisson **heurístico no calibrado** y, de forma opcional, búsqueda de noticias y redacción con IA. No sabe el futuro ni garantiza apuestas ganadoras. No inventa información: si no alcanza la muestra mínima, aparta el partido.

## Funciones

- Busca encuentros reales por fecha y zona horaria de Tijuana.
- Selecciona hasta **5 partidos por tanda** para no agotar rápidamente la cuota gratuita del proveedor.
- Permite pegar equipos en el formato `Local - Visitante` y localizarlos en el calendario.
- Opcional: detecta nombres de equipos en una **captura** con OpenAI Vision; solicita una clave OpenAI.
- Calcula resultados previos **anteriores al saque inicial** para evitar usar resultados posteriores.
- Muestra últimos nueve partidos, resultados, rivales, sedes, goles, tabla de liga y enfrentamientos directos.
- Consulta lesiones y alineaciones de API-Football; contrasta si los afectados fueron titulares en dos de tres alineaciones recientes y etiqueta **ADVERTENCIA MUY IMPORTANTE**.
- Si hay once confirmado, comprueba si faltan **3 o más jugadores habituales** frente a sus alineaciones anteriores.
- Evita penalizar otra vez lesiones antiguas de jugadores que no disputaron los partidos recientes.
- Aplica un **pequeño ajuste explícito** a los goles esperados por bajas nuevas de titulares habituales. No dispone de un modelo de impacto individual validado.
- Separa `VERIFICADO` (muestra histórica suficiente + dos fuentes externas + historial de alineaciones), `PARCIAL` y `APARTADO` (menos de 3 partidos anteriores por equipo).
- Opcional: búsqueda de enlaces de medios/federaciones con Tavily; **un enlace no garantiza que una lesión esté confirmada**. Debe leerse la fuente.
- Opcional: redacta un informe narrativo con IA basado únicamente en los datos recogidos.
- No utiliza cuotas de apuestas y permite ocultar copas y amistosos.
- Exporta informes a CSV y JSON.
- Incluye un **modo demostración** con datos deportivos claramente ficticios.

## Cómo publicarla desde un teléfono Android

### Paso 1. Crea el repositorio

1. Entra en [github.com](https://github.com) y accede a tu cuenta.
2. Pulsa `+` → **New repository**.
3. Nombre sugerido: `bato-picks-analyzer`.
4. Elige visibilidad **Private** o **Public** según tus preferencias.
5. Crea el repositorio. **GitHub guarda el código, no ejecuta el servicio Python.**

### Paso 2. Sube estos archivos

1. Descarga y **descomprime** el ZIP de la aplicación. GitHub no descomprime automáticamente ZIPs subidos.
2. Abre tu repositorio. Pulsa **Add file** → **Upload files** (si el botón no aparece en Android, activa «Sitio de escritorio» del navegador).
3. Sube a la **raíz** del repositorio estos archivos sin cambiarlos de nombre:
   - `app.py`
   - `motor.py`
   - `proveedores.py`
   - `requirements.txt`
   - `README.md`
4. Confirma con **Commit changes**.
5. La carpeta `.streamlit` es opcional: solo personaliza los colores. No necesitas subirla para que la app funcione.

### Paso 3. Consigue una clave deportiva

1. Crea una cuenta en [API-Football / API-Sports](https://www.api-football.com/).
2. Desde el panel de usuario copia tu **API key** (se llama **API_FOOTBALL_KEY** en esta app).
3. Según la información publicada en noviembre de 2026, el plan gratuito permite **100 consultas por día, hasta 10 por minuto**. El análisis profundo consulta varios endpoints por partido y las ligas menores pueden tener menos cobertura. Revisa las condiciones vigentes en el panel de proveedor.
4. **No escribas la clave dentro de archivos de GitHub ni en un repositorio público.**

### Paso 4. Publica la aplicación

1. Ve a [share.streamlit.io](https://share.streamlit.io/).
2. Accede con GitHub y elige **Create app** → **Yup, I have an app**.
3. Selecciona tu repositorio, rama `main`, archivo principal `app.py`.
4. En **Advanced settings** → **Secrets**, agrega:

```toml
API_FOOTBALL_KEY = "pega_aqui_tu_clave"
```

5. Pulsa **Deploy**. Al concluir, recibirás una dirección `*.streamlit.app` que podrás abrir desde tu celular.

### Paso 5. Funciones adicionales (opcionales)

Para buscar artículos de prensa y clasificar mejor la calidad de las fuentes, puedes conseguir una clave de [Tavily](https://tavily.com/) y agregar al mismo panel de secretos:

```toml
TAVILY_API_KEY = "tu_clave_de_tavily"
```

Para extraer partidos desde tus capturas y pedir una explicación en español redactada por IA, puedes crear una clave de [OpenAI API](https://platform.openai.com/api-keys) y agregar:

```toml
OPENAI_API_KEY = "tu_clave_de_openai"
```

**La API de OpenAI se factura por separado de una suscripción ChatGPT Plus.** Consulta precios y configura límites de gasto en el proveedor. El modo básico de estadísticas funciona sin OpenAI ni Tavily.

## Ejecución en tu propia computadora (opcional)

```bash
python -m venv .venv
# Activa el entorno virtual según tu sistema.
pip install -r requirements.txt
export API_FOOTBALL_KEY="TU_CLAVE"  # macOS / Linux
streamlit run app.py
```

En Windows PowerShell define la variable con `$env:API_FOOTBALL_KEY="TU_CLAVE"`.

## Qué significan los indicadores

| Estado | Interpretación |
|---|---|
| ✓ VERIFICADO | Al menos cinco resultados previos por equipo, dos dominios externos confiables encontrados y suficientes alineaciones históricas; la información individual todavía debe comprobarse en los enlaces. |
| ⚠ PARCIAL | Hay resultados, pero no se pudieron corroborar suficientemente lesiones, alineaciones o fuentes independientes. |
| ✳ APARTADO | Menos de tres partidos anteriores para uno de los equipos; no se produce porcentaje. |

**ADVERTENCIA MUY IMPORTANTE**: el proveedor reporta una baja de alguien que fue titular en al menos 2 partidos históricos revisados, o al menos 3 titulares recientes están fuera de la alineación oficial. Esto no afirma que la baja sea oficial: es un aviso para abrir y corroborar la información.

## Limitaciones importantes

- El proveedor puede no tener lesiones o alineaciones de ciertos torneos femeniles, Sub-19, ligas locales y clubes modestos.
- Las publicaciones de medios se listan con enlace y procedencia; la búsqueda automática no comprueba manualmente cada noticia. El usuario debe revisar el artículo.
- Si no hay alineaciones oficiales aún, **no se confirma que alguien vaya a ser titular**.
- Para análisis retrospectivos, los resultados se cortan antes del encuentro, pero las lesiones consultadas a la API pueden corresponder al estado actual, no al histórico.
- Los rangos y ajustes del modelo son supuestos de ingeniería, no probabilidades calibradas con un conjunto de validación. Se recomienda probar el modelo retrospectivamente con datos sin filtración del futuro antes de tomar decisiones.
- Una tasa aparente alta de aciertos no implica rentabilidad. No hay automatización de apuestas.
- Los partidos de copa pueden marcarse como riesgo de rotación; el filtro para ocultarlos está activado por defecto.

## Estructura del código

```text
bato-picks-analyzer/
├── app.py                 # Interfaz y opciones
├── motor.py               # Resultados, estadísticas, titulares y Poisson
├── proveedores.py         # API-Football, búsqueda Tavily, OpenAI opcional
├── requirements.txt       # Dependencias
├── .streamlit/
│   ├── config.toml        # Colores (opcional)
│   └── secrets.toml.example
└── tests/
    └── test_motor.py
```

Fuentes técnicas: [API-Football Documentation](https://www.api-football.com/documentation-v3) · [Streamlit Community Cloud](https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/deploy) · [Subir archivos a GitHub](https://docs.github.com/en/repositories/working-with-files/managing-files/adding-a-file-to-a-repository).

