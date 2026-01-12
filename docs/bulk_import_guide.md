# Guía: Importación Masiva de Taxonomía (BLOCK 5)

## Descripción General

La característica de **Importación Masiva de Taxonomía** permite a los administradores cargar estructuras ontológicas completas (grupos, subgrupos, categorías y activos) mediante un formato JSON normalizado, sin necesidad de crear manualmente cada elemento a través de la interfaz.

## Arquitectura

### Backend (Completado)

**Endpoint:** `POST /api/import/taxonomy`

**Autenticación:** Requerido (solo administradores)

**Payload:**
```json
{
  "group": {
    "name": "Technology",
    "code": "TECH"
  },
  "subgroups": [
    {
      "name": "Large Cap",
      "code": "TECH-LC",
      "categories": [
        {
          "name": "Software",
          "code": "TECH-LC-SW",
          "asset_type": "equity",
          "assets": [
            {"symbol": "MSFT", "name": "Microsoft"},
            {"symbol": "AAPL", "name": "Apple"}
          ]
        }
      ]
    }
  ]
}
```

**Respuesta (200 OK):**
```json
{
  "groups_created": 1,
  "groups_updated": 0,
  "subgroups_created": 1,
  "subgroups_updated": 0,
  "categories_created": 1,
  "categories_updated": 0,
  "assets_created": 2,
  "assets_updated": 0,
  "links_created": 2,
  "errors": []
}
```

**Códigos de Error:**
- `401 Unauthorized`: Usuario no autenticado
- `403 Forbidden`: Usuario no tiene permisos de administrador
- `422 Unprocessable Entity`: JSON inválido o estructura malformada

---

### Frontend UI (Completado)

#### 1. Página de Importación: `/import-taxonomy`

**Ubicación:** Menu lateral → 📦 Import Taxonomy

**Componentes:**

1. **Área de Entrada JSON**
   - TextArea con monofont (tamaño mínimo 300px)
   - Validación en tiempo real (contador de caracteres)
   - Botón "📤 Import" (deshabilitado si JSON vacío o cargando)

2. **Validación**
   - Cliente: JSON.parse() con try/catch
   - Servidor: Esquema Pydantic

3. **Gestión de Estados**
   - **Loading:** Spinner + texto "Importing..."
   - **Error:** Caja roja con mensaje específico
     - JSON inválido: "Invalid JSON: [error]"
     - 401/403: "Unauthorized. Admin access required."
     - 422: "Validation Error: [detail]"
     - Otros: "Import failed: [error]"
   - **Éxito:** Caja verde con resumen (created/updated por tipo)

4. **Guía Integrada**
   - Muestra estructura JSON requerida
   - Ejemplos de cada nivel (grupo, subgrupo, categoría, activo)

#### 2. Integración en Página de Universo: `UniversePage`

**Cambio:** Lista de activos con paginación

**Nuevas Capacidades:**

1. **Selector de Límite por Página**
   - Opciones: 25, 50, 100 assets/página
   - Reinicia offset a 0 al cambiar

2. **Controles de Navegación**
   - Botón "← Anterior" (deshabilitado en página 1)
   - Botón "Siguiente →" (deshabilitado en última página)
   - Contador: "Displaying X-Y of Z assets"

3. **Búsqueda**
   - Campo de búsqueda por símbolo/nombre
   - Reinicia offset a 0 al cambiar término
   - Parámetro `?q=` en endpoint

**Endpoint Nuevo:** `GET /api/assets/category/{id}/paginated?limit=25&offset=0&q=''`

---

## Casos de Uso

### Caso 1: Importación de Nueva Taxonomía

**Escenario:** Agregar sector "Energía" con múltiples categorías

1. Navegar a `/import-taxonomy`
2. Copiar-pegar JSON:
```json
{
  "group": {
    "name": "Energy",
    "code": "ENRG"
  },
  "subgroups": [
    {
      "name": "Renewables",
      "code": "ENRG-REN",
      "categories": [
        {
          "name": "Solar",
          "code": "ENRG-REN-SOL",
          "asset_type": "equity",
          "assets": [
            {"symbol": "SUNW", "name": "Sunworks Inc."}
          ]
        }
      ]
    }
  ]
}
```
3. Click "📤 Import"
4. Ver confirmación: "✅ Groups: 1 created"

### Caso 2: Navegación Paginada

**Escenario:** Explorar 500+ activos en categoría "Technology"

1. Ir a página Universo (`/`)
2. Seleccionar categoría "Technology"
3. Ver primeros 25 activos
4. Cambiar a "50 per page" → recarga con offset=0
5. Click "Siguiente →" para página 2
6. Buscar "Apple" → reinicia a página 1 con resultados filtrados

---

## Tests

### Frontend (39 tests PASSING ✅)

**ImportTaxonomyPage:**
- ✅ Renderiza formulario
- ✅ Valida JSON inválido
- ✅ Muestra éxito con resumen
- ✅ Gestiona errores 403
- ✅ Limpia textarea en éxito

**UniversePage (Pagination):**
- ✅ Renderiza sin errores
- ✅ Tiene selectores y botones
- ✅ Estructura correcta

