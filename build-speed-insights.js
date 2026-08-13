/**
 * Build script to bundle Vercel Speed Insights for static deployment
 * This creates a standalone JavaScript file that can be served from the static directory
 */

const fs = require('fs');
const path = require('path');

// Read the Speed Insights module
const speedInsightsPath = path.join(__dirname, 'node_modules', '@vercel', 'speed-insights', 'dist', 'index.js');
const speedInsightsCode = fs.readFileSync(speedInsightsPath, 'utf8');

// Create a wrapper that initializes Speed Insights on page load
const wrapper = `
/**
 * Vercel Speed Insights - Bundled for Static Deployment
 * Auto-generated from @vercel/speed-insights package
 */

// Speed Insights module code
${speedInsightsCode}

// Auto-initialize on page load
(function() {
  'use strict';
  
  function init() {
    try {
      // Check if running in development
      const isDev = window.location.hostname === 'localhost' || 
                    window.location.hostname === '127.0.0.1' ||
                    window.location.hostname.includes('dev');
      
      if (isDev) {
        console.log('[Speed Insights] Development mode - tracking disabled');
        return;
      }
      
      // Initialize Speed Insights using the inject function from the module
      if (typeof module !== 'undefined' && module.exports && module.exports.injectSpeedInsights) {
        module.exports.injectSpeedInsights({
          debug: false
        });
      }
    } catch (error) {
      console.error('[Speed Insights] Initialization error:', error);
    }
  }
  
  // Run when DOM is ready
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
`;

// Write the bundled file
const outputPath = path.join(__dirname, 'static', 'speed-insights.js');
fs.writeFileSync(outputPath, wrapper, 'utf8');

console.log('✓ Speed Insights bundle created at:', outputPath);
