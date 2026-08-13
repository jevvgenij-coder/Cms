# Vercel Speed Insights Setup

This document describes how Vercel Speed Insights has been integrated into this Flask application.

## What is Speed Insights?

Vercel Speed Insights is a performance monitoring tool that automatically tracks Core Web Vitals and other performance metrics for your website. It provides real-time insights into your application's performance.

## Installation

The following components have been added to enable Speed Insights:

### 1. NPM Package Installation

- **Package**: `@vercel/speed-insights` v1.0.0+
- **File**: `package.json` - Contains the Speed Insights dependency
- **Lock file**: `package-lock.json` - Ensures consistent dependency versions

### 2. Integration Files

#### `static/speed-insights.js`
A browser-compatible JavaScript file that initializes Speed Insights tracking. This file:
- Checks if the application is running in development or production
- Only enables tracking in production (when deployed to Vercel)
- Loads the Vercel Speed Insights tracking script from `/_vercel/speed-insights/script.js`
- Handles errors gracefully if the script cannot be loaded

#### `templates/base.html`
Updated to include the Speed Insights script in the `<head>` section:
```html
<script defer src="{{ url_for('static', filename='speed-insights.js') }}"></script>
```

### 3. Build Script (Optional)

`build-speed-insights.js` - A Node.js script that can bundle the Speed Insights package for more advanced use cases.

## How It Works

1. **In Development**: Speed Insights tracking is automatically disabled when running on localhost or development domains. This prevents development traffic from affecting your production analytics.

2. **In Production**: When deployed to Vercel:
   - The Speed Insights script is loaded from Vercel's CDN
   - Core Web Vitals (LCP, FID, CLS, etc.) are automatically tracked
   - Performance metrics are sent to your Vercel dashboard
   - Data appears in the Speed Insights tab of your project

## Enabling Speed Insights on Vercel

To start collecting metrics, you need to:

1. **Deploy to Vercel**: Push your code and deploy to Vercel
2. **Enable Speed Insights**: 
   - Go to your project dashboard on Vercel
   - Navigate to the "Speed Insights" tab
   - Enable Speed Insights for your project
3. **Redeploy**: After enabling, redeploy your application
4. **View Metrics**: Data will start appearing in your dashboard after real users visit your site

## Configuration

The Speed Insights implementation uses default configuration, which includes:
- Automatic Core Web Vitals tracking
- Real User Monitoring (RUM)
- No custom configuration required

For advanced configuration options, refer to the [Vercel Speed Insights documentation](https://vercel.com/docs/speed-insights).

## Testing

To test that Speed Insights is working:

1. Deploy your application to Vercel
2. Enable Speed Insights in the dashboard
3. Visit your deployed site
4. Open browser DevTools Console
5. Look for the Speed Insights script being loaded from `/_vercel/speed-insights/script.js`

## Files Modified

- `templates/base.html` - Added Speed Insights script tag
- `static/speed-insights.js` - Created Speed Insights initialization script
- `package.json` - Added @vercel/speed-insights dependency
- `package-lock.json` - Generated lock file for npm dependencies

## Troubleshooting

**Script not loading in development**: This is expected behavior. Speed Insights only tracks in production.

**No data in dashboard**: 
- Ensure Speed Insights is enabled in your Vercel project settings
- Verify the application is deployed and receiving traffic
- Check browser console for any error messages

**Script fails to load**: If deployed outside of Vercel, the `/_vercel/speed-insights/script.js` endpoint won't be available. Speed Insights is specifically designed for Vercel deployments.

## Documentation

- [Speed Insights Quickstart](https://vercel.com/docs/speed-insights/quickstart)
- [Speed Insights Package](https://vercel.com/docs/speed-insights/package)
- [@vercel/speed-insights on npm](https://www.npmjs.com/package/@vercel/speed-insights)

## Support

For issues or questions about Speed Insights:
- [Vercel Documentation](https://vercel.com/docs)
- [Vercel Support](https://vercel.com/support)
