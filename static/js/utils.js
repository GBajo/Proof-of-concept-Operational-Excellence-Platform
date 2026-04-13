// Utilidades compartidas

/**
 * Formatea un número con separador de miles.
 * @param {number} n
 * @returns {string}
 */
function formatNumber(n) {
  if (n === null || n === undefined) return '—';
  const locale = document.documentElement.lang === 'en' ? 'en-US' : 'es-ES';
  return Number(n).toLocaleString(locale);
}

/**
 * Formatea un porcentaje con un decimal.
 * @param {number} n
 * @returns {string}
 */
function formatPct(n) {
  if (n === null || n === undefined) return '—';
  return Number(n).toFixed(1);
}

/**
 * Devuelve la hora HH:MM de una cadena ISO.
 * @param {string} iso
 * @returns {string}
 */
function isoToTime(iso) {
  if (!iso) return '';
  // Usar Date para parsear correctamente independientemente del formato ISO
  try {
    const d = new Date(iso.replace(' ', 'T'));
    if (isNaN(d.getTime())) throw new Error('invalid date');
    return d.toLocaleTimeString('es-ES', { hour: '2-digit', minute: '2-digit', hour12: false });
  } catch {
    // Fallback: extracción posicional para formato YYYY-MM-DD HH:MM:SS
    return iso.replace('T', ' ').substring(11, 16);
  }
}

/**
 * Etiqueta de categoría en español.
 * @param {string} cat
 * @returns {string}
 */
function categoryLabel(cat) {
  const isEn = document.documentElement.lang === 'en';
  const map = {
    safety:      isEn ? 'Safety'       : 'Seguridad',
    quality:     isEn ? 'Quality'      : 'Calidad',
    production:  isEn ? 'Production'   : 'Producción',
    maintenance: isEn ? 'Maintenance'  : 'Mantenimiento',
  };
  return map[cat] || cat;
}

/**
 * Clase CSS de badge por categoría.
 * @param {string} cat
 * @returns {string}
 */
function categoryBadgeClass(cat) {
  const map = {
    safety: 'badge--red',
    quality: 'badge--orange',
    production: 'badge--blue',
    maintenance: 'badge--gray',
  };
  return map[cat] || 'badge--gray';
}