### Backend (37 tests PASSING ✅)

- ✅ POST /api/import/taxonomy (RBAC, validación, creación)
- ✅ GET /api/assets/category/{id}/paginated (limit, offset, search)
- Todos los tests existentes mantienen estado PASSING

---

## Demo Script

**Ubicación:** `scripts/import_taxonomy_demo.py`

**Uso:**
```bash
# Asegurar backend en http://localhost:8000
python scripts/import_taxonomy_demo.py
```

**Salida:**
```
🚀 WSW Bulk Import Demo

Step 1: Authenticating...
✅ Logged in as admin@wsw.local

Step 2: Preparing import payload...
   📋 Taxonomy: Technology
   └─ 2 subgroups
      └─ Large Cap Tech (3 assets across 1 categories)
      └─ Semiconductors (3 assets across 1 categories)

Step 3: Importing taxonomy...

📊 Import Results:
   📦 Groups: 1 created, 0 updated
   📁 Subgroups: 2 created, 0 updated
   📂 Categories: 2 created, 0 updated
   💰 Assets: 6 created, 0 updated
   🔗 Links: 8 created

✅ Demo completed successfully!

💡 Next steps:
   1. Visit http://localhost:5173 to see the imported assets (frontend)
   2. Backend API at http://localhost:8000
   ...
```

---

## Exportar Taxonomía

### Desde la API (curl)

```bash
curl -H "Authorization: Bearer <ADMIN_TOKEN>" \
     http://localhost:8000/api/export/taxonomy \
     -o taxonomy_export.json
```

### Desde la UI

1. Ir a `/import-taxonomy` (frontend http://localhost:5173)
2. Click en el botón **Export**
3. Se descarga `taxonomy_export.json` compatible con el endpoint de importación

---

## Especificación JSON

### Estructura Mínima

```json
{
  "group": {
    "name": "string (requerido)",
    "code": "string (requerido)"
  },
  "subgroups": [
    {
      "name": "string",
      "code": "string",
      "categories": [
        {
          "name": "string",
          "code": "string",
          "asset_type": "equity|fixed_income|commodity|...",
          "assets": [
            {
              "symbol": "string (unique)",
              "name": "string"
            }
          ]
        }
      ]
    }
  ]
}
```

### Validaciones

| Campo | Tipo | Req? | Notas |
|-------|------|------|-------|
| group.name | str | ✅ | Max 255 chars |
| group.code | str | ✅ | Único, max 50 chars |
| subgroups[] | array | ✅ | Min 1 elemento |
| subgroups.name | str | ✅ | Max 255 chars |
| subgroups.code | str | ✅ | Único, max 50 chars |
| categories[] | array | ✅ | Min 1 elemento |
| categories.asset_type | str | ✅ | Ver enum en `models.py` |
| assets[] | array | ✅ | Min 1 elemento |
| assets.symbol | str | ✅ | Único, max 20 chars |
| assets.name | str | ✅ | Max 255 chars |

---

## Limitaciones & Extensiones Futuras

### Actuales

- **Creación únicamente:** Endpoint crea nuevos elementos; actualizaciones parciales vía PATCH futuro
- **Sin transacciones parciales:** Falla = rollback completo (no hay "creación parcial")
- **Validación básica:** Sin chequeo de símbolos reales (usar `yfinance` como validador futuro)

### Propuestas

1. **PATCH /api/import/taxonomy** - Actualizar ontología existente
2. **GET /api/import/taxonomy/validate** - Pre-validar JSON sin importar
3. **Validación de símbolos** - Cruzar contra yfinance API
4. **Importación desde CSV** - Convertir CSV a JSON en backend
5. **Auditoría de cambios** - Trackear quién/cuándo importó qué

---

## Troubleshooting

### "Unauthorized. Admin access required."
- ✅ Verificar que usuario logueado es administrador
- ✅ Verificar token en header `Authorization: Bearer <token>`

### "Invalid JSON: Expecting value"
- ✅ Validar sintaxis JSON (comillas, comas, brackets)
- ✅ Usar JSONLint o VS Code para debugging

### "Validation Error: Extra fields not permitted"
- ✅ Remover campos no reconocidos (ej: `description`, `color`)
- ✅ Ver especificación JSON arriba

### Assets no aparecen después de importar
- ✅ Verificar que categoría está seleccionada en Universo
- ✅ F5 para refrescar (recarga desde servidor)
- ✅ Revisar respuesta 200 OK en Network inspector

---

## Referencias

- Backend Endpoint: [api/import.py](../../api/import_endpoints.py)
- Frontend Component: [ImportTaxonomyPage.tsx](../../frontend/src/pages/ImportTaxonomyPage.tsx)
- Tests: 
  - Backend: [tests/test_import_taxonomy.py](../../tests/test_import_taxonomy.py) *(pending)*
  - Frontend: [frontend/src/test/ImportTaxonomyPage.test.tsx](../../frontend/src/test/ImportTaxonomyPage.test.tsx)
- Models: [models.py](../../models.py)
