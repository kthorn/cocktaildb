// Configuration for the Cocktail Database application (prod environment)
const config = {
    // API endpoint
    apiUrl: 'https://a5crx5o72d.execute-api.us-east-1.amazonaws.com/api',

    // Cognito configuration
    userPoolId: 'us-east-1_nBFSSIaCD',
    clientId: '4klgtis5qqa9eb7anku6rsr979',
    cognitoDomain: 'https://cocktaildbauth-prod-732940910135.auth.us-east-1.amazoncognito.com', // This is the base Cognito Hosted UI domain

    // Application URL (for redirects, etc.)
    appUrl: 'https://mixology.tools',

    // General settings
    appName: 'Cocktail Database (prod)'
};

// Export the configuration
export default config;
