# 🚀 QUICK REFERENCE - Metrics & Alerts API

## Endpoints de Métricas

### GET /api/metrics/{asset_id}/metrics
Obtiene el snapshot de métricas más reciente para un activo.

**Requerimientos**:
- `Authorization: Bearer TOKEN`
- Rol: VIEWER, ANALYST, o ADMIN

**Respuesta** (200 OK):
```json
{
  "id": 1,
  "asset_id": 100,
  "as_of": "2024-01-15T10:30:00Z",
  "metrics": {
    "sma20": 150.25,
    "rsi14": 65.3,
    "volatility": 0.0245,
    "max_drawdown": -0.0812,
    "momentum": 0.0356,
    "last_price": 151.80
  },
  "quality": {"bars_count": 252, "low_data": false},
  "explain": {},
  "created_at": "2024-01-15T10:30:00Z"
}
```

---

### POST /api/metrics/{asset_id}/metrics/recompute
Recalcula todas las métricas para un activo.

**Requerimientos**:
- `Authorization: Bearer TOKEN`
- Rol: ANALYST o ADMIN

**Parámetros**:
- `asset_id` (path): ID del activo

**Respuesta** (200 OK):
- Retorna el nuevo snapshot calculado

---

## Endpoints de Alertas

### GET /api/alerts
Lista todas las alertas con filtros opcionales.

**Requerimientos**:
- `Authorization: Bearer TOKEN`
- Rol: VIEWER, ANALYST, o ADMIN

**Parámetros de Query**:
- `asset_id` (int, optional): Filtrar por activo
- `severity` (string, optional): "info", "warning", o "critical"
- `active` (bool, default: true): Solo alertas no resueltas
- `skip` (int, default: 0): Paginación
- `limit` (int, default: 50, max: 500): Paginación

**Respuesta** (200 OK):
```json
[
  {
    "id": 1,
    "asset_id": 100,
    "key": "rsi_high",
    "severity": "warning",
    "message": "RSI14 is high (75.2)",
    "triggered_at": "2024-01-15T10:25:00Z",
    "resolved_at": null,
    "payload": {"rsi": 75.2}
  }
]
```

---

### POST /api/alerts/{alert_id}/resolve
Marca una alerta como resuelta.

**Requerimientos**:
- `Authorization: Bearer TOKEN`
- Rol: ANALYST o ADMIN

**Parámetros**:
- `alert_id` (path): ID de la alerta

**Respuesta** (200 OK):
- Retorna la alerta actualizada

---

## Tipos de Alertas Automáticas

| Clave | Severidad | Condición | Notas |
|-------|-----------|-----------|-------|
| rsi_high | warning | RSI14 > 70 | Posible sobreventa |
| rsi_low | warning | RSI14 < 30 | Posible sobrecarga |
| drawdown_alert | critical | Max DD < -15% | Caída significativa |
| high_volatility | info | Volatilidad > 5% | Información |
| low_data | warning | < 20 barras | Datos insuficientes |

---

## Disponibilidad de Datos

Los endpoints requieren:
1. **Datos de precios**: Cargados vía `ingest.py` o API de ingesta
2. **Mínimo 20 barras**: Para cálculos confiables de métricas
3. **Activos activos**: Solo activos con `is_active=true`

---

## Ejemplos cURL

### Obtener métricas
```bash
curl -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  http://localhost:8000/api/metrics/1/metrics
```

### Listar alertas críticas
```bash
curl -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  "http://localhost:8000/api/alerts?severity=critical&active=true"
```

### Listar alertas por activo
```bash
curl -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  "http://localhost:8000/api/alerts?asset_id=100"
```

### Resolver alerta
```bash
curl -X POST -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  http://localhost:8000/api/alerts/5/resolve
```

---

## Errores Comunes

| Código | Descripción | Solución |
|--------|-------------|----------|
| 404 | Activo no encontrado | Verificar que el asset_id existe |
| 404 | No metrics snapshot | Ejecutar `/metrics/{id}/metrics/recompute` |
| 403 | Access denied | Verificar rol de usuario |
| 401 | Unauthorized | Proporcionar token JWT válido |
| 400 | Bad request | Verificar parámetros |

---

## Control de Acceso (RBAC)

### Roles Disponibles
- **viewer**: Solo lectura (GET)
- **analyst**: Lectura + Modificación (GET, POST)
- **admin**: Control total

### Matriz de Permisos

| Endpoint | viewer | analyst | admin |
|----------|--------|---------|-------|
| GET /api/metrics/{id}/metrics | ✓ | ✓ | ✓ |
| POST /api/metrics/{id}/metrics/recompute | ✗ | ✓ | ✓ |
| GET /api/alerts | ✓ | ✓ | ✓ |
| POST /api/alerts/{id}/resolve | ✗ | ✓ | ✓ |
| POST /api/alerts/recompute | ✗ | ✓ | ✓ |

---

## Configuración y Límites

- **Rate Limit**: 100 solicitudes/minuto por IP
- **Pagination**: Máximo 500 resultados por página
- **Cache**: Snapshots se cachean por 15 minutos
- **Timeout**: 30 segundos por solicitud

---

## Debugging

### Ver documentación interactiva
```bash
# En modo DEBUG
curl http://localhost:8000/docs
```

### Verificar status del sistema
```bash
curl http://localhost:8000/health
```

### Ver configuración actual
```bash
curl http://localhost:8000/api/config
```

---

## Links Útiles

- [Documentación Completa](./CONVERGENCE_COMPLETE_GUIDE.md)
- [Informe Final](./CONVERGENCE_FINAL_REPORT.md)
- [Resumen de Cambios](./CONVERGENCE_SUMMARY.md)
- [Dashboard de Estado](./CONVERGENCE_STATUS.txt)

---

**Última actualización**: 2024-01-XX
**Versión**: 1.0.0
