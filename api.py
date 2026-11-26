"""
Radar de Subastas — API.

Encadena cuatro fuentes públicas para responder a una pregunta que hoy nadie
responde de una vez: *esta subasta que sale a X euros, ¿es oportunidad o
trampa?*

    BOE (oportunidad) → Catastro (qué es) → valoración (cuánto vale)
                                          → rentabilidad (qué deja al mes)
                                          → riesgo (qué puede salir mal)

Puerto 8010.
"""
from __future__ import annotations

import os
from html import escape
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, HTMLResponse, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from boe_client import BoeClient, PROVINCIAS
from catastro import consultar as consultar_catastro
from rentabilidad import Supuestos, analizar, precio_maximo_para_cash_flow
from riesgo import evaluar as evaluar_riesgo
from valoracion import valorar
from zonas import (analizar_zonas, contexto_distritos, provincias_disponibles,
                   se_pagan_solos)
from inversor import analizar_inversor
from contexto_zona import evaluar_zona
from entorno import analizar_entorno, geocodificar

app = FastAPI(
    title="Radar de Subastas",
    description="Oportunidades inmobiliarias en subastas públicas, valoradas y con su riesgo.",
    version="1.0.0",
)
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"]
)


class SupuestosIn(BaseModel):
    entrada_pct: float = Field(0.30, ge=0.0, le=1.0)
    interes_anual: float = Field(0.032, ge=0.0, le=0.20)
    anios_hipoteca: int = Field(25, ge=1, le=40)
    reforma: float = Field(0.0, ge=0.0)
    vacancia_pct: float = Field(0.06, ge=0.0, le=0.5)
    irpf_marginal: float = Field(0.30, ge=0.0, le=0.55)
    comunidad_mensual: float = Field(60.0, ge=0.0)
    ibi_anual: float = Field(400.0, ge=0.0)

    def a_supuestos(self) -> Supuestos:
        return Supuestos(**self.model_dump())


class AnalisisIn(BaseModel):
    identificador: str = Field(..., description="Identificador de la subasta, p. ej. SUB-JA-2026-265154")
    alquiler_mensual: Optional[float] = Field(None, ge=0, description="Alquiler real si lo conoces")
    precio_adjudicacion: float | None = Field(None, gt=0)
    valor_referencia_catastro: float | None = Field(None, gt=0)
    deuda_asumida: float | None = Field(None, ge=0)
    deuda_liquidada: float = Field(0, ge=0)
    cuota_deuda: float | None = Field(None, ge=0)
    supuestos: Optional[SupuestosIn] = None


class CalculadoraIn(BaseModel):
    precio_compra: float = Field(..., gt=0)
    alquiler_mensual: float = Field(..., gt=0)
    provincia: Optional[str] = Field(None, description="Determina el ITP aplicable")
    supuestos: Optional[SupuestosIn] = None


@app.get("/", include_in_schema=False, response_class=HTMLResponse)
def buscador_web():
    pagina = Path(__file__).with_name("buscador.html").read_text(encoding="utf-8")
    provincias = "".join(
        f'<option value="{provincia["codigo"]}">{escape(provincia["nombre"])}</option>'
        for provincia in provincias_disponibles()
    )
    return pagina.replace("<!-- opciones-provincia -->", provincias)


@app.get("/panel.js", include_in_schema=False)
def panel_script():
    return FileResponse(Path(__file__).with_name("panel.js"), media_type="text/javascript")


@app.get("/health")
def health():
    return {"status": "ok", "service": "subastas-radar", "version": "1.0.0"}


@app.get("/subastas/health")
def health_prefijo():
    return health()


@app.get("/subastas/provincias")
def provincias():
    """Provincias con atajo por nombre; el resto se consulta por código INE."""
    return {"provincias": sorted(PROVINCIAS), "nota": "También admite el código INE de dos dígitos."}


@app.get("/subastas/buscar")
def buscar(provincia: str = Query("madrid"), limite: int = Query(10, ge=1, le=40)):
    """Subastas de inmuebles en curso, con sus datos económicos y del bien."""
    try:
        with BoeClient() as cliente:
            subastas = cliente.buscar_con_detalle(provincia, limite)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"El portal del BOE no respondió: {e}")

    return {
        "provincia": provincia,
        "total": len(subastas),
        "subastas": [s.to_dict() | {"url": s.url} for s in subastas],
        "fuente": "Portal de Subastas de la Agencia Estatal BOE",
    }


