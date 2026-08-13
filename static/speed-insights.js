/**
 * Vercel Speed Insights Integration for Flask/HTML Application
 * 
 * This script initializes Vercel Speed Insights tracking.
 * Speed Insights automatically tracks Core Web Vitals and performance metrics.
 * 
 * The script will only track in production (when deployed to Vercel).
 * In development (localhost), tracking is disabled.
 * 
 * Documentation: https://vercel.com/docs/speed-insights
 */

(function() {
  'use strict';
  
  /**
   * Check if we're in a development environment
   */
  function isDevelopment() {
    const hostname = window.location.hostname;
    return hostname === 'localhost' || 
           hostname === '127.0.0.1' || 
           hostname.includes('.local') ||
           hostname.includes('dev.');
  }
  
  /**
   * Initialize Speed Insights queue
   * This queue collects events before the main script loads
   */
  function initQueue() {
    if (window.si) return;
    
    window.si = function() {
      (window.siq = window.siq || []).push(arguments);
    };
  }
  
  /**
   * Load the Vercel Speed Insights tracking script
   */
  function loadSpeedInsights() {
    // Don't track in development
    if (isDevelopment()) {
      console.log('[Speed Insights] Development environment detected - tracking disabled');
      return;
    }
    
    // Initialize the queue
    initQueue();
    
    // Load the tracking script from Vercel's CDN
    // When deployed to Vercel, this path is automatically available
    const script = document.createElement('script');
    script.defer = true;
    script.src = '/_vercel/speed-insights/script.js';
    
    script.onerror = function() {
      console.warn('[Speed Insights] Could not load tracking script. This is expected in non-Vercel environments.');
    };
    
    script.onload = function() {
      console.log('[Speed Insights] Tracking initialized');
    };
    
    // Add script to page
    const firstScript = document.getElementsByTagName('script')[0];
    if (firstScript && firstScript.parentNode) {
      firstScript.parentNode.insertBefore(script, firstScript);
    } else {
      document.head.appendChild(script);
    }
  }
  
  /**
   * Initialize when DOM is ready
   */
  function init() {
    if (document.readyState === 'loading') {
      document.addEventListener('DOMContentLoaded', loadSpeedInsights);
    } else {
      loadSpeedInsights();
    }
  }
  
  // Start initialization
  init();
  
})();
