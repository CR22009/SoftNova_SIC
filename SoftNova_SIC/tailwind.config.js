/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    './templates/**/*.html', // Escanea archivos HTML en la carpeta templates
    './contabilidad/templates/**/*.html', // Escanea archivos de la app
    './core/templates/**/*.html', // Si tienes una app 'core'
  ],
  theme: {
    extend: {
      colors: {
        // Paleta de colores personalizada para SoftNova_SIC
        'sic-dark-blue': '#000B58',
        'sic-medium-blue': '#003161',
        'sic-teal': '#006A67',
        'sic-light-teal': '#3B9797',
      }
    },
  },
  plugins: [
    require('@tailwindcss/forms'), // Plugin útil para estilos de formularios
  ],
}