@app.get("/subastas/zonas")
def zonas(provincia: str = Query("madrid", description="Nombre o código INE de dos dígitos"),
          superficie: int = Query(80, ge=25, le=400),
          entrada_pct: float = Query(0.30, ge=0.0, le=1.0),
          interes_anual: float = Query(None, ge=0.0, le=0.2),
          anios: int = Query(25, ge=5, le=40),
          diferencial: float = Query(None, ge=0.0, le=0.05,
                                     description="Diferencial sobre el Euríbor; por defecto 0,008"),
          limite: int = Query(40, ge=5, le=100)):
    """Compara los municipios de una provincia como inversión de alquiler.

    Con el alquiler real de cada municipio —el declarado a la Agencia
    Tributaria—, la renta del hogar del INE y el valor tasado oficial. Cada
    cifra dice de qué organismo, de qué año y de qué ámbito viene."""
    if interes_anual is None:
        from datos_vivos import tipo_hipotecario_estimado
        interes_anual = tipo_hipotecario_estimado(diferencial)["tipo_estimado"]
    s = Supuestos(entrada_pct=entrada_pct, interes_anual=interes_anual, anios_hipoteca=anios)
    return analizar_zonas(provincia, superficie, s, limite).to_dict()


@app.get("/subastas/se-pagan-solos")
def municipios_que_se_pagan_solos(
        superficie: int = Query(80, ge=25, le=400),
        entrada_pct: float = Query(0.30, ge=0.0, le=1.0),
        interes_anual: float = Query(None, ge=0.0, le=0.2),
        anios: int = Query(25, ge=5, le=40),
        diferencial: float = Query(None, ge=0.0, le=0.05),
        limite: int = Query(40, ge=5, le=200)):
    """Dónde en España una vivienda tipo se paga sola.

    La pregunta del proyecto llevada al mapa entero: en qué municipios el
    alquiler real cubre la hipoteca y todos los gastos, sin poner dinero cada
    mes. Con los supuestos por defecto salen unas decenas de los 3.388 con dato,
    y eso es en sí la respuesta más útil."""
    if interes_anual is None:
        from datos_vivos import tipo_hipotecario_estimado
        interes_anual = tipo_hipotecario_estimado(diferencial)["tipo_estimado"]
    s = Supuestos(entrada_pct=entrada_pct, interes_anual=interes_anual, anios_hipoteca=anios)
    return se_pagan_solos(superficie, s, limite)


@app.get("/subastas/se-pagan-solos.csv")
def municipios_que_se_pagan_solos_csv(
        superficie: int = Query(80, ge=25, le=400),
        entrada_pct: float = Query(0.30, ge=0.0, le=1.0),
        interes_anual: float = Query(None, ge=0.0, le=0.2),
        anios: int = Query(25, ge=5, le=40),
        diferencial: float = Query(None, ge=0.0, le=0.05),
        limite: int = Query(200, ge=5, le=3400)):
    """El mismo resultado, en CSV, para poder llevárselo.

    Hasta ahora la respuesta se veía en pantalla y ahí se quedaba. Quien quiera
    comprobar el cálculo, cruzarlo con lo suyo o citarlo no tenía forma de
    sacarlo, y es justo lo que hace útil —y citable— una herramienta de datos.

    El fichero lleva cabecera con los SUPUESTOS y las FUENTES: fuera de la
    pantalla que los explica, una tabla de cifras sin contexto se malinterpreta
    sola. Y deja constancia de que el dato es de organismos públicos, no mío.
    """
    import csv as _csv
    import io as _io
    from datetime import datetime as _dt

    datos = municipios_que_se_pagan_solos(
        superficie=superficie, entrada_pct=entrada_pct,
        interes_anual=interes_anual, anios=anios,
        diferencial=diferencial, limite=limite)

    filas = datos.get("municipios") or []
    buf = _io.StringIO()

    sup = datos.get("supuestos") or {}
    buf.write(f"# Municipios de Espana donde una vivienda tipo se paga sola\n")
    buf.write(f"# Generado: {_dt.now().isoformat(timespec='seconds')}\n")
    buf.write(f"# Herramienta: https://adrianmoreno-dev.com/demo/radar-subastas\n")
    buf.write(f"# Superficie tipo: {datos.get('superficie_tipo', superficie)} m2\n")
    for k, v in sup.items():
        buf.write(f"# Supuesto {k}: {v}\n")
    for aviso in (datos.get("avisos") or []):
        buf.write(f"# Aviso: {aviso}\n")
    fuentes = datos.get("fuentes") or {}
    if isinstance(fuentes, dict):
        for clave, desc in fuentes.items():
            buf.write(f"# Fuente ({clave}): {desc}\n")
    else:
        for fuente in fuentes:
            buf.write(f"# Fuente: {fuente}\n")
    buf.write(f"# Total de municipios que cumplen: {datos.get('total', len(filas))}"
              f" (este fichero trae {len(filas)})\n")
    buf.write("#\n")

    if filas:
        w = _csv.DictWriter(buf, fieldnames=list(filas[0].keys()), extrasaction="ignore")
        w.writeheader()
        w.writerows(filas)

    nombre = f"se-pagan-solos-{superficie}m2-entrada{int(entrada_pct*100)}.csv"
    return Response(
        content=buf.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{nombre}"'},
    )


