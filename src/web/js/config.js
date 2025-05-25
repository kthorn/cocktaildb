// Configuration for the Cocktail Database application (dev environment)
const config = {
    // API endpoint
    apiUrl: 'https://notydlwqjg.execute-api.us-east-1.amazonaws.com/api',

    // Cognito configuration
    userPoolId: 'us-east-1_soMU2Xdub',
    clientId: '2tlupke974via48519tnc1ioto',
    cognitoDomain: 'https://cocktaildbauth-dev-732940910135.auth.us-east-1.amazoncognito.com', // This is the base Cognito Hosted UI domain

    // Application URL (for redirects, etc.)
    appUrl: 'https://dm5yrgc752xin.cloudfront.net',

    // General settings
    appName: 'Cocktail Database (dev)'
};

// Export the configuration
export default config;
