# PackLine Operator Assistant

## Project overview
Web application for packaging line operators in a pharmaceutical manufacturing plant.
Helps manage shift handovers and captures voice-based operator comments throughout the shift.
Displays real-time production KPIs and line performance dashboards.

## Tech stack
- **Backend:** Python 3.12 + Flask
- **Database:** SQLite (prototype phase)
- **Frontend:** HTML/CSS/JS (no frontend framework, keep it simple)
- **Voice:** Web Speech API (browser-native, no external services)
- **Charts:** Chart.js via CDN

## Architecture
- Single Flask application with Jinja2 templates
- RESTful API endpoints returning JSON for dashboard updates
- SQLite database for shifts, comments, and KPI data
- Browser-based speech recognition (Web Speech API)
- Auto-refresh dashboards using JavaScript fetch polling

## Key features (priority order)
1. **Shift management** — Start/end shift, operator name, line assignment, shift handover notes
2. **Voice comments** — Record operator comments via microphone, transcribe to text, tag with timestamp and operator
3. **KPI dashboard** — OEE, units produced, downtime, line speed, reject rate
4. **Shift summary** — Auto-generated summary of all comments and KPIs at shift end

## Coding conventions
- Python: snake_case for functions and variables, PascalCase for classes
- Comments and UI text in Spanish (this is for a Spanish plant)
- All API responses in JSON format
- Use type hints in Python functions
- Keep HTML templates in templates/ directory
- Keep static files (CSS, JS) in static/ directory

## Database tables (initial design)
- **operators** — id, name, role, badge_number
- **shifts** — id, operator_id, line_number, start_time, end_time, status, handover_notes
- **comments** — id, shift_id, operator_id, text, timestamp, category (safety/quality/production/maintenance)
- **kpi_readings** — id, shift_id, timestamp, units_produced, units_rejected, downtime_minutes, line_speed

## KPIs to display
- **OEE** (Overall Equipment Effectiveness) = Availability × Performance × Quality
- **Units produced** vs target
- **Reject rate** (%)
- **Downtime** (minutes and %)
- **Line speed** (units/hour, current vs nominal)
- **Right First Time** (%)

## Important constraints
- Prototype/demo only — use sample data, no real production systems
- Voice recognition uses browser Web Speech API (Chrome recommended)
- Single-user prototype (no authentication needed for now)
- All data stored locally in SQLite
- Must work in GitHub Codespaces

## Asistente inteligente (RAG)
- La app conecta con el LLM Gateway de Lilly para generar sugerencias
- Endpoint del gateway: https://lilly-code.gateway.llm.lilly.com (o el que corresponda)
- Los documentos de contexto (SOPs, manuales, errores) se almacenan en una carpeta docs/
- Se extraen, fragmentan e indexan en SQLite para búsqueda por palabras clave
- Formatos soportados: PDF, Word (.docx), Excel (.xlsx), enlaces web
- El sistema busca fragmentos relevantes al comentario del operador y los envía al LLM junto con el comentario
- Dos modos de activación: automático (tras cada comentario) y manual (botón "Pedir ayuda")
- Las respuestas del LLM se muestran como sugerencias, siempre referenciando el documento fuente