@app.get("/subastas/distritos")
def distritos(ciudad: str = Query("madrid")):
    """Renta del hogar y evolución del alquiler por distrito censal.

    Sólo esas dos cosas: son las únicas que el INE publica a ese grano."""
    return contexto_distritos(ciudad)


@app.get("/subastas/ciudades")
def ciudades():
    """Provincias con comparación de municipios disponible."""
    return {"provincias": provincias_disponibles()}


@app.get("/subastas/oportunidades")
def oportunidades(provincia: str = Query("madrid"), limite: int = Query(12, ge=1, le=30),
                  precio_max: float = Query(None, description="Descarta lo que no puedas pagar"),
                  entrada_max: float = Query(None, description="Capital del que dispones"),
                  riesgo_max: int = Query(None, ge=0, le=100),
                  incluir_cerradas: bool = Query(False,
                      description="El BOE tarda en marcar como cerradas las que ya vencieron"),
                  solo_analizables: bool = Query(True),
                  localidad: str | None = Query(None, max_length=100)):
    """Subastas ya valoradas y ordenadas por oportunidad.

    El listado crudo obliga a entrar una por una para saber si algo interesa, y
    muchas no se pueden analizar siquiera (sin referencia catastral no hay
    superficie, y sin superficie no hay precio por m²). Aquí llegan ya con su
    riesgo, su precio por m² y el capital que harían falta, ordenadas para que lo
    interesante esté arriba.
    """
    try:
        with BoeClient() as cliente:
            subastas = cliente.buscar_con_detalle(provincia, limite, localidad)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"El portal del BOE no respondió: {e}")

    from impuestos import calcular_itp, gastos_compra

    resultados = []
    for s in subastas:
        d = s.to_dict() | {"url": s.url}
        d["analizable"] = bool(s.referencia_catastral and s.valor_subasta)
        d["motivo_no_analizable"] = None
        if not s.valor_subasta:
            d["motivo_no_analizable"] = "la subasta no publica valor de salida"
        elif not s.referencia_catastral:
            d["motivo_no_analizable"] = ("sin referencia catastral no se puede saber "
                                         "la superficie ni el precio por m²")

        riesgo = evaluar_riesgo(s.to_dict(), None)
        d["riesgo_nivel"] = riesgo.nivel
        d["riesgo_puntuacion"] = riesgo.puntuacion
        d["riesgos_clave"] = [r["titulo"] for r in riesgo.riesgos[:3]]

        # Superficie del Catastro sólo si la hay: es lo que permite el €/m².
        d["superficie_m2"] = None
        d["precio_m2"] = None
        if s.referencia_catastral:
            inm = consultar_catastro(s.referencia_catastral)
            if inm.superficie_m2:
                d["superficie_m2"] = inm.superficie_m2
                d["anio_construccion"] = inm.anio_construccion
                if s.valor_subasta:
                    d["precio_m2"] = round(s.valor_subasta / inm.superficie_m2, 2)

        # Capital necesario: es el filtro que de verdad usa un inversor.
        if s.valor_subasta:
            itp = calcular_itp(s.valor_subasta, s.provincia)["cuota"]
            gastos = gastos_compra(s.valor_subasta)["total"]
            d["capital_necesario_estimado"] = round(s.valor_subasta * 0.30 + itp + gastos, 2)
        else:
            d["capital_necesario_estimado"] = None

        # Días hasta el cierre: en subastas la urgencia es parte de la decisión.
        # Y si ya cerró, hay que decirlo: el BOE tarda en cambiar el estado de
        # «en curso», así que una subasta terminada puede seguir apareciendo en
        # el listado. Antes se recortaba a cero y se mostraba «0 días para
        # pujar», que es indistinguible de «cierra hoy» e invita a actuar sobre
        # algo que ya no se puede pujar.
        d["dias_para_cierre"] = None
        d["cerrada"] = False
        if s.fecha_fin:
            from datetime import datetime, timezone
            try:
                fin = datetime.fromisoformat(s.fecha_fin)
                ahora = datetime.now(fin.tzinfo or timezone.utc)
                restante = fin - ahora
                d["cerrada"] = restante.total_seconds() <= 0
                d["dias_para_cierre"] = None if d["cerrada"] else max(0, restante.days)
                if d["cerrada"]:
                    d["motivo_no_analizable"] = (
                        f"el plazo terminó el {s.fecha_fin[:10]}; el portal del BOE "
                        "todavía la lista como en curso")
                    d["analizable"] = False
            except ValueError:
                pass

        resultados.append(d)

    if not incluir_cerradas:
        resultados = [r for r in resultados if not r["cerrada"]]
    if solo_analizables:
        resultados = [r for r in resultados if r["analizable"]]
    if precio_max:
        resultados = [r for r in resultados if (r["valor_subasta"] or 0) <= precio_max]
    if entrada_max:
        resultados = [r for r in resultados
                      if (r["capital_necesario_estimado"] or 0) <= entrada_max]
    if riesgo_max is not None:
        resultados = [r for r in resultados if r["riesgo_puntuacion"] <= riesgo_max]

    # Orden: primero lo barato por m² y con menos riesgo. Sin €/m² va al final,
    # porque no se puede comparar.
    def clave(r):
        sin_dato = r["precio_m2"] is None
        return (sin_dato, r["riesgo_puntuacion"], r["precio_m2"] or 0)

    resultados.sort(key=clave)

    return {
        "provincia": provincia,
        "total": len(resultados),
        "filtros": {"precio_max": precio_max, "entrada_max": entrada_max,
                    "riesgo_max": riesgo_max, "solo_analizables": solo_analizables,
                    "incluir_cerradas": incluir_cerradas},
        "oportunidades": resultados,
        "orden": "menor riesgo y menor precio por m² primero",
        "fuente": "Portal de Subastas del BOE + Catastro",
    }


