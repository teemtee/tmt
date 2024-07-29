// Respect browsers with light color scheme preference
// Wait for the DOM to be fully loaded before running the script
document.addEventListener('DOMContentLoaded', (event) => {
    // Check if the browser supports the matchMedia method
    // and if the user has set a preference for light mode
    if (window.matchMedia && window.matchMedia('(prefers-color-scheme: light)').matches) {
        // If the user prefers light mode, set the theme to light
        // This overrides the default dark theme set in conf.py
        document.documentElement.dataset.theme = 'light';
    }
    // If the user hasn't set a preference or prefers dark mode,
    // the theme will remain dark as set in conf.py
});
