'use strict';

const operaciones = {
  '/health': ['Estado de la API', 'Comprueba si el servidor local responde.'],
  '/subastas/health': ['Estado del servicio de subastas', 'Comprueba la ruta de salud bajo el prefijo de subastas.'],
  '/subastas/provincias': ['Provincias del BOE', 'Consulta los nombres de provincia que acepta el buscador.'],
  '/subastas/buscar': ['Fichas del BOE', 'Obtén las fichas originales de inmuebles en curso de una provincia.'],
  '/subastas/zonas': ['Comparar municipios', 'Compara municipios de una provincia según alquiler, precio y financiación.'],
  '/subastas/se-pagan-solos': ['Municipios que se pagan solos', 'Busca municipios donde el alquiler estimado cubre los gastos y la hipoteca.'],
  '/subastas/se-pagan-solos.csv': ['Exportar municipios', 'Genera un CSV con los resultados, las fuentes y los supuestos.'],
  '/subastas/distritos': ['Comparar distritos', 'Consulta renta del hogar y evolución del alquiler por distrito censal.'],
  '/subastas/ciudades': ['Cobertura de la comparativa', 'Devuelve las provincias y sus códigos INE disponibles en la comparativa.'],
  '/subastas/oportunidades': ['Oportunidades', 'Busca subastas y añade indicadores de riesgo, superficie y capital estimado.'],
  '/subastas/analizar': ['Analizar una subasta', 'Consulta la ficha BOE y calcula la rentabilidad y el riesgo del caso.'],
  '/subastas/inversor': ['Métricas del inversor', 'Calcula indicadores como cobertura de deuda, esfuerzo y sensibilidad a los tipos.'],
  '/subastas/zona': ['Contexto de un municipio', 'Consulta información sobre zona tensionada, inspecciones y eficiencia energética.'],
  '/subastas/alquiler': ['Evolución del alquiler', 'Compara cómo cambian los índices de alquiler y de precio de compra.'],
  '/subastas/entorno': ['Servicios del entorno', 'Busca transporte, servicios y molestias alrededor de unas coordenadas.'],
  '/subastas/vigencia': ['Vigencia de las fuentes', 'Comprueba qué fuentes están actualizadas y cuáles requieren revisión.'],
  '/subastas/tipo-interes': ['Tipo hipotecario estimado', 'Suma el diferencial del banco al Euríbor a 12 meses.'],
  '/subastas/calculadora': ['Calculadora de rentabilidad', 'Estima la cuota, el flujo de caja y la rentabilidad de un inmueble.']
};

const campos = {
  provincia: ['Provincia', 'Selecciona la provincia de la consulta. En financiación determina los impuestos aplicables.'],
  localidad: ['Localidad', 'Acota la búsqueda del BOE a un municipio dentro de la provincia.'],
  limite: ['Límite de registros', 'Máximo de registros a consultar o devolver. En subastas se aplica antes de filtrar.'],
  superficie: ['Superficie (m²)', 'Tamaño de la vivienda tipo que se utiliza para estimar alquiler y valor.'],
  entrada_pct: ['Entrada (%)', 'Proporción del precio que aportas con fondos propios.'],
  interes_anual: ['Interés anual (%)', 'Tipo aplicado a la hipoteca. En comparativas, vacíalo para usar Euríbor más diferencial.'],
  anios: ['Plazo (años)', 'Plazo de devolución de la hipoteca usado en la comparativa.'],
  diferencial: ['Diferencial (puntos porcentuales)', 'Margen del banco que se suma al Euríbor cuando se usa un tipo variable.'],
  ciudad: ['Ciudad', 'Selecciona la ciudad cuyos distritos quieres comparar.'],
  precio_max: ['Valor de subasta máximo (€)', 'Descarta las fichas que superen el valor de subasta indicado.'],
  entrada_max: ['Capital necesario máximo (€)', 'Limita el desembolso inicial estimado, incluidos impuestos y gastos.'],
  riesgo_max: ['Riesgo máximo (0–100)', 'Las puntuaciones más altas indican más señales de riesgo.'],
  incluir_cerradas: ['Incluir fichas vencidas', 'Incluye fichas aún listadas por el BOE cuyo plazo ya ha terminado.'],
  solo_analizables: ['Solo fichas analizables', 'Exige que la ficha publique valor de subasta y referencia catastral.'],
  identificador: ['Identificador BOE', 'Referencia con formato SUB-JA-2026-268716. Puedes copiarla de una ficha del BOE.'],
  alquiler_mensual: ['Alquiler mensual bruto (€)', 'Ingreso mensual de alquiler. En el análisis de subasta, vacíalo para dejar que la API lo estime.'],
  precio_compra: ['Precio de compra (€)', 'Importe de adquisición utilizado para calcular financiación, gastos y rentabilidad.'],
  anios_hipoteca: ['Plazo de hipoteca (años)', 'Número de años en los que se devuelve el préstamo.'],
  reforma: ['Presupuesto de reforma (€)', 'Inversión inicial prevista para preparar la vivienda.'],
  vacancia_pct: ['Vacancia (%)', 'Parte del año en la que se estima que la vivienda estará sin alquilar.'],
  irpf_marginal: ['IRPF marginal (%)', 'Tipo marginal empleado en la estimación fiscal del alquiler.'],
  comunidad_mensual: ['Comunidad mensual (€)', 'Cuota mensual de la comunidad de propietarios.'],
  ibi_anual: ['IBI anual (€)', 'Importe anual del Impuesto sobre Bienes Inmuebles.'],
  municipio: ['Municipio', 'Nombre del municipio que se consulta en las fuentes de contexto.'],
  anio_construccion: ['Año de construcción', 'Permite estimar antigüedad y posibles obligaciones de inspección.'],
  codigo_municipio: ['Código INE del municipio', 'Código de cinco dígitos. Conserva el cero inicial cuando corresponda.'],
  codigo_distrito: ['Código INE del distrito', 'Código de siete dígitos del distrito. Déjalo vacío para consultar el municipio.'],
  lat: ['Latitud', 'Coordenada norte-sur en grados decimales, entre −90 y 90.'],
  lon: ['Longitud', 'Coordenada este-oeste en grados decimales, entre −180 y 180.'],
  supuestos: ['Supuestos financieros', 'Activa el grupo para enviar tus propios valores de financiación, gastos e impuestos.']
};