@app.post("/subastas/analizar")
def analizar_subasta(datos: AnalisisIn):
    """Análisis completo de una subasta: qué es, cuánto vale, qué renta y qué riesgo tiene."""
    try:
        with BoeClient() as cliente:
            subasta = cliente.detalle(datos.identificador)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"No se pudo leer la subasta: {e}")

    precio = datos.precio_adjudicacion or subasta.valor_subasta
    if not precio or precio <= 0:
        raise HTTPException(422, "Introduce un precio previsto para analizar esta ficha.")
    deuda = datos.deuda_asumida or 0
    liquidacion = datos.deuda_liquidada
    if liquidacion > deuda or (datos.cuota_deuda and deuda <= liquidacion):
        raise HTTPException(422, "La liquidación debe ser como máximo el saldo asumido. Solo indica cuota si queda deuda pendiente.")

    inmueble = (consultar_catastro(subasta.referencia_catastral).to_dict()
                if subasta.referencia_catastral else
                {"error": "La subasta no publica referencia catastral"})
    ficha = subasta.to_dict()
    v = valorar(ficha | {"valor_subasta": precio}, inmueble, datos.alquiler_mensual)
    alquiler = datos.alquiler_mensual if datos.alquiler_mensual is not None else v.alquiler_mensual
    riesgo = evaluar_riesgo(ficha, inmueble)
    supuestos = datos.supuestos.a_supuestos() if datos.supuestos else Supuestos()
    provincia = inmueble.get("provincia") or subasta.provincia
    referencia = datos.valor_referencia_catastro
    cuota_deuda = datos.cuota_deuda or 0
    avisos = []
    if datos.deuda_asumida is None:
        avisos.append("Deuda asumida pendiente de verificar. Los totales provisionales usan 0 € de deuda.")
    if deuda > liquidacion and datos.cuota_deuda is None:
        avisos.append("Falta la cuota de la deuda pendiente. Los indicadores de caja se muestran sin ella.")
    if referencia is None:
        avisos.append("Falta el valor de referencia del Catastro. El ITP es provisional.")
    avisos.append("Escenario sujeto a ITP. Confirma el régimen fiscal, las cargas y la base imponible aplicable al expediente.")
    avisos.append("Fuera de la estimación: derramas, procurador, gastos del procedimiento y costes de recuperar la posesión.")
    if alquiler is None:
        avisos.append("Sin alquiler disponible. Solo se presenta la inversión y los gastos fijos conocidos.")

    def calcular(importe):
        return analizar(importe, alquiler or 0, provincia, supuestos,
                        base_itp=max(importe, referencia or 0), deuda_asumida=deuda,
                        deuda_liquidada=liquidacion, cuota_deuda=cuota_deuda)

    a = calcular(precio)
    formalizacion = a.detalle["gastos_formalizacion"]
    gastos = {
        "inversion_total": a.inversion_total,
        "capital_aportado": a.capital_aportado,
        "costes_adquisicion_total": round(a.itp + a.otros_gastos_compra + a.reforma, 2),
        "salidas_caja_mensuales": a.detalle["salidas_caja_mensuales"] if alquiler is not None else None,
        "salidas_caja_anuales": a.detalle["salidas_caja_anuales"] if alquiler is not None else None,
        "precio_compra": a.precio_compra,
        "origen_precio": "Adjudicación prevista" if datos.precio_adjudicacion else "Valor publicado por el BOE",
        "deuda_asumida": datos.deuda_asumida,
        "deuda_liquidada": liquidacion,
        "deuda_pendiente": deuda - liquidacion if datos.deuda_asumida is not None else None,
        "cuota_deuda": datos.cuota_deuda,
        "valor_referencia_catastro": referencia,
        "base_itp": max(precio, referencia or 0),
        "itp_pct": a.itp_pct,
        "itp": a.itp,
        "notaria": formalizacion["notaria"],
        "registro": formalizacion["registro"],
        "gestoria": formalizacion["gestoria"],
        "reforma": a.reforma,
        "entrada_euros": round(precio * supuestos.entrada_pct, 2),
        "hipoteca": a.hipoteca,
        "cuota_mensual": a.cuota_mensual,
        "deposito": subasta.deposito,
        "ibi_anual": supuestos.ibi_anual,
        "comunidad_anual": round(supuestos.comunidad_mensual * 12, 2),
        "seguro_anual": supuestos.seguro_anual,
        "mantenimiento_anual": round((alquiler or 0) * 12 * (1 - supuestos.vacancia_pct)
                                    * supuestos.mantenimiento_pct_alquiler, 2) if alquiler is not None else None,
        "gestion_anual": round((alquiler or 0) * 12 * (1 - supuestos.vacancia_pct)
                              * supuestos.gestion_pct_alquiler, 2) if alquiler is not None else None,
        "gastos_anuales": a.gastos_anuales if alquiler is not None else None,
        "irpf_estimado": a.irpf_estimado if alquiler is not None else None,
        "avisos": avisos,
    }
    financiero = a.to_dict() if alquiler is not None else None
    retorno = None
    if financiero is not None:
        caja_anual = a.detalle["cash_flow_anual"]
        techo = None
        if deuda <= liquidacion or datos.cuota_deuda is not None:
            bajo, alto = .01, max(precio, alquiler * 12 * 60, 1)
            while alto < 1e9 and calcular(alto).detalle["cash_flow_anual"] >= 0:
                alto *= 2
            if calcular(bajo).detalle["cash_flow_anual"] >= 0 > calcular(alto).detalle["cash_flow_anual"]:
                for _ in range(50):
                    medio = (bajo + alto) / 2
                    if calcular(medio).detalle["cash_flow_anual"] >= 0:
                        bajo = medio
                    else:
                        alto = medio
                techo = int(bajo * 100) / 100
        financiero["precio_maximo_cash_flow_cero"] = techo
        retorno = {
            "cash_flow_mensual": a.cash_flow_mensual,
            "cash_flow_anual": caja_anual,
            "rentabilidad_neta": a.rentabilidad_neta,
            "retorno_caja_pct": round(caja_anual / a.capital_aportado, 4) if a.capital_aportado > 0 else None,
            "alquiler_mensual": a.alquiler_mensual,
            "origen_alquiler": "Introducido por el usuario" if datos.alquiler_mensual is not None else v.alquiler_ambito,
            "ingresos_anuales_brutos": a.ingresos_anuales_brutos,
            "ingresos_mensuales_efectivos": a.detalle["ingresos_mensuales_efectivos"],
            "salidas_caja_mensuales": gastos["salidas_caja_mensuales"],
            "salidas_caja_anuales": gastos["salidas_caja_anuales"],
            "perdida_vacancia": round(a.ingresos_anuales_brutos - a.ingresos_anuales_efectivos, 2),
            "ingresos_anuales_efectivos": a.ingresos_anuales_efectivos,
            "beneficio_neto_anual_antes_impuestos": a.beneficio_neto_anual_antes_impuestos,
            "beneficio_neto_anual": a.beneficio_neto_anual,
            "rentabilidad_bruta": a.rentabilidad_bruta,
            "anios_recuperar_capital_caja": round(a.capital_aportado / caja_anual, 1)
                                          if caja_anual > 0 and a.capital_aportado > 0 else None,
            "precio_maximo_cash_flow_cero": techo,
            "formulas": [
                "Rentabilidad bruta = ingreso bruto anual ÷ inversión total.",
                "Rentabilidad neta = beneficio anual tras IRPF y antes de cuotas ÷ inversión total.",
                "Flujo de caja = ingresos efectivos menos gastos operativos, IRPF y ambas cuotas.",
                "Retorno de caja = flujo anual tras ambas cuotas ÷ capital propio inicial.",
                "Recuperación simple = capital propio inicial ÷ flujo anual positivo. No proyecta cambios futuros.",
            ],
        }

    # Contexto del entorno: manda sobre la rentabilidad, porque una zona
    # tensionada limita por ley el alquiler que se puede cobrar.
    zona = evaluar_zona(
        inmueble.get("municipio") or subasta.localidad,
        inmueble.get("provincia") or subasta.provincia,
        inmueble.get("anio_construccion"),
        codigo_ine_provincia=inmueble.get("codigo_ine_provincia"),
        codigo_ine_municipio=inmueble.get("codigo_ine_municipio"),
    )

    # La pregunta del proyecto, respondida de frente y antes que nada.
    autofinanciacion = None
    compatible = not deuda and (referencia is None or referencia <= precio)
    if alquiler and not compatible:
        avisos.append("Las métricas avanzadas de inversor y autofinanciación quedan fuera de este escenario. "
                      "Los apartados de gastos y retorno sí usan la deuda y la base fiscal introducidas.")
    if alquiler and compatible:
        from autofinanciacion import analizar_autofinanciacion
        cp, cm = inmueble.get("codigo_ine_provincia"), inmueble.get("codigo_ine_municipio")
        autofinanciacion = analizar_autofinanciacion(
            precio, alquiler,
            inmueble.get("provincia") or subasta.provincia, supuestos,
            (str(cp).zfill(2) + str(cm).zfill(3)) if cp and cm else None,
        ).to_dict()

    metricas = None
    if alquiler and compatible:
        metricas = analizar_inversor(
            precio, alquiler,
            inmueble.get("provincia") or subasta.provincia, supuestos,
            renta_hogar_zona_anual=zona.renta_hogar_anual,
        ).to_dict()

    # Entorno: lo que hace que un piso se alquile rápido o se quede vacío.
    entorno = None
    coords = geocodificar(subasta.direccion, subasta.codigo_postal,
                          inmueble.get("municipio") or subasta.localidad)
    if coords:
        entorno = analizar_entorno(*coords).to_dict()
        entorno["coordenadas"] = {"lat": coords[0], "lon": coords[1]}

    return {
        "gastos_inversion": gastos,
        "ingresos_retorno": retorno,
        "se_paga_solo": autofinanciacion,
        "subasta": subasta.to_dict() | {"url": subasta.url},
        "inmueble": inmueble,
        "valoracion": v.to_dict(),
        "rentabilidad": financiero,
        "metricas_inversor": metricas,
        "contexto_zona": zona.to_dict(),
        "entorno": entorno,
        "riesgo": riesgo.to_dict(),
    }


