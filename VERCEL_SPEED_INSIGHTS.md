# Vercel Speed Insights Integration

This document explains how Vercel Speed Insights has been integrated into this Flask application.

## What is Vercel Speed Insights?

Vercel Speed Insights is a tool that tracks real-world performance metrics (Web Vitals) for your web application. It measures:

- **FID (First Input Delay)**: Time from when a user first interacts with your page to when the browser responds
- **LCP (Largest Contentful Paint)**: Time it takes for the largest content element to become visible
- **CLS (Cumulative Layout Shift)**: Measures visual stability by tracking unexpected layout shifts
- **TTFB (Time to First Byte)**: Time from navigation to receiving the first byte of content
- **FCP (First Contentful Paint)**: Time from navigation to the first piece of content being rendered

## Implementation Details

### Files Modified

1. **templates/base.html**
   - Added Speed Insights script initialization in the `<head>` section
   - Script only loads when `VERCEL_ANALYTICS_ID` environment variable is present
   - Uses the official Vercel Speed Insights script path: `/_vercel/speed-insights/script.js`

2. **frontend/index.html**
   - Added Speed Insights script initialization for standalone frontend page
   - Uses the same script loading mechanism

3. **app.py**
   - Updated the `inject_user()` context processor to inject `vercel_analytics_id` into all templates
   - This makes the analytics ID available throughout the application

4. **.env.example**
   - Created example environment file documenting the `VERCEL_ANALYTICS_ID` variable

5. **README.md**
   - Added documentation about Speed Insights setup and configuration

## How It Works

The implementation follows Vercel's recommended approach for non-Node.js applications:

1. **Script Initialization**: A minimal JavaScript snippet initializes the Speed Insights queue:
   ```javascript
   window.si = window.si || function () { (window.siq = window.siq || []).push(arguments); };
   ```

2. **Script Loading**: The actual Speed Insights script is loaded asynchronously from Vercel's CDN:
   ```html
   <script defer src="/_vercel/speed-insights/script.js"></script>
   ```

3. **Automatic Tracking**: Once loaded, the script automatically:
   - Measures Web Vitals metrics
   - Sends data to Vercel's analytics endpoint
   - Reports metrics in your Vercel dashboard

## Setup Instructions

### Step 1: Deploy to Vercel

Deploy this application to Vercel using one of these methods:

- Connect your Git repository to Vercel for automatic deployments
- Use the Vercel CLI: `vercel deploy`

### Step 2: Enable Speed Insights

1. Log in to your Vercel dashboard
2. Navigate to your project
3. Go to the "Speed Insights" section
4. Click the "Enable" button

### Step 3: Wait for Data

After enabling Speed Insights:

1. The `VERCEL_ANALYTICS_ID` environment variable is automatically set by Vercel
2. The Speed Insights scripts will automatically load on your pages
3. Visit your deployed site to generate some traffic
4. Performance metrics will appear in the Vercel dashboard within a few minutes

## Environment Variables

### VERCEL_ANALYTICS_ID

- **Type**: String
- **Required**: No (optional, automatically set by Vercel)
- **Description**: Unique identifier for your Vercel project's analytics
- **Set by**: Vercel platform (automatic when Speed Insights is enabled)
- **Used for**: Authenticating metric submissions to Vercel's analytics API

When running locally without this variable, the Speed Insights scripts simply won't load (no errors or warnings).

## Local Development

Speed Insights is designed for production use on Vercel. When running locally:

- The scripts won't load if `VERCEL_ANALYTICS_ID` is not set
- No metrics will be collected or sent
- Your application functions normally without any performance impact

To test the integration locally, you can manually set the environment variable, but metrics will only be properly collected and displayed when deployed to Vercel.

## Verification

To verify Speed Insights is working:

1. **Check the HTML source**: View the page source of your deployed site and look for:
   ```html
   <script defer src="/_vercel/speed-insights/script.js"></script>
   ```

2. **Check browser DevTools**: Open the Network tab and look for requests to:
   - `/_vercel/speed-insights/script.js`
   - `vitals.vercel-analytics.com` (for metric submission)

3. **Check Vercel Dashboard**: After some traffic, metrics should appear in the Speed Insights section of your Vercel project dashboard

## Performance Impact

Speed Insights is designed to have minimal performance impact:

- **Script size**: ~2-3 KB gzipped
- **Loading**: Asynchronous with `defer` attribute
- **Execution**: Non-blocking, runs after page load
- **Network**: Metrics sent using `navigator.sendBeacon()` for reliability

## Privacy & Data

Speed Insights collects:
- Performance metrics (Web Vitals)
- Page URLs
- User agent information
- Geographic location (country level)

It does NOT collect:
- Personal user information
- Form data
- Cookies (beyond necessary analytics)

Data is aggregated and displayed in your Vercel dashboard for analysis.

## Troubleshooting

### Metrics not appearing

1. **Check if Speed Insights is enabled** in your Vercel project settings
2. **Verify the environment variable** is set: Check Vercel project settings → Environment Variables
3. **Wait for traffic**: You need actual user visits to generate metrics
4. **Check deployment status**: Ensure your latest deployment includes the Speed Insights integration

### Script not loading

1. **Check browser console** for any error messages
2. **Verify the template context**: The `vercel_analytics_id` should be present when viewing page source
3. **Check network tab**: Look for the script request in browser DevTools

### Local development issues

Speed Insights is meant for production use. If you need to test locally:
1. Set `VERCEL_ANALYTICS_ID` in your local environment (copy from Vercel dashboard)
2. Note that metrics may not display correctly since they're designed for Vercel's infrastructure

## Additional Resources

- [Vercel Speed Insights Documentation](https://vercel.com/docs/speed-insights)
- [Web Vitals Guide](https://web.dev/vitals/)
- [Vercel Analytics Overview](https://vercel.com/docs/analytics)

## Summary

Vercel Speed Insights has been successfully integrated into this Flask application. Once deployed to Vercel and enabled in the dashboard, it will automatically track and report Web Vitals metrics with zero additional configuration needed.