const ejemplos = {
  provincia:'28', localidad:'Madrid', limite:20, superficie:80, entrada_pct:.30,
  interes_anual:.032, anios:25, diferencial:.008, ciudad:'madrid', precio_max:99999.99,
  entrada_max:40000, riesgo_max:75, incluir_cerradas:false, solo_analizables:false,
  identificador:'SUB-JA-2026-268716', alquiler_mensual:750, precio_compra:85000,
  anios_hipoteca:25, reforma:5000, vacancia_pct:.06, irpf_marginal:.30, comunidad_mensual:60,
  ibi_anual:400, municipio:'Madrid', anio_construccion:2000, codigo_municipio:'28079',
  codigo_distrito:'2807904', lat:40.3928, lon:-3.7274
};

const sugerencias = {
  localidad:['Madrid','Barcelona','Bilbao','Sevilla'],
  municipio:['Madrid','Barcelona','Bilbao','Sevilla','Valencia','Málaga'],
  codigo_municipio:['28079','08019','48020','41091','46250','29067'],
  codigo_distrito:['2807904'],
  limite:[5,10,20,30,40,100,200], superficie:[50,65,80,100,120],
  precio_max:[49999.99,74999.99,99999.99,149999.99,199999.99],
  entrada_max:[10000,20000,30000,40000,50000], riesgo_max:[25,50,75,100],
  entrada_pct:[20,25,30,40,50], interes_anual:[2.5,3,3.2,3.5,4],
  diferencial:[0.5,0.8,1,1.25,1.5], anios:[15,20,25,30,35],
  anios_hipoteca:[15,20,25,30,35]
};

const porcentajes = ['entrada_pct','interes_anual','diferencial','vacancia_pct','irpf_marginal'];
const ciudades = [['madrid','Madrid'],['barcelona','Barcelona'],['valencia','Valencia'],['sevilla','Sevilla'],['malaga','Málaga']];
const provinciasPanel = Array.from(document.querySelectorAll('#zona optgroup[label="Provincias"] option'),
  option => [option.value, option.textContent]);
const menuPanel = document.querySelector('#operations');
const detallePanel = document.querySelector('#operation-panel');
const buscadorPanel = document.querySelector('#buscador');

function elemento(etiqueta, texto) {
  const nodo = document.createElement(etiqueta);
  if (texto !== undefined) nodo.textContent = texto;
  return nodo;
}