@app.post("/subastas/inversor")
def metricas_inversor(datos: CalculadoraIn):
    """Métricas de solvencia sobre una operación: DSCR, punto muerto de
    ocupación, estrés de tipos, esfuerzo del inquilino y coste de oportunidad."""
    supuestos = datos.supuestos.a_supuestos() if datos.supuestos else Supuestos()
    m = analizar_inversor(datos.precio_compra, datos.alquiler_mensual,
                          datos.provincia, supuestos)
    return m.to_dict()


@app.get("/subastas/zona")
def zona(municipio: str = Query(...), provincia: str = Query(None),
         anio_construccion: int = Query(None)):
    """Contexto del entorno: zona tensionada, ITE y eficiencia energética."""
    return evaluar_zona(municipio, provincia, anio_construccion).to_dict()


@app.get("/subastas/alquiler")
def alquiler(codigo_municipio: str = Query(..., description="Código INE del municipio, 5 dígitos"),
             codigo_distrito: str = Query(None, description="Código INE del distrito, 7 dígitos")):
    """Cómo evoluciona el alquiler frente al precio de compra en una zona.

    Con los contratos que se declaran a Hacienda (IPVA) y el índice oficial de
    precios de vivienda (IPV), ambos del INE. Son índices, no niveles: dicen
    cuánto sube el alquiler, no cuánto se paga por él.
    """
    from alquiler_ine import (distritos_de, precio_vs_alquiler,
                              tendencia_alquiler_municipio)

    codigo = codigo_municipio.strip().zfill(5)
    municipio = tendencia_alquiler_municipio(codigo)
    comparacion = precio_vs_alquiler(codigo, codigo[:2], codigo_distrito)
    return {
        "municipio": municipio.to_dict(),
        "precio_vs_alquiler": comparacion.to_dict(),
        "distritos_disponibles": distritos_de(codigo),
    }


