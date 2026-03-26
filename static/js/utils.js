// Utilidades compartidas

/**
 * Formatea un número con separador de miles.
 * @param {number} n
 * @returns {string}
 */
function formatNumber(n) {
  if (n === null || n === undefined) return '—';
  return Number(n).toLocaleString('es-ES');
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
  return iso.replace('T', ' ').substring(11, 16);
}

/**
 * Etiqueta de categoría en español.
 * @param {string} cat
 * @returns {string}
 */
function categoryLabel(cat) {
  const map = {
    safety: 'Seguridad',
    quality: 'Calidad',
    production: 'Producción',
    maintenance: 'Mantenimiento',
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
