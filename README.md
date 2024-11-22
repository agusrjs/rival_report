# Dashboard de Análisis Rival

Este proyecto proporciona un análisis detallado de los datos de la liga Primera B Nacional de Argentina, aunque podría utilizarse con distintos torneos en todo el mundo. Los datos fueron provistos por **Sofascore**, obtenidos mediante web scraping. Tanto esto como para el procesamiento se realizó en Python. Los resultados se visualizan en un dashboard interactivo desarrollado en **Power BI**. El panel incluye secciones de análisis propio de cada equipo, más allá de los proveedores de datos. Se muestra un ejemplo de esto seleccionando el equipo **San Telmo**.

![Liga](images/screenshot00.png)

## **Objetivo del proyecto**

El propósito principal es realizar un análisis detallado del desempeño de los equipos y jugadores en la liga Primera B Nacional, con una exploración en profundidad del equipo **San Telmo**. El dashboard permite:

- **Análisis de rendimiento por equipo**: Estadísticas acumuladas por equipo durante la temporada.
- **Análisis de jugadores**: Desempeño individual, mapas de calor, y contribuciones clave.
- **Eventos y partidos**: Resúmenes, alineaciones, y estadísticas de partidos.
- **Visualizaciones interactivas**: Métricas clave presentadas de manera visual para facilitar la toma de decisiones.

![Plantel](images/screenshot01.png)

![Equipo](images/screenshot02.png)

## **Estructura del proceso**

1. **Obtención de datos**  
   Utilizando `getting_data.ipynb` y el script `pvd_Sofascore.py`, se recopilan datos relevantes de la liga y sus equipos:
   - Equipos de la liga y estadísticas acumuladas.
   - Jugadores, sus perfiles, mapas de calor y estadísticas.
   - Partidos, alineaciones, resultados, y resúmenes de eventos.

2. **Procesamiento de datos**  
   Los datos se estructuran en tablas CSV que luego son utilizadas como fuentes para el dashboard.

3. **Visualización en Power BI**  
   - Se crean métricas y gráficos personalizados.
   - Se implementan filtros para facilitar el análisis específico de San Telmo y otros equipos.

![Alineaciones](images/screenshot03.png)

## **Visualización del dashboard**

El dashboard incluye las siguientes secciones clave:  
- **Vista general de la liga**: Tabla de posiciones, resultados recientes, y estadísticas agregadas.  
- **Análisis por equipo**: Rendimiento y métricas específicas para San Telmo y otros equipos.  
- **Rendimiento de jugadores**: Mapas de calor, estadísticas clave, y contribuciones individuales.  
- **Eventos y detalles de partidos**: Resultados, incidencias, y datos de momentum.

![Partido](images/screenshot05.png)

![Remates](images/screenshot06.png)