@app.get("/subastas/entorno")
def entorno_zona(lat: float = Query(...), lon: float = Query(...)):
    """Transporte, servicios y molestias alrededor de unas coordenadas (OSM)."""
    return analizar_entorno(lat, lon).to_dict()


@app.get("/subastas/vigencia")
def vigencia():
    """Estado de frescura de los datos: tipos de ITP, tipo de referencia del
    BCE y las dos fuentes externas. Pensado para engancharlo a un monitor."""
    from vigencia import comprobar
    resultados = [c.to_dict() for c in comprobar()]
    # Un fallo intermitente de un servicio ajeno (el Catastro corta conexiones
    # a ratos) no tumba el veredicto: aparece en la lista, para que se vea, pero
    # `todo_ok` responde a lo que hay que ARREGLAR aquí. Si el ruido apaga la
    # alarma, la alarma deja de servir. (2026-09-21)
    accionables = [c for c in resultados if c["estado"] not in ("ok", "intermitente")]
    return {
        "comprobaciones": resultados,
        "todo_ok": not accionables,
    }


@app.get("/subastas/tipo-interes")
def tipo_interes(diferencial: float = Query(None, ge=0.0, le=0.05,
                                            description="Diferencial del banco sobre el Euríbor")):
    """Tipo hipotecario: Euríbor a 12 meses en vivo más el diferencial del banco.

    El Euríbor sale del Banco de España con su fecha. El diferencial es lo único
    que no se mide, y por eso es un parámetro."""
    from datos_vivos import tipo_hipotecario_estimado
    return tipo_hipotecario_estimado(diferencial)


@app.post("/subastas/calculadora")
def calculadora(datos: CalculadoraIn):
    """Rentabilidad de cualquier operación, venga o no de una subasta.

    Útil para contrastar: los portales muestran rentabilidad bruta, que ignora
    ITP, gastos de compra y vacancia."""
    supuestos = datos.supuestos.a_supuestos() if datos.supuestos else Supuestos()
    from autofinanciacion import analizar_autofinanciacion
    resultado = analizar(datos.precio_compra, datos.alquiler_mensual, datos.provincia, supuestos)
    return {
        "se_paga_solo": analizar_autofinanciacion(
            datos.precio_compra, datos.alquiler_mensual, datos.provincia, supuestos
        ).to_dict(),
        "analisis": resultado.to_dict(),
        "precio_maximo_cash_flow_cero": precio_maximo_para_cash_flow(
            datos.alquiler_mensual, 0.0, datos.provincia, supuestos
        ),
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=int(os.getenv("PORT", 8010)))
