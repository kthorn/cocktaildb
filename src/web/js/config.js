// Configuration for the Cocktail Database application (dev environment)
const config = {
    // API endpoint
    apiUrl: 'https://6kukiw1dxg.execute-api.us-east-1.amazonaws.com/api',

    // Cognito configuration
    userPoolId: 'us-east-1_LvzBbpSF3',
    clientId: '3j29jtgdfvc058hdbn9p5nnome',
    cognitoDomain: 'https://cocktaildbauth-dev-732940910135.auth.us-east-1.amazoncognito.com', // This is the base Cognito Hosted UI domain

    // Application URL (for redirects, etc.)
    appUrl: 'https://d2ifvut6v1mmr8.cloudfront.net',

    // General settings
    appName: 'Cocktail Database (dev)'
};

// Export the configuration
export default config;