function montarPanel(spec) {
  function resolver(schema) {
    if (schema.$ref) return spec.components.schemas[schema.$ref.split('/').pop()];
    if (schema.anyOf) return {...resolver(schema.anyOf.find(part => part.type !== 'null')), ...schema};
    return schema;
  }

  let numeroLista = 0;

  function campo(nombre, schema, requerido, padre) {
    const [titulo, ayuda] = campos[nombre] || [nombre, schema.description || 'Valor que se envía a la API.'];
    const etiqueta = elemento('label', titulo + (requerido ? ' *' : ''));
    const escala = porcentajes.includes(nombre) ? 100 : 1;
    const mostrar = valor => typeof valor === 'number' ? Number((valor * escala).toPrecision(12)) :
      typeof valor === 'boolean' ? (valor ? 'Sí' : 'No') : valor;
    const inicial = ejemplos[nombre] ?? schema.default;
    const opciones = nombre === 'provincia' ? provinciasPanel : nombre === 'ciudad' ? ciudades :
      schema.type === 'boolean' ? [['true','Sí'],['false','No']] :
      schema.enum?.map(value => [String(value), String(value)]);
    const input = elemento(opciones ? 'select' : 'input');
    if (opciones) {
      if (!requerido) input.add(new Option('Usar valor de la API', ''));
      for (const [valor, texto] of opciones) input.add(new Option(texto, valor));
      if (inicial != null) input.value = String(inicial);
    } else if (['number','integer'].includes(schema.type)) {
      input.type = 'number';
      const step = schema.type === 'integer' ? 1 : .00001;
      input.step = schema.type === 'integer' ? '1' : 'any';
      const min = schema.minimum ?? (schema.exclusiveMinimum == null ? undefined : schema.exclusiveMinimum + step);
      const max = schema.maximum ?? (schema.exclusiveMaximum == null ? undefined : schema.exclusiveMaximum - step);
      if (min != null) input.min = mostrar(min);
      if (max != null) input.max = mostrar(max);
      if (nombre === 'lat') { input.min = -90; input.max = 90; }
      if (nombre === 'lon') { input.min = -180; input.max = 180; }
      input.value = inicial == null ? '' : mostrar(inicial);
    } else {
      input.type = 'text';
      if (schema.maxLength) input.maxLength = schema.maxLength;
      if (nombre === 'codigo_municipio') input.pattern = '[0-9]{5}';
      if (nombre === 'codigo_distrito') input.pattern = '[0-9]{7}';
      if (nombre === 'identificador') input.pattern = 'SUB-[A-Z]{2}-[0-9]{4}-[0-9]+';
      input.value = inicial ?? '';
    }
    input.name = nombre;
    input.required = requerido;
    const defecto = schema.default == null ? (requerido ? 'Obligatorio.' : 'Opcional.') :
      'Por defecto en la API: ' + mostrar(schema.default) + '.';
    etiqueta.append(input, elemento('small', ayuda + ' ' + defecto));
    if (!opciones && sugerencias[nombre]) {
      const lista = elemento('datalist');
      lista.id = 'sugerencias-' + ++numeroLista;
      input.setAttribute('list', lista.id);
      const disponibles = sugerencias[nombre].filter(valor => typeof valor !== 'number' ||
        ((!input.min || valor >= Number(input.min)) && (!input.max || valor <= Number(input.max))));
      lista.append(...disponibles.map(valor => new Option(String(valor), String(valor))));
      etiqueta.append(lista);
    }
    padre.append(etiqueta);
    return () => {
      const value = input.value.trim();
      if (!value) return undefined;
      if (schema.type === 'boolean') return value === 'true';
      if (['number','integer'].includes(schema.type)) return Number(value) / escala;
      return value;
    };
  }

  function formulario(propiedades, requeridos, padre) {
    const rejilla = elemento('div');
    rejilla.className = 'filters';
    padre.append(rejilla);
    const lectores = Object.entries(propiedades).map(([nombre, raw]) => {
      const schema = resolver(raw);
      if (!schema.properties) return [nombre, campo(nombre, schema, requeridos.includes(nombre), rejilla)];
      const grupo = elemento('fieldset');
      const leyenda = elemento('legend');
      const activar = elemento('input');
      activar.type = 'checkbox';
      activar.checked = true;
      const titulo = elemento('label', campos[nombre][0]);
      titulo.prepend(activar);
      leyenda.append(titulo);
      grupo.append(leyenda, elemento('small', campos[nombre][1]));
      const leer = formulario(schema.properties, schema.required || [], grupo);
      activar.addEventListener('change', () => { grupo.disabled = !activar.checked; });
      padre.append(grupo);
      return [nombre, () => activar.checked ? leer() : undefined];
    });
    return () => Object.fromEntries(lectores.map(([nombre, leer]) => [nombre, leer()])
      .filter(([, value]) => value !== undefined));
  }

  function crearOperacion(path, method, operacion, titulo, ayuda) {
    const cuerpo = elemento('section');
    cuerpo.className = 'results';
    cuerpo.append(elemento('h2', titulo), elemento('p', ayuda), elemento('small', method.toUpperCase() + ' ' + path));
    const form = elemento('form');
    const params = (operacion.parameters || []).filter(param => param.in === 'query');
    const leerQuery = formulario(Object.fromEntries(params.map(param => [param.name, param.schema])),
      params.filter(param => param.required).map(param => param.name), form);
    const esquema = operacion.requestBody?.content['application/json']?.schema;
    const modelo = esquema ? resolver(esquema) : null;
    const leerCuerpo = modelo ? formulario(modelo.properties, modelo.required || [], form) : null;
    const ejecutar = elemento('button', 'Ejecutar consulta');
    ejecutar.type = 'submit';
    form.append(ejecutar);
    const aviso = elemento('p');
    aviso.className = 'note';
    aviso.setAttribute('role', 'status');
    const resultado = elemento('pre');
    resultado.hidden = true;
    const descargar = elemento('a', 'Descargar CSV');
    descargar.hidden = true;
    let enlaceCsv;
    form.addEventListener('submit', async event => {
      event.preventDefault();
      ejecutar.disabled = true;
      aviso.textContent = 'Consultando…';
      resultado.hidden = true;
      descargar.hidden = true;
      if (enlaceCsv) URL.revokeObjectURL(enlaceCsv);
      try {
        const query = new URLSearchParams(leerQuery());
        const peticion = {method: method.toUpperCase()};
        if (leerCuerpo) {
          peticion.headers = {'Content-Type':'application/json'};
          peticion.body = JSON.stringify(leerCuerpo());
        }
        const respuesta = await fetch(path + (query.size ? '?' + query : ''), peticion);
        const tipo = respuesta.headers.get('content-type') || '';
        if (tipo.includes('json')) {
          const datos = await respuesta.json();
          resultado.textContent = JSON.stringify(datos, null, 2);
        } else {
          resultado.textContent = await respuesta.text();
        }
        if (respuesta.ok && tipo.includes('text/csv')) {
          enlaceCsv = URL.createObjectURL(new Blob([resultado.textContent], {type:'text/csv;charset=utf-8'}));
          descargar.href = enlaceCsv;
          descargar.download = 'municipios-que-se-pagan-solos.csv';
          descargar.hidden = false;
        }
        resultado.hidden = false;
        aviso.textContent = respuesta.ok ? 'Consulta completada.' : 'La API devolvió un error HTTP ' + respuesta.status + '.';
      } catch (error) {
        aviso.textContent = 'No se pudo completar la consulta. ' + error.message;
      } finally {
        ejecutar.disabled = false;
      }
    });
    cuerpo.append(form, aviso, descargar, resultado);
    return cuerpo;
  }

  const tabBuscador = menuPanel.querySelector('button');
  function seleccionar(tab, contenido) {
    for (const item of menuPanel.querySelectorAll('[role="tab"]')) {
      item.setAttribute('aria-selected', String(item === tab));
      item.tabIndex = item === tab ? 0 : -1;
    }
    buscadorPanel.hidden = Boolean(contenido);
    detallePanel.hidden = !contenido;
    if (contenido) {
      detallePanel.setAttribute('aria-labelledby', tab.id);
      detallePanel.replaceChildren(contenido);
    }
  }
  tabBuscador.addEventListener('click', () => seleccionar(tabBuscador, null));

  for (const [path, metodos] of Object.entries(spec.paths)) {
    for (const [method, operation] of Object.entries(metodos)) {
      if (!['get','post','put','patch','delete'].includes(method)) continue;
      const [titulo, ayuda] = operaciones[path] || [operation.summary, operation.description || ''];
      const tab = elemento('button', titulo);
      tab.type = 'button';
      tab.id = 'operacion-' + operation.operationId;
      tab.tabIndex = -1;
      tab.setAttribute('role', 'tab');
      tab.setAttribute('aria-selected', 'false');
      tab.setAttribute('aria-controls', detallePanel.id);
      const contenido = crearOperacion(path, method, operation, titulo, ayuda);
      tab.addEventListener('click', () => seleccionar(tab, contenido));
      menuPanel.append(tab);
    }
  }

  menuPanel.addEventListener('keydown', event => {
    const tabs = Array.from(menuPanel.querySelectorAll('[role="tab"]'));
    const actual = tabs.indexOf(event.target);
    const destinos = {ArrowRight:(actual + 1) % tabs.length, ArrowLeft:(actual + tabs.length - 1) % tabs.length,
      Home:0, End:tabs.length - 1};
    if (actual < 0 || !(event.key in destinos)) return;
    event.preventDefault();
    const tab = tabs[destinos[event.key]];
    tab.focus();
    tab.click();
  });
}

fetch('/openapi.json')
  .then(response => {
    if (!response.ok) throw new Error('HTTP ' + response.status);
    return response.json();
  })
  .then(montarPanel)
  .catch(error => {
    document.querySelector('#panel-status').textContent = 'No se pudieron cargar las operaciones. ' + error.message;
